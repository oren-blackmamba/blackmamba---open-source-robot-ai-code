"""Joint-level controller that enforces range and velocity limits."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class JointLimits:
    name: str
    min_rad: float
    max_rad: float
    max_speed_rad_s: float


class ActuatorController:
    """Slews joints toward targets without exceeding position or speed limits."""

    def __init__(self, limits: Iterable[JointLimits]):
        self.limits = {item.name: item for item in limits}
        self.positions = {name: 0.0 for name in self.limits}

    def reset(self) -> None:
        self.positions = {name: 0.0 for name in self.limits}

    def step(self, targets: dict[str, float], dt: float) -> dict[str, float]:
        for name, target in targets.items():
            if name not in self.limits:
                raise KeyError(f"Unknown joint {name!r}")
            limit = self.limits[name]
            target = min(max(target, limit.min_rad), limit.max_rad)
            max_delta = limit.max_speed_rad_s * dt
            delta = min(max(target - self.positions[name], -max_delta), max_delta)
            self.positions[name] += delta
        return dict(self.positions)
