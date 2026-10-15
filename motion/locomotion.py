"""Gait generation and walk planning."""

from __future__ import annotations

import math
from dataclasses import dataclass

from energy.power_estimator import PowerEstimator


@dataclass(frozen=True)
class Footstep:
    index: int
    foot: str
    x: float
    y: float
    time_s: float


@dataclass(frozen=True)
class WalkPlan:
    distance_m: float
    duration_s: float
    steps: int
    energy_wh: float


class GaitGenerator:
    @staticmethod
    def step_length_m(speed: float) -> float:
        return min(0.30 + 0.30 * speed, 0.8)

    def cadence_hz(self, speed: float) -> float:
        return speed / self.step_length_m(speed)

    def footsteps(self, start: tuple[float, float], end: tuple[float, float],
                  speed: float, t0: float = 0.0) -> list[Footstep]:
        dx, dy = end[0] - start[0], end[1] - start[1]
        distance = math.hypot(dx, dy)
        if distance < 1e-9:
            return []
        count = max(1, math.ceil(distance / self.step_length_m(speed)))
        interval = (distance / speed) / count
        steps = []
        for i in range(1, count + 1):
            frac = i / count
            steps.append(Footstep(i, "left" if i % 2 else "right",
                                  start[0] + dx * frac, start[1] + dy * frac, t0 + i * interval))
        return steps


class Locomotion:
    def __init__(self, estimator: PowerEstimator, gait: GaitGenerator | None = None):
        self.estimator = estimator
        self.gait = gait or GaitGenerator()

    def plan_walk(self, start: tuple[float, float], waypoints: list[tuple[float, float]],
                  speed: float) -> WalkPlan:
        distance = steps = 0
        position = start
        for waypoint in waypoints:
            distance += math.hypot(waypoint[0] - position[0], waypoint[1] - position[1])
            steps += len(self.gait.footsteps(position, waypoint, speed))
            position = waypoint
        return WalkPlan(distance, distance / speed, steps,
                        self.estimator.walk_energy_wh(distance, speed) if distance else 0.0)
