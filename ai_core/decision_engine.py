"""Action selection under energy constraints."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from energy.energy_optimizer import EnergyOptimizer, PlanOption


@dataclass(frozen=True)
class Approval:
    approved: bool
    reason: str
    required_wh: float


class DecisionEngine:
    def __init__(self, optimizer: EnergyOptimizer, low_soc: float = 0.20,
                 margin_fraction: float = 0.15):
        self.optimizer = optimizer
        self.low_soc = low_soc
        self.margin_fraction = margin_fraction

    def approve(self, plan_energy_wh: float, usable_wh: float,
                return_energy_wh: float = 0.0) -> Approval:
        """Approve a plan only if it fits the usable energy with a safety margin."""
        required = plan_energy_wh * (1.0 + self.margin_fraction) + return_energy_wh
        if required <= usable_wh:
            return Approval(True, "enough energy", required)
        return Approval(False, f"needs {required:.1f} Wh but only {usable_wh:.1f} Wh usable", required)

    def choose_plan(self, options: Sequence[PlanOption],
                    usable_wh: Optional[float] = None) -> Optional[PlanOption]:
        return self.optimizer.choose(options, usable_wh)

    def should_return_to_dock(self, soc: float) -> bool:
        return soc <= self.low_soc

    def idle_mode(self, usable_fraction: float, time_fraction_remaining: float,
                  tolerance: float = 0.02) -> str:
        """Stay attentive while the energy pace is on schedule, else drop to low power."""
        if usable_fraction + tolerance >= time_fraction_remaining:
            return "stand"
        return "rest"
