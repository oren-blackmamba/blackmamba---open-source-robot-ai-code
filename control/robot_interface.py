"""Robot interface and the simulated robot.

All physical actions go through ``RobotInterface.execute``. The simulated robot
validates every command with the safety monitor and accounts for time and
energy, so the AI layer cannot bypass the safety checks.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Optional

from energy.battery_monitor import BatteryMonitor
from energy.power_estimator import PowerEstimator
from safety.emergency_stop import EmergencyStop
from safety.operating_limits import OperatingLimits
from safety.safety_monitor import SafetyMonitor


@dataclass
class Command:
    kind: str                      # walk | stand | manipulate | gesture | rest | charge
    params: dict = field(default_factory=dict)


@dataclass
class CommandResult:
    ok: bool
    reason: str = ""
    code: str = "ok"
    duration_s: float = 0.0
    energy_wh: float = 0.0


@dataclass(frozen=True)
class RobotState:
    x: float
    y: float
    heading: float
    time_s: float
    soc: float
    energy_wh: float
    usable_wh: float
    temperature_c: float
    mode: str
    estop_active: bool
    total_drawn_wh: float
    distance_m: float


class RobotInterface(ABC):
    @abstractmethod
    def execute(self, cmd: Command) -> CommandResult:
        """Run a command through the safety layer."""

    @abstractmethod
    def state(self) -> RobotState:
        """Current robot state."""


_MODE_FOR_KIND = {
    "stand": "standing",
    "manipulate": "manipulating",
    "gesture": "gesture",
    "rest": "low_power",
}


class SimulatedRobot(RobotInterface):
    """Time- and energy-accurate (within the model) simulated humanoid."""

    CHUNK_S = 60.0

    def __init__(self, cfg: dict[str, Any], start: tuple[float, float] = (0.0, 0.0),
                 dock: Optional[tuple[float, float]] = None,
                 estop: Optional[EmergencyStop] = None,
                 safety: Optional[SafetyMonitor] = None):
        self.cfg = cfg
        self.estimator = PowerEstimator.from_config(cfg)
        self.battery = BatteryMonitor.from_config(cfg)
        self.estop = estop or EmergencyStop()
        self.safety = safety or SafetyMonitor(OperatingLimits.from_config(cfg), self.estop)
        self.x, self.y = start
        self.heading = 0.0
        self.time_s = 0.0
        self.mode = "standing"
        self.distance_m = 0.0
        self.dock = dock
        self.charge_power_w = float(cfg.get("sim", {}).get("charge_power_w", 1500.0))
        self.nominal_speed = float(cfg["motion"]["nominal_walk_speed_m_s"])
        self.energy_by_mode: dict[str, float] = defaultdict(float)
        self.time_by_mode: dict[str, float] = defaultdict(float)

    # -- RobotInterface -------------------------------------------------
    def state(self) -> RobotState:
        b = self.battery
        return RobotState(
            x=self.x, y=self.y, heading=self.heading, time_s=self.time_s,
            soc=b.soc, energy_wh=b.energy_wh, usable_wh=b.usable_energy_wh,
            temperature_c=b.temperature_c, mode=self.mode,
            estop_active=self.estop.is_active, total_drawn_wh=b.total_drawn_wh,
            distance_m=self.distance_m,
        )

    def execute(self, cmd: Command) -> CommandResult:
        decision = self.safety.validate(cmd.kind, cmd.params, self.battery.soc,
                                        self.battery.temperature_c)
        if not decision.approved:
            return CommandResult(False, "; ".join(decision.reasons), decision.code)
        params = decision.params
        if cmd.kind == "walk":
            return self._walk(params)
        if cmd.kind == "charge":
            return self._charge(params)
        duration = float(params.get("duration_s", 0.0))
        done, wh = self._advance(_MODE_FOR_KIND[cmd.kind], duration, float(params.get("ai_load", 0.5)))
        return self._result(done, duration, wh)

    # -- internals ------------------------------------------------------
    def _result(self, done: float, wanted: float, wh: float) -> CommandResult:
        if done >= wanted - 1e-6:
            return CommandResult(True, duration_s=done, energy_wh=wh)
        return CommandResult(False, "battery reserve reached", "battery_protect", done, wh)

    def _advance(self, mode: str, duration: float, ai_load: float,
                 speed: Optional[float] = None) -> tuple[float, float]:
        """Run ``mode`` for up to ``duration`` s, in chunks. Returns (seconds done, Wh used)."""
        done = wh_total = 0.0
        remaining = duration
        while remaining > 1e-9:
            usable = self.battery.usable_energy_wh
            if usable <= 1e-9:
                break
            power = self.estimator.power_for(mode, ai_load, speed)
            dt = min(self.CHUNK_S, remaining, usable / power * 3600.0)
            wh = self.battery.draw(power, dt)
            self.time_s += dt
            self.mode = mode
            self.energy_by_mode[mode] += wh
            self.time_by_mode[mode] += dt
            wh_total += wh
            done += dt
            remaining -= dt
            if not self.safety.check_state(0.0, self.battery.soc, self.battery.temperature_c):
                break
        return done, wh_total

    def _walk(self, params: dict) -> CommandResult:
        tx, ty = params["to"]
        speed = float(params.get("speed", self.nominal_speed))
        dx, dy = tx - self.x, ty - self.y
        distance = math.hypot(dx, dy)
        if distance < 1e-9:
            return CommandResult(True)
        duration = distance / speed
        done, wh = self._advance("walking", duration, float(params.get("ai_load", 0.5)), speed)
        fraction = done / duration
        self.x += dx * fraction
        self.y += dy * fraction
        self.heading = math.atan2(dy, dx)
        self.distance_m += distance * fraction
        return self._result(done, duration, wh)

    def _charge(self, params: dict) -> CommandResult:
        if self.dock is None or math.hypot(self.x - self.dock[0], self.y - self.dock[1]) > 0.6:
            return CommandResult(False, "not at the charging dock", "not_at_dock")
        rest_w = self.estimator.power_for("low_power", 0.0)
        net_w = self.charge_power_w - rest_w
        if "target_soc" in params:
            needed_wh = max(0.0, float(params["target_soc"]) * self.battery.capacity_wh
                            - self.battery.energy_wh)
            duration = needed_wh / net_w * 3600.0
        else:
            duration = float(params.get("duration_s", 0.0))
        added = self.battery.charge(net_w, duration)
        duration = added / net_w * 3600.0
        self.time_s += duration
        self.mode = "charging"
        self.time_by_mode["charging"] += duration
        return CommandResult(True, duration_s=duration, energy_wh=-added)
