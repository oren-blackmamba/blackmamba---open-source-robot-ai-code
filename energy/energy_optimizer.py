"""Energy-aware choice between alternative plans and walking speeds."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from energy.power_estimator import PowerEstimator


@dataclass(frozen=True)
class PlanOption:
    name: str
    duration_s: float
    energy_wh: float


class EnergyOptimizer:
    """Scores options by energy plus a value placed on time.

    ``time_weight_wh_per_min`` says how many Wh one minute of the robot's time is
    worth, so the optimizer never picks a plan that is cheap but absurdly slow.
    """

    def __init__(self, time_weight_wh_per_min: float = 0.5):
        self.time_weight = time_weight_wh_per_min

    def cost(self, option: PlanOption) -> float:
        return option.energy_wh + self.time_weight * option.duration_s / 60.0

    def choose(self, options: Sequence[PlanOption],
               energy_budget_wh: Optional[float] = None) -> Optional[PlanOption]:
        """Cheapest option that fits the energy budget, or None if none fits."""
        feasible = [o for o in options if energy_budget_wh is None or o.energy_wh <= energy_budget_wh]
        return min(feasible, key=self.cost) if feasible else None

    def choose_walk_speed(self, estimator: PowerEstimator, distance_m: float,
                          max_speed: float, ai_load: float = 0.5) -> float:
        """Walking speed (m/s) with the lowest combined energy and time cost."""
        if distance_m <= 1e-9:
            return min(estimator.nominal_walk_speed, max_speed)
        best_speed, best_cost = 0.3, float("inf")
        speed = 0.3
        while speed <= max_speed + 1e-9:
            option = PlanOption(
                f"{speed:.2f} m/s",
                distance_m / speed,
                estimator.walk_energy_wh(distance_m, speed, ai_load),
            )
            cost = self.cost(option)
            if cost < best_cost:
                best_speed, best_cost = speed, cost
            speed = round(speed + 0.05, 10)
        return best_speed
