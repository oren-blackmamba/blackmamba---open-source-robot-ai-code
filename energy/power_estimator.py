"""Power model: electrical power per activity mode, including compute and sensors."""

from __future__ import annotations

import math
from typing import Any

MODES = ("standing", "walking", "manipulating", "gesture", "low_power")


class PowerEstimator:
    """Estimates the total electrical power of the robot.

    Walking power grows with speed as ``standing + k * v**2`` so that the energy
    per metre has a minimum at a moderate speed, like human cost of transport.
    """

    def __init__(self, table: dict[str, float], nominal_walk_speed: float = 1.0):
        self.table = {key: float(value) for key, value in table.items()}
        self.nominal_walk_speed = nominal_walk_speed

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> "PowerEstimator":
        return cls(cfg["power_w"], float(cfg["motion"]["nominal_walk_speed_m_s"]))

    def compute_power_w(self, ai_load: float) -> float:
        load = min(max(ai_load, 0.0), 1.0)
        idle, active = self.table["compute_idle"], self.table["compute_active"]
        return idle + (active - idle) * load

    @property
    def walk_k(self) -> float:
        """Speed-dependent walking coefficient, W per (m/s)^2."""
        return (self.table["walking"] - self.table["standing"]) / self.nominal_walk_speed ** 2

    def power_for(self, mode: str, ai_load: float = 0.5, speed: float | None = None) -> float:
        """Total power in W for an activity mode."""
        if mode not in MODES:
            raise ValueError(f"Unknown mode {mode!r}; expected one of {MODES}")
        if mode == "walking":
            v = self.nominal_walk_speed if speed is None else speed
            mechanical = self.table["standing"] + self.walk_k * v * v
        else:
            mechanical = self.table[mode]
        low = mode == "low_power"
        sensors = self.table["sensors"] * (0.5 if low else 1.0)
        compute = self.compute_power_w(0.0 if low else ai_load)
        return mechanical + compute + sensors

    def energy_wh(self, mode: str, duration_s: float, ai_load: float = 0.5,
                  speed: float | None = None) -> float:
        return self.power_for(mode, ai_load, speed) * duration_s / 3600.0

    def walk_energy_wh(self, distance_m: float, speed: float, ai_load: float = 0.5) -> float:
        if speed <= 0:
            raise ValueError("speed must be positive")
        return self.energy_wh("walking", distance_m / speed, ai_load, speed)

    def most_efficient_speed(self, max_speed: float, min_speed: float = 0.3,
                             ai_load: float = 0.5) -> float:
        """Speed that minimises energy per metre: v* = sqrt(overhead / k)."""
        overhead = self.table["standing"] + self.compute_power_w(ai_load) + self.table["sensors"]
        best = math.sqrt(overhead / self.walk_k)
        return min(max(best, min_speed), max_speed)
