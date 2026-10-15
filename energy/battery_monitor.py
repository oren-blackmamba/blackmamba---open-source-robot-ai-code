"""Software battery model: state of charge, reserve and temperature."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass
class BatteryMonitor:
    """Tracks the energy stored in the pack.

    ``reserve_fraction`` of the capacity is never available for work; it is kept
    for battery protection and a safe shutdown.
    """

    capacity_wh: float
    energy_wh: float
    reserve_fraction: float = 0.10
    temperature_c: float = 25.0
    ambient_c: float = 25.0
    thermal_tau_s: float = 600.0
    thermal_k_c_per_w: float = 0.025
    total_drawn_wh: float = 0.0

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> "BatteryMonitor":
        battery = cfg["battery"]
        capacity = float(battery["capacity_wh"])
        ambient = float(cfg.get("sim", {}).get("ambient_temp_c", 25.0))
        return cls(
            capacity_wh=capacity,
            energy_wh=capacity * float(battery.get("initial_soc", 1.0)),
            reserve_fraction=float(battery["reserve_fraction"]),
            temperature_c=ambient,
            ambient_c=ambient,
        )

    @property
    def soc(self) -> float:
        """State of charge, 0..1."""
        return self.energy_wh / self.capacity_wh

    @property
    def reserve_wh(self) -> float:
        return self.capacity_wh * self.reserve_fraction

    @property
    def usable_energy_wh(self) -> float:
        """Energy available for work, above the protected reserve."""
        return max(0.0, self.energy_wh - self.reserve_wh)

    @property
    def usable_fraction(self) -> float:
        """Usable energy relative to a full pack's usable energy, 0..1."""
        return self.usable_energy_wh / (self.capacity_wh - self.reserve_wh)

    @property
    def is_depleted(self) -> bool:
        return self.usable_energy_wh <= 1e-9

    def is_low(self, threshold_soc: float = 0.20) -> bool:
        return self.soc <= threshold_soc

    def draw(self, power_w: float, dt_s: float) -> float:
        """Draw ``power_w`` for ``dt_s`` seconds. Returns the energy drawn in Wh."""
        wh = min(max(power_w, 0.0) * dt_s / 3600.0, self.energy_wh)
        self.energy_wh -= wh
        self.total_drawn_wh += wh
        self._update_thermal(power_w, dt_s)
        return wh

    def charge(self, power_w: float, dt_s: float) -> float:
        """Charge at ``power_w`` for ``dt_s`` seconds. Returns the energy added in Wh."""
        wh = min(max(power_w, 0.0) * dt_s / 3600.0, self.capacity_wh - self.energy_wh)
        self.energy_wh += wh
        self._update_thermal(300.0, dt_s)
        return wh

    def _update_thermal(self, power_w: float, dt_s: float) -> None:
        target = self.ambient_c + self.thermal_k_c_per_w * power_w
        alpha = 1.0 - math.exp(-dt_s / self.thermal_tau_s)
        self.temperature_c += (target - self.temperature_c) * alpha
