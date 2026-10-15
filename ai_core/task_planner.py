"""Goal parsing (Hebrew and English) and task decomposition."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from energy.energy_optimizer import EnergyOptimizer
from energy.power_estimator import PowerEstimator
from motion.gesture_controller import gesture_duration_s
from motion.motion_planner import MotionPlanner

SCAN_S, GRASP_S, RELEASE_S = 3.0, 8.0, 4.0
DEFAULT_DESTINATION = "desk"

FETCH_WORDS = ["bring", "fetch", "הבא", "תביא", "קח"]
GO_WORDS = ["go to", "walk to", "navigate", "לך", "גש", "סע"]
GESTURE_WORDS = ["wave", "hello", "greet", "נופף", "שלום"]
CHARGE_WORDS = ["charge", "טען", "טעינה"]


def _find(text: str, aliases: list[str]) -> Optional[int]:
    """Index of the earliest alias in ``text``. ASCII aliases match whole words."""
    best: Optional[int] = None
    for alias in aliases:
        if alias.isascii():
            match = re.search(r"\b" + re.escape(alias) + r"\b", text)
            index = match.start() if match else -1
        else:
            index = text.find(alias)
        if index >= 0 and (best is None or index < best):
            best = index
    return best


find_alias = _find


@dataclass
class ParsedGoal:
    intent: str                        # fetch | go | gesture | charge | unknown
    obj: Optional[str] = None
    places: list = field(default_factory=list)   # mentioned places, in order
    gesture: Optional[str] = None


@dataclass(frozen=True)
class Task:
    kind: str                          # navigate | scan | grasp | release | gesture | dock
    target: Optional[str] = None
    duration_s: float = 0.0


@dataclass
class Plan:
    tasks: list
    goal: ParsedGoal


@dataclass(frozen=True)
class PlanEstimate:
    duration_s: float
    energy_wh: float
    distance_m: float


def parse_goal(text: str, env) -> ParsedGoal:
    lowered = text.lower()
    if _find(lowered, FETCH_WORDS) is not None:
        intent = "fetch"
    elif _find(lowered, CHARGE_WORDS) is not None:
        intent = "charge"
    elif _find(lowered, GO_WORDS) is not None:
        intent = "go"
    elif _find(lowered, GESTURE_WORDS) is not None:
        intent = "gesture"
    else:
        intent = "unknown"

    objects = [(i, label) for label, aliases in env.object_aliases.items()
               if (i := _find(lowered, aliases)) is not None]
    places = [(i, name) for name, aliases in env.place_aliases.items()
              if (i := _find(lowered, aliases)) is not None]
    return ParsedGoal(
        intent=intent,
        obj=min(objects)[1] if objects else None,
        places=[name for _, name in sorted(places)],
        gesture="wave" if intent == "gesture" else None,
    )


class TaskPlanner:
    def __init__(self, env, motion: MotionPlanner, estimator: PowerEstimator,
                 optimizer: EnergyOptimizer, max_walk_speed: float):
        self.env = env
        self.motion = motion
        self.estimator = estimator
        self.optimizer = optimizer
        self.max_walk_speed = max_walk_speed

    def plan(self, parsed: ParsedGoal) -> Optional[Plan]:
        if parsed.intent == "fetch" and parsed.obj:
            source = self.env.object_place(parsed.obj)
            others = [p for p in parsed.places if p != source]
            destination = others[-1] if others else DEFAULT_DESTINATION
            tasks = [Task("navigate", source), Task("scan", parsed.obj),
                     Task("grasp", parsed.obj, GRASP_S), Task("navigate", destination),
                     Task("release", parsed.obj, RELEASE_S)]
        elif parsed.intent == "go" and parsed.places:
            tasks = [Task("navigate", parsed.places[-1])]
        elif parsed.intent == "gesture":
            gesture = parsed.gesture or "wave"
            tasks = [Task("gesture", gesture, gesture_duration_s(gesture))]
        elif parsed.intent == "charge":
            tasks = [Task("dock", "dock")]
        else:
            return None
        return Plan(tasks, parsed)

    def estimate(self, plan: Plan, start: tuple[float, float]) -> Optional[PlanEstimate]:
        """Predicted time and energy, or None if a route does not exist."""
        position = start
        duration = energy = distance = 0.0
        for task in plan.tasks:
            if task.kind in ("navigate", "dock"):
                target = self.env.places[task.target]
                path = self.motion.plan(position, target)
                if path is None:
                    return None
                length = self.motion.path_length(position, path)
                speed = self.optimizer.choose_walk_speed(self.estimator, length, self.max_walk_speed)
                duration += length / speed
                energy += self.estimator.walk_energy_wh(length, speed) if length else 0.0
                distance += length
                position = target
            elif task.kind == "scan":
                duration += SCAN_S
                energy += self.estimator.energy_wh("standing", SCAN_S, ai_load=1.0)
            elif task.kind in ("grasp", "release"):
                duration += task.duration_s
                energy += self.estimator.energy_wh("manipulating", task.duration_s)
            elif task.kind == "gesture":
                duration += task.duration_s
                energy += self.estimator.energy_wh("gesture", task.duration_s)
        return PlanEstimate(duration, energy, distance)
