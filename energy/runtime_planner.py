"""Runtime planning: can a given workload run for the target number of hours?"""

from __future__ import annotations

from dataclasses import dataclass

from energy.battery_monitor import BatteryMonitor
from energy.power_estimator import PowerEstimator


@dataclass(frozen=True)
class DutyFit:
    duty: dict
    useful_fraction: float   # share of the desired workload that fits the budget
    feasible: bool
    average_power_w: float
    budget_w: float


class RuntimePlanner:
    """Projects runtime from a duty cycle (fraction of time per activity mode)."""

    def __init__(self, battery: BatteryMonitor, estimator: PowerEstimator, ai_load: float = 0.5):
        self.battery = battery
        self.estimator = estimator
        self.ai_load = ai_load

    def average_power_w(self, duty: dict[str, float]) -> float:
        total = sum(duty.values())
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"Duty cycle fractions must sum to 1, got {total}")
        return sum(frac * self.estimator.power_for(mode, self.ai_load) for mode, frac in duty.items())

    def sustainable_power_w(self, hours: float) -> float:
        """Average power the usable energy can sustain for ``hours``."""
        return self.battery.usable_energy_wh / hours

    def projected_runtime_h(self, duty: dict[str, float]) -> float:
        return self.battery.usable_energy_wh / self.average_power_w(duty)

    def remaining_runtime_h(self, average_power_w: float) -> float:
        return self.battery.usable_energy_wh / average_power_w

    def fit_duty_cycle(self, desired: dict[str, float], hours: float) -> DutyFit:
        """Blend the desired workload with low-power time until it fits ``hours``."""
        desired_power = self.average_power_w(desired)
        budget = self.sustainable_power_w(hours)
        if desired_power <= budget:
            return DutyFit(dict(desired), 1.0, True, desired_power, budget)
        low_power = self.estimator.power_for("low_power", self.ai_load)
        if low_power >= budget:
            return DutyFit({"low_power": 1.0}, 0.0, False, low_power, budget)
        shift = (desired_power - budget) / (desired_power - low_power)
        duty = {mode: frac * (1.0 - shift) for mode, frac in desired.items()}
        duty["low_power"] = duty.get("low_power", 0.0) + shift
        return DutyFit(duty, 1.0 - shift, True, self.average_power_w(duty), budget)
