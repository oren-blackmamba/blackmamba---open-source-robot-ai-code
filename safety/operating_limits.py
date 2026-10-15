"""Hard operating limits enforced by the safety monitor."""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any


@dataclass(frozen=True)
class OperatingLimits:
    max_joint_speed_rad_s: float = 3.0
    max_walk_speed_m_s: float = 1.4
    max_tilt_deg: float = 25.0
    min_soc_to_work: float = 0.10
    max_battery_temp_c: float = 55.0

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> "OperatingLimits":
        section = cfg["safety"]
        values = {f.name: float(section[f.name]) for f in fields(cls) if f.name in section}
        return cls(**values)
