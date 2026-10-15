"""A full working shift: a stream of requests handled by the agent on one battery charge.

The shift is a model-based simulation. Its result is only as good as the assumed
power numbers in config/robot_config.yaml; it does NOT show that real hardware
reaches the same runtime.
"""

from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Optional

from ai_core.agent import HumanisAgent
from config.loader import load_config
from control.robot_interface import Command, SimulatedRobot
from simulation.environments.home_environment import HomeEnvironment

GOAL_POOL = [
    "תביא לי את הכוס מהמטבח לסלון",
    "bring me the cup from the kitchen",
    "הבא את הספר לחדר השינה",
    "bring the toolbox to the living room",
    "fetch the medicine box and bring it to the desk",
    "תביא את התרופות לסלון",
    "לך לסדנה",
    "go to the kitchen",
    "walk to the door",
    "wave hello",
    "נופף לשלום",
    "do something",
    "where is the cup?",
    "איפה הספר?",
    "כמה סוללה נשארה?",
    "bring it to the desk",
    "תודה",
]


@dataclass
class ShiftReport:
    hours_target: float
    hours_operated: float
    completed_target: bool
    ended_reason: str
    goals_total: int
    goals_by_status: dict
    distance_m: float
    energy_used_wh: float
    average_power_w: float
    final_soc: float
    energy_left_pct: float
    energy_by_mode_wh: dict
    time_by_mode_h: dict
    soc_timeline: list = field(default_factory=list)   # (hours, soc)


def generate_goals(hours: float, seed: int, mean_gap_min: float = 2.5) -> list[tuple[float, str]]:
    """Request arrival times (seconds) with exponential gaps."""
    rng = random.Random(seed)
    goals, t = [], 0.0
    while True:
        t += rng.expovariate(1.0 / (mean_gap_min * 60.0))
        if t >= hours * 3600.0:
            return goals
        goals.append((t, rng.choice(GOAL_POOL)))


def run_shift(hours: float = 12.0, seed: int = 0, cfg: Optional[dict[str, Any]] = None,
              mean_gap_min: float = 2.5) -> ShiftReport:
    cfg = cfg or load_config()
    env = HomeEnvironment()
    robot = SimulatedRobot(cfg, start=env.places["desk"], dock=env.dock)
    agent = HumanisAgent(robot, env, cfg, seed=seed)
    total_s = hours * 3600.0
    timeline: list[tuple[float, float]] = [(0.0, robot.battery.soc)]
    next_snapshot = 900.0
    statuses: Counter = Counter()
    ended = ""

    def snapshot() -> None:
        nonlocal next_snapshot
        while robot.time_s >= next_snapshot:
            timeline.append((next_snapshot / 3600.0, robot.battery.soc))
            next_snapshot += 900.0

    def idle_until(t_end: float) -> bool:
        """Wait for the next request, choosing stand-by or low power to stay on schedule."""
        while robot.time_s < t_end - 1e-9:
            time_fraction = max(0.0, (total_s - robot.time_s) / total_s)
            mode = agent.decision.idle_mode(robot.battery.usable_fraction, time_fraction)
            chunk = min(120.0, t_end - robot.time_s)
            kind = "stand" if mode == "stand" else "rest"
            if not robot.execute(Command(kind, {"duration_s": chunk, "ai_load": 0.1})).ok:
                return False
            snapshot()
        return True

    for arrival_s, text in generate_goals(hours, seed, mean_gap_min):
        if not idle_until(arrival_s):
            ended = "battery reserve reached"
            break
        result = agent.handle_goal(text)
        statuses[result.status] += 1
        snapshot()
        if robot.battery.is_depleted:
            ended = "battery reserve reached"
            break
    if not ended and not idle_until(total_s):
        ended = "battery reserve reached"

    completed = not ended and robot.time_s >= total_s - 1e-6
    drawn = robot.battery.total_drawn_wh
    operated_h = min(robot.time_s, total_s) / 3600.0
    usable_full = robot.battery.capacity_wh * (1.0 - robot.battery.reserve_fraction)
    return ShiftReport(
        hours_target=hours,
        hours_operated=operated_h,
        completed_target=completed,
        ended_reason=ended or "shift completed",
        goals_total=sum(statuses.values()),
        goals_by_status=dict(statuses),
        distance_m=robot.distance_m,
        energy_used_wh=drawn,
        average_power_w=drawn / operated_h if operated_h else 0.0,
        final_soc=robot.battery.soc,
        energy_left_pct=100.0 * robot.battery.usable_energy_wh / usable_full,
        energy_by_mode_wh=dict(robot.energy_by_mode),
        time_by_mode_h={mode: s / 3600.0 for mode, s in robot.time_by_mode.items()},
        soc_timeline=timeline,
    )
