"""Human-proportioned MuJoCo (MJCF) model, generated from ``HumanoidModel``.

The joint names, position limits and rotation conventions are the same as in the software
model, so a gesture or pose computed anywhere in HUMANIS can drive the physical model.

Body (all numbers are ASSUMED, chosen to match an average adult; replace them with measured
values from a real prototype):

    height 1.75 m, mass ~70 kg, hip height 0.91 m
    pelvis 10 kg, torso 22 kg, head 5 kg, arm 4 kg each, leg 12.7 kg each

Coordinates: x forward, y left, z up. A positive rotation about +y swings a hanging limb
backwards, so hip/shoulder pitch are negative for "forward", and knee flexion is positive.

Self-collision is disabled; only the feet and body collide with the floor, so a falling robot
can pass its limbs through each other. This keeps the model fast and stable.
"""

from __future__ import annotations

from simulation.robot_model.humanoid_model import HumanoidModel

TIMESTEP_S = 0.002

# joint -> (axis, kp, kv, torque limit in N*m)
_JOINT_SPEC: dict[str, tuple[str, float, float, float]] = {
    "neck_yaw": ("0 0 1", 30, 3, 20), "neck_pitch": ("0 1 0", 30, 3, 20),
    "torso_yaw": ("0 0 1", 300, 20, 120),
    "shoulder_pitch": ("0 1 0", 120, 10, 80), "shoulder_roll": ("1 0 0", 120, 10, 80),
    "elbow": ("0 1 0", 80, 8, 60), "wrist": ("0 1 0", 20, 2, 15),
    "hip_pitch": ("0 1 0", 1200, 80, 250), "hip_roll": ("1 0 0", 1200, 80, 250),
    "knee": ("0 1 0", 1000, 70, 250), "ankle_pitch": ("0 1 0", 600, 40, 150),
}

PELVIS_HEIGHT_M = 0.93


def _spec(name: str) -> tuple[str, float, float, float]:
    key = name[2:] if name[:2] in ("r_", "l_") else name
    return _JOINT_SPEC[key]


def _joint(model: HumanoidModel, name: str) -> str:
    limit = next(j for j in model.joints if j.name == name)
    axis, _, _, _ = _spec(name)
    return (f'<joint name="{name}" type="hinge" axis="{axis}" '
            f'range="{limit.min_rad} {limit.max_rad}" damping="1" armature="0.05"/>')


def _arm(model: HumanoidModel, side: str, sign: int) -> str:
    p = f"{side}_"
    return f"""
        <body name="{p}upper_arm" pos="0 {0.22 * sign} 0.43">
          {_joint(model, p + 'shoulder_pitch')}
          {_joint(model, p + 'shoulder_roll')}
          <geom type="capsule" fromto="0 0 0 0 0 -0.30" size="0.04" mass="2.0"/>
          <body name="{p}forearm" pos="0 0 -0.30">
            {_joint(model, p + 'elbow')}
            <geom type="capsule" fromto="0 0 0 0 0 -0.26" size="0.035" mass="1.4"/>
            <body name="{p}hand" pos="0 0 -0.26">
              {_joint(model, p + 'wrist')}
              <geom type="box" pos="0 0 -0.07" size="0.03 0.05 0.07" mass="0.6"/>
            </body>
          </body>
        </body>"""


def _leg(model: HumanoidModel, side: str, sign: int) -> str:
    p = f"{side}_"
    return f"""
      <body name="{p}thigh" pos="0 {0.09 * sign} -0.02">
        {_joint(model, p + 'hip_roll')}
        {_joint(model, p + 'hip_pitch')}
        <geom type="capsule" fromto="0 0 0 0 0 -0.43" size="0.06" mass="8.0"/>
        <body name="{p}shank" pos="0 0 -0.43">
          {_joint(model, p + 'knee')}
          <geom type="capsule" fromto="0 0 0 0 0 -0.40" size="0.045" mass="3.5"/>
          <body name="{p}foot" pos="0 0 -0.40">
            {_joint(model, p + 'ankle_pitch')}
            <geom name="{p}foot_geom" type="box" pos="0.05 0 -0.04" size="0.13 0.05 0.04"
                  mass="1.2" friction="1.0 0.005 0.0001"/>
          </body>
        </body>
      </body>"""


def build_mjcf(model: HumanoidModel | None = None) -> str:
    """Return the MJCF XML of the humanoid standing on a floor."""
    model = model or HumanoidModel.default()
    actuators = "\n    ".join(
        f'<position name="{n}" joint="{n}" kp="{_spec(n)[1]}" kv="{_spec(n)[2]}" '
        f'ctrllimited="true" ctrlrange="{lim.min_rad} {lim.max_rad}" '
        f'forcelimited="true" forcerange="-{_spec(n)[3]} {_spec(n)[3]}"/>'
        for n, lim in ((j.name, j) for j in model.joints))
    return f"""<mujoco model="humanis">
  <compiler angle="radian" autolimits="true"/>
  <option timestep="{TIMESTEP_S}" integrator="implicitfast" gravity="0 0 -9.81"/>
  <default>
    <geom contype="1" conaffinity="0" condim="3"/>
  </default>
  <worldbody>
    <geom name="floor" type="plane" size="20 20 0.1" contype="0" conaffinity="1"
          friction="1.0 0.005 0.0001"/>
    <body name="pelvis" pos="0 0 {PELVIS_HEIGHT_M}">
      <freejoint name="root"/>
      <geom type="box" size="0.08 0.14 0.07" mass="10"/>
      <body name="torso" pos="0 0 0.07">
        {_joint(model, 'torso_yaw')}
        <geom type="box" pos="0 0 0.25" size="0.09 0.16 0.25" mass="22"/>
        <body name="head" pos="0 0 0.5">
          {_joint(model, 'neck_yaw')}
          {_joint(model, 'neck_pitch')}
          <geom type="sphere" pos="0 0 0.13" size="0.11" mass="5"/>
        </body>{_arm(model, 'r', -1)}{_arm(model, 'l', 1)}
      </body>{_leg(model, 'r', -1)}{_leg(model, 'l', 1)}
    </body>
  </worldbody>
  <actuator>
    {actuators}
  </actuator>
</mujoco>
"""


def write_mjcf(path: str, model: HumanoidModel | None = None) -> str:
    """Write the model to ``path`` so it can be opened in the MuJoCo viewer."""
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(build_mjcf(model))
    return path
