"""Central AI orchestration: understand a goal, plan it, check energy, act safely."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from ai_core.decision_engine import DecisionEngine
from ai_core.memory import EpisodicMemory
from ai_core.llm_brain import Brain, RuleBrain
from ai_core.reasoning import Reasoner
from ai_core.task_planner import SCAN_S, Plan, Task, TaskPlanner
from control.robot_interface import Command, CommandResult, RobotInterface
from energy.energy_optimizer import EnergyOptimizer
from energy.power_estimator import PowerEstimator
from motion.motion_planner import MotionPlanner
from perception.object_detection import ObjectDetector
from perception.vision import SimulatedCamera

PLANNING_S = 2.0   # compute time spent understanding and planning each goal


@dataclass
class GoalResult:
    goal: str
    status: str            # completed | failed | needs_clarification | deferred_low_energy
    message: str
    duration_s: float = 0.0
    energy_wh: float = 0.0
    steps_done: int = 0
    steps_total: int = 0
    clarification: Optional[str] = None


class HumanisAgent:
    """Every physical action goes through ``robot.execute`` and therefore the safety layer."""

    def __init__(self, robot: RobotInterface, env, cfg: dict[str, Any],
                 memory: Optional[EpisodicMemory] = None, seed: int = 0,
                 allow_charging: bool = False, brain: Optional[Brain] = None):
        self.robot = robot
        self.env = env
        self.cfg = cfg
        self.estimator = PowerEstimator.from_config(cfg)
        self.optimizer = EnergyOptimizer()
        self.max_walk_speed = float(cfg["safety"]["max_walk_speed_m_s"])
        self.motion = MotionPlanner(env.build_grid())
        self.planner = TaskPlanner(env, self.motion, self.estimator, self.optimizer,
                                   self.max_walk_speed)
        self.reasoner = Reasoner(env)
        self.decision = DecisionEngine(self.optimizer)
        self.memory = memory or EpisodicMemory()
        self.camera = SimulatedCamera(env.world_objects(), seed=seed)
        self.detector = ObjectDetector()
        self.allow_charging = allow_charging
        # The brain only proposes plans. It can be a language model; the safety and
        # energy layers below still check everything it proposes.
        self.brain: Brain = brain or RuleBrain(env, self.planner)

    def _understand(self, goal: str) -> tuple[Optional[Plan], Optional[str]]:
        """Ask the brain for a plan. Returns (plan, clarification question)."""
        state = self.robot.state()
        context = {"place": self._nearest_place(state.x, state.y),
                   "soc_pct": round(100 * state.soc)}
        proposal = self.brain.propose(goal, context)
        self.memory.add(state.time_s, "brain", f"{goal} via {proposal.source or 'brain'}")
        return proposal.plan, proposal.clarification

    def _nearest_place(self, x: float, y: float) -> str:
        return min(self.env.places, key=lambda name: (self.env.places[name][0] - x) ** 2
                   + (self.env.places[name][1] - y) ** 2)

    # -- public ---------------------------------------------------------
    def handle_goal(self, goal: str) -> GoalResult:
        start = self.robot.state()
        thought = self._cmd("stand", duration_s=PLANNING_S, ai_load=1.0)
        if not thought.ok:
            return self._finish(goal, start, "failed", thought.reason)

        plan, clarification = self._understand(goal)
        if clarification:
            return self._finish(goal, start, "needs_clarification",
                                "goal not understood", clarification=clarification)

        estimate = self.planner.estimate(plan, (start.x, start.y)) if plan else None
        if plan is None or estimate is None:
            return self._finish(goal, start, "failed", "no plan or no route")

        approval = self.decision.approve(estimate.energy_wh, self.robot.state().usable_wh)
        if not approval.approved:
            if self.allow_charging:
                self._recharge()
            return self._finish(goal, start, "deferred_low_energy", approval.reason,
                                steps_total=len(plan.tasks))

        done = 0
        for task in plan.tasks:
            ok, reason = self._execute(task)
            if not ok:
                return self._finish(goal, start, "failed", f"{task.kind}: {reason}",
                                    steps_done=done, steps_total=len(plan.tasks))
            done += 1
        return self._finish(goal, start, "completed", "done", steps_done=done,
                            steps_total=len(plan.tasks))

    # -- execution ------------------------------------------------------
    def _cmd(self, kind: str, **params) -> CommandResult:
        return self.robot.execute(Command(kind, params))

    def _execute(self, task: Task) -> tuple[bool, str]:
        if task.kind == "navigate":
            return self._navigate(task.target)
        if task.kind == "scan":
            return self._scan(task.target)
        if task.kind in ("grasp", "release"):
            return self._ok(self._cmd("manipulate", duration_s=task.duration_s))
        if task.kind == "gesture":
            return self._ok(self._cmd("gesture", duration_s=task.duration_s))
        if task.kind == "dock":
            return self._recharge()
        return False, f"unknown task {task.kind}"

    @staticmethod
    def _ok(result: CommandResult) -> tuple[bool, str]:
        return result.ok, result.reason

    def _navigate(self, place: str) -> tuple[bool, str]:
        state = self.robot.state()
        target = self.env.places[place]
        path = self.motion.plan((state.x, state.y), target)
        if path is None:
            return False, f"no route to {place}"
        length = self.motion.path_length((state.x, state.y), path)
        speed = self.optimizer.choose_walk_speed(self.estimator, length, self.max_walk_speed)
        for waypoint in path:
            result = self._cmd("walk", to=waypoint, speed=speed)
            if not result.ok:
                return False, result.reason
        return True, ""

    def _scan(self, label: str) -> tuple[bool, str]:
        for _ in range(2):
            result = self._cmd("stand", duration_s=SCAN_S, ai_load=1.0)
            if not result.ok:
                return False, result.reason
            state = self.robot.state()
            frame = self.camera.capture((state.x, state.y, state.heading), state.time_s, sweep=True)
            detection = self.detector.find(label, frame)
            if detection:
                self.memory.remember_sighting(label, detection.x, detection.y, state.time_s)
                return True, ""
        return False, f"{label} not found"

    def _recharge(self) -> tuple[bool, str]:
        ok, reason = self._navigate("dock")
        if not ok:
            return False, reason
        return self._ok(self._cmd("charge", target_soc=0.95))

    def _finish(self, goal: str, start, status: str, message: str, steps_done: int = 0,
                steps_total: int = 0, clarification: Optional[str] = None) -> GoalResult:
        end = self.robot.state()
        result = GoalResult(goal, status, message, end.time_s - start.time_s,
                            end.total_drawn_wh - start.total_drawn_wh, steps_done, steps_total,
                            clarification)
        self.memory.add(end.time_s, "goal", f"{goal} -> {status}", (status,))
        return result
