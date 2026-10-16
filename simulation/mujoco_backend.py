"""MuJoCo physics backend for the HUMANIS humanoid.

What is real physics here: rigid-body dynamics of a 70 kg, 1.75 m human-proportioned body with
19 torque-limited position-controlled joints, contact and friction with the floor, balance under
pushes, and joint torques and speeds from which electrical power is computed.

What is NOT implemented: walking (needs a gait controller), grasping and carrying (needs a
hand and contact model). The backend refuses those commands instead of faking them.

All body, motor and gain parameters are ASSUMPTIONS, not measurements of real hardware.
Requires:  pip install mujoco
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Optional

try:
    import mujoco
    import numpy as np
except ImportError as error:  # pragma: no cover - exercised only without mujoco
    raise ImportError("The physics backend needs MuJoCo: pip install mujoco") from error

from control.actuator_controller import ActuatorController
from control.robot_interface import Command, CommandResult, SimulatedRobot
from motion.gesture_controller import GestureController, gesture_duration_s
from simulation.robot_model.humanoid_model import HumanoidModel
from simulation.robot_model.mjcf import TIMESTEP_S, build_mjcf

# Motor constant Km (N*m per sqrt(W)): copper loss is (torque / Km)^2. ASSUMED values.
_MOTOR_KM = {"hip_pitch": 2.5, "hip_roll": 2.5, "knee": 2.5, "ankle_pitch": 1.5,
             "torso_yaw": 1.5, "shoulder_pitch": 1.0, "shoulder_roll": 1.0, "elbow": 0.8,
             "wrist": 0.3, "neck_yaw": 0.3, "neck_pitch": 0.3}


def _km(joint: str) -> float:
    return _MOTOR_KM[joint[2:] if joint[:2] in ("r_", "l_") else joint]


@dataclass(frozen=True)
class PushResult:
    impulse_ns: float
    fell: bool
    max_tilt_deg: float
    max_com_shift_m: float
    final_tilt_deg: float


class MuJoCoHumanoid:
    """The physical body: stepping, measurement and electrical power."""

    FALL_TILT_DEG = 40.0

    def __init__(self, model: Optional[HumanoidModel] = None, control_dt_s: float = 0.01,
                 motor_efficiency: float = 0.8):
        self.humanoid = model or HumanoidModel.default()
        self.control_dt = control_dt_s
        self.substeps = max(1, round(control_dt_s / TIMESTEP_S))
        self.efficiency = motor_efficiency
        self.model = mujoco.MjModel.from_xml_string(build_mjcf(self.humanoid))
        self.data = mujoco.MjData(self.model)
        self.joint_names = [j.name for j in self.humanoid.joints]
        self._actuator = {n: self.model.actuator(n).id for n in self.joint_names}
        self._dof = np.array([self.model.joint(n).dofadr[0] for n in self.joint_names])
        self._km = np.array([_km(n) for n in self.joint_names])
        self._torso = self.model.body("torso").id
        self._pelvis = self.model.body("pelvis").id
        self.reset()

    def reset(self) -> None:
        mujoco.mj_resetData(self.model, self.data)
        mujoco.mj_forward(self.model, self.data)
        self.time_s = 0.0

    def place(self, x: float, y: float, heading_rad: float = 0.0) -> None:
        """Stand the robot at (x, y) facing ``heading_rad``, upright and at rest."""
        self.reset()
        self.data.qpos[0:2] = (x, y)
        self.data.qpos[3:7] = (math.cos(heading_rad / 2), 0.0, 0.0, math.sin(heading_rad / 2))
        mujoco.mj_forward(self.model, self.data)

    # -- stepping -------------------------------------------------------
    def step(self, targets: dict[str, float]) -> float:
        """Advance one control period toward joint ``targets`` (rad). Returns mean electrical
        joint power in W over the period (mechanical + copper loss)."""
        for name, value in targets.items():
            self.data.ctrl[self._actuator[name]] = value
        energy_j = 0.0
        for _ in range(self.substeps):
            mujoco.mj_step(self.model, self.data)
            energy_j += self._joint_power_w() * TIMESTEP_S
        self.time_s += self.substeps * TIMESTEP_S
        return energy_j / (self.substeps * TIMESTEP_S)

    def _joint_power_w(self) -> float:
        torque = self.data.qfrc_actuator[self._dof]
        speed = self.data.qvel[self._dof]
        mechanical = np.maximum(torque * speed, 0.0) / self.efficiency   # no regeneration
        copper = (torque / self._km) ** 2
        return float(np.sum(mechanical + copper))

    # -- measurements ---------------------------------------------------
    @property
    def tilt_deg(self) -> float:
        """Angle between the torso's up axis and vertical."""
        up = self.data.xmat[self._torso].reshape(3, 3)[2, 2]
        return math.degrees(math.acos(min(1.0, max(-1.0, float(up)))))

    @property
    def pelvis_height_m(self) -> float:
        return float(self.data.xpos[self._pelvis][2])

    @property
    def position_xy(self) -> tuple[float, float]:
        x, y = self.data.xpos[self._pelvis][:2]
        return float(x), float(y)

    @property
    def heading_rad(self) -> float:
        forward = self.data.xmat[self._pelvis].reshape(3, 3)[:, 0]
        return math.atan2(float(forward[1]), float(forward[0]))

    @property
    def com_xy(self) -> tuple[float, float]:
        x, y = self.data.subtree_com[self._pelvis][:2]
        return float(x), float(y)

    @property
    def total_mass_kg(self) -> float:
        return float(self.model.body_subtreemass[self._pelvis])

    @property
    def has_fallen(self) -> bool:
        return self.tilt_deg > self.FALL_TILT_DEG or self.pelvis_height_m < 0.5

    # -- disturbance ----------------------------------------------------
    def push(self, impulse_ns: float, direction_deg: float = 0.0, duration_s: float = 0.1,
             observe_s: float = 3.0, hold: Optional[dict[str, float]] = None) -> PushResult:
        """Apply a horizontal push to the torso and watch whether the robot stays up.

        ``direction_deg`` 0 pushes forward, 90 to the left. Returns tilt and centre-of-mass
        excursion statistics.
        """
        hold = hold or {n: 0.0 for n in self.joint_names}
        com0 = self.com_xy
        angle = math.radians(direction_deg)
        force = impulse_ns / duration_s
        max_tilt = max_shift = 0.0
        steps = int((duration_s + observe_s) / self.control_dt)
        push_steps = int(duration_s / self.control_dt)
        for i in range(steps):
            self.data.xfrc_applied[self._torso, :3] = (
                (force * math.cos(angle), force * math.sin(angle), 0.0) if i < push_steps else (0, 0, 0))
            self.step(hold)
            max_tilt = max(max_tilt, self.tilt_deg)
            x, y = self.com_xy
            max_shift = max(max_shift, math.hypot(x - com0[0], y - com0[1]))
            if self.has_fallen:
                break
        self.data.xfrc_applied[:] = 0.0
        return PushResult(impulse_ns, self.has_fallen, max_tilt, max_shift, self.tilt_deg)


class MuJoCoRobot(SimulatedRobot):
    """``RobotInterface`` whose time, motion and energy come from the physics engine.

    Commands still go through the safety monitor. Standing, resting and gestures run in
    physics; walking and manipulating are refused because they are not implemented.
    """

    def __init__(self, cfg: dict[str, Any], **kwargs):
        super().__init__(cfg, **kwargs)
        settings = cfg.get("mujoco", {})
        self.body = MuJoCoHumanoid(HumanoidModel.from_config(cfg),
                                   float(settings.get("control_dt_s", 0.01)),
                                   float(settings.get("motor_efficiency", 0.8)))
        self.body.place(self.x, self.y)                 # the body starts where the robot says it is
        self.actuators = ActuatorController(self.body.humanoid.joint_limits())
        self.quiescent_w = float(settings.get("driver_quiescent_w_per_joint", 1.5)) * len(self.body.joint_names)
        self.last_joint_power_w = 0.0

    # -- commands -------------------------------------------------------
    def execute(self, cmd: Command) -> CommandResult:
        if cmd.kind == "gesture":
            return self._gesture(cmd)
        if cmd.kind == "manipulate":
            decision = self.safety.validate("manipulate", cmd.params, self.battery.soc,
                                            self.battery.temperature_c)
            if not decision.approved:
                return CommandResult(False, "; ".join(decision.reasons), decision.code)
            return CommandResult(False, "grasping is not implemented in the MuJoCo backend",
                                 "unsupported")
        return super().execute(cmd)

    def _result(self, done: float, wanted: float, wh: float) -> CommandResult:
        if done < wanted - 1e-6 and self.estop.is_active:
            return CommandResult(False, self.estop.reason, "estop", done, wh)
        return super()._result(done, wanted, wh)

    def _walk(self, params: dict) -> CommandResult:
        return CommandResult(False, "walking is not implemented in the MuJoCo backend",
                             "unsupported")

    def _gesture(self, cmd: Command) -> CommandResult:
        decision = self.safety.validate("gesture", cmd.params, self.battery.soc,
                                        self.battery.temperature_c)
        if not decision.approved:
            return CommandResult(False, "; ".join(decision.reasons), decision.code)
        name = cmd.params.get("name", "wave")
        ai_load = float(cmd.params.get("ai_load", 0.5))
        before_wh, before_s = self.battery.total_drawn_wh, self.time_s
        stopped = False

        def follow(positions: dict[str, float], dt: float) -> None:
            nonlocal stopped
            if not stopped:
                stopped = not self._tick(positions, "gesture", ai_load)

        GestureController(self.actuators, self.body.control_dt).perform(name, on_step=follow)
        done, wh = self.time_s - before_s, self.battery.total_drawn_wh - before_wh
        wanted = float(cmd.params.get("duration_s", gesture_duration_s(name)))
        if not stopped and wanted > done:                       # hold still for the remainder
            extra, extra_wh = self._advance("standing", wanted - done, ai_load)
            done, wh = done + extra, wh + extra_wh
        return self._result(done, wanted, wh)

    # -- physics-driven time and energy ---------------------------------
    def _tick(self, targets: dict[str, float], mode: str, ai_load: float) -> bool:
        """One control period. Returns False if the safety layer stopped the robot."""
        dt = self.body.control_dt
        joint_w = self.body.step(targets)
        self.last_joint_power_w = joint_w
        total_w = (joint_w + self.quiescent_w + self.estimator.compute_power_w(ai_load)
                   + self.estimator.table["sensors"] * (0.5 if mode == "low_power" else 1.0))
        wh = self.battery.draw(total_w, dt)
        self.time_s += dt
        self.mode = mode
        self.energy_by_mode[mode] += wh
        self.time_by_mode[mode] += dt
        self.x, self.y = self.body.position_xy
        self.heading = self.body.heading_rad
        return self.safety.check_state(self.body.tilt_deg, self.battery.soc,
                                       self.battery.temperature_c)

    def _advance(self, mode: str, duration: float, ai_load: float,
                 speed: Optional[float] = None) -> tuple[float, float]:
        """Hold the current pose in physics for ``duration`` seconds."""
        done = wh_total = 0.0
        dt = self.body.control_dt
        while done < duration - 1e-9:
            if self.battery.usable_energy_wh <= 1e-9:
                break
            before = self.battery.total_drawn_wh
            ok = self._tick(dict(self.actuators.positions), mode, ai_load)
            wh_total += self.battery.total_drawn_wh - before
            done += dt
            if not ok:
                break
        return done, wh_total
