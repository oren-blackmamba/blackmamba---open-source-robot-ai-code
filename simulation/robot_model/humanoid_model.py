"""Kinematic summary of the simulated humanoid (joint limits and body parameters)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from control.actuator_controller import JointLimits

# name, min_rad, max_rad, max_speed_rad_s (all speeds stay within the 3.0 rad/s safety limit)
_JOINTS = (
    ("neck_yaw", -1.5, 1.5, 3.0), ("neck_pitch", -0.6, 0.6, 3.0),
    ("torso_yaw", -0.8, 0.8, 2.0),
    ("r_shoulder_pitch", -3.1, 1.5, 2.5), ("r_shoulder_roll", -1.5, 0.3, 2.5),
    ("r_elbow", -2.5, 0.1, 3.0), ("r_wrist", -1.2, 1.2, 3.0),
    ("l_shoulder_pitch", -3.1, 1.5, 2.5), ("l_shoulder_roll", -0.3, 1.5, 2.5),
    ("l_elbow", -2.5, 0.1, 3.0), ("l_wrist", -1.2, 1.2, 3.0),
    ("r_hip_pitch", -1.8, 0.7, 2.5), ("r_hip_roll", -0.5, 0.5, 2.0),
    ("r_knee", 0.0, 2.4, 2.5), ("r_ankle_pitch", -0.8, 0.8, 3.0),
    ("l_hip_pitch", -1.8, 0.7, 2.5), ("l_hip_roll", -0.5, 0.5, 2.0),
    ("l_knee", 0.0, 2.4, 2.5), ("l_ankle_pitch", -0.8, 0.8, 3.0),
)


@dataclass
class HumanoidModel:
    mass_kg: float = 70.0
    height_m: float = 1.75
    com_height_m: float = 0.9
    joints: list[JointLimits] = field(default_factory=list)

    @classmethod
    def default(cls) -> "HumanoidModel":
        return cls(joints=[JointLimits(*row) for row in _JOINTS])

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> "HumanoidModel":
        model = cls.default()
        model.mass_kg = float(cfg["robot"]["mass_kg"])
        model.height_m = float(cfg["robot"]["height_m"])
        model.com_height_m = float(cfg["motion"]["com_height_m"])
        return model

    def joint_limits(self) -> list[JointLimits]:
        return list(self.joints)
