"""Pluggable language-model brain.

A large language model (for example Claude) can act as the robot's high-level
reasoner: it turns an open-ended request into a short plan. The model is never
trusted with the body. Its answer must be JSON, every step is checked against a
fixed vocabulary and the known map, and every resulting physical action still
passes through the safety monitor and the energy check.

    brain = LLMBrain(env, client=AnthropicClient())     # needs `pip install anthropic`
    agent = HumanisAgent(robot, env, cfg, brain=brain)

Tests and offline runs use ``RuleBrain`` or a fake client; no network is needed.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Optional, Protocol

from ai_core.task_planner import (GRASP_S, RELEASE_S, ParsedGoal, Plan, Task, TaskPlanner,
                                  parse_goal)
from motion.gesture_controller import gesture_duration_s
from ai_core.reasoning import Reasoner

DEFAULT_MODEL = "claude-sonnet-5-5"
MAX_STEPS = 12
KNOWN_GESTURES = ("wave", "nod", "point")


@dataclass
class BrainProposal:
    plan: Optional[Plan] = None
    clarification: Optional[str] = None
    source: str = ""


class Brain(Protocol):
    def propose(self, goal: str, context: dict[str, Any]) -> BrainProposal: ...


class LLMClient(Protocol):
    def complete(self, system: str, user: str) -> str: ...


class AnthropicClient:
    """Thin wrapper over the Anthropic Messages API (optional dependency)."""

    def __init__(self, model: Optional[str] = None, api_key: Optional[str] = None,
                 max_tokens: int = 800):
        try:
            import anthropic  # type: ignore
        except ImportError as error:
            raise RuntimeError("Install the optional dependency: pip install anthropic") from error
        self._client = anthropic.Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))
        self.model = model or os.environ.get("HUMANIS_LLM_MODEL", DEFAULT_MODEL)
        self.max_tokens = max_tokens

    def complete(self, system: str, user: str) -> str:
        message = self._client.messages.create(
            model=self.model, max_tokens=self.max_tokens, system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(block.text for block in message.content if getattr(block, "type", "") == "text")


class RuleBrain:
    """Offline brain: keyword parsing, Hebrew and English. The default."""

    def __init__(self, env, planner: TaskPlanner):
        self.env = env
        self.planner = planner
        self.reasoner = Reasoner(env)

    def propose(self, goal: str, context: dict[str, Any]) -> BrainProposal:
        parsed = parse_goal(goal, self.env)
        assessment = self.reasoner.assess(parsed, goal)
        if not assessment.understood:
            return BrainProposal(clarification=assessment.clarification, source="rules")
        return BrainProposal(plan=self.planner.plan(parsed), source="rules")


SYSTEM_PROMPT = """You are the planning module of a humanoid robot working in a building.
Turn the user's request into a short plan using ONLY these steps:
  {"step": "navigate", "target": <place>}
  {"step": "scan",     "target": <object>}      look for an object
  {"step": "grasp",    "target": <object>}
  {"step": "release",  "target": <object>}
  {"step": "gesture",  "target": "wave" | "nod" | "point"}
  {"step": "dock"}                              go to the charging dock and charge
Places: %(places)s
Objects (and where they usually are): %(objects)s
To carry an object: navigate to it, scan, grasp, navigate to the destination, release.
Reply with JSON only, no other text:
  {"plan": [ ...steps... ]}                     when the request is clear
  {"clarification": "<one short question>"}     when it is unclear or impossible
Use at most %(max_steps)d steps. Never invent places or objects. Answer in the user's language."""


def _extract_json(text: str) -> Optional[dict]:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        value = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


class LLMBrain:
    """Language-model planner with strict validation and an offline fallback."""

    def __init__(self, env, client: LLMClient, fallback: Optional[Brain] = None):
        self.env = env
        self.client = client
        self.fallback = fallback
        self.last_error = ""

    def system_prompt(self) -> str:
        objects = ", ".join(f"{o.label} ({o.place})" for o in self.env.objects)
        return SYSTEM_PROMPT % {"places": ", ".join(sorted(self.env.places)),
                                "objects": objects, "max_steps": MAX_STEPS}

    def propose(self, goal: str, context: dict[str, Any]) -> BrainProposal:
        user = (f"Request: {goal}\nRobot is at: {context.get('place', 'unknown')}\n"
                f"Battery: {context.get('soc_pct', '?')}% charged")
        try:
            raw = self.client.complete(self.system_prompt(), user)
        except Exception as error:  # network or API failure must never stop the robot
            return self._fallback(goal, context, f"LLM unavailable: {error}")
        data = _extract_json(raw)
        if data is None:
            return self._fallback(goal, context, "LLM reply was not valid JSON")
        if isinstance(data.get("clarification"), str) and data["clarification"].strip():
            return BrainProposal(clarification=data["clarification"].strip(), source="llm")
        tasks, error = self.validate_steps(data.get("plan"))
        if error:
            return self._fallback(goal, context, error)
        return BrainProposal(plan=Plan(tasks, ParsedGoal(intent="llm")), source="llm")

    def _fallback(self, goal: str, context: dict[str, Any], error: str) -> BrainProposal:
        self.last_error = error
        if self.fallback is not None:
            proposal = self.fallback.propose(goal, context)
            proposal.source = f"fallback ({error})"
            return proposal
        return BrainProposal(clarification=None, source=f"rejected ({error})")

    def validate_steps(self, steps: Any) -> tuple[list[Task], str]:
        """Convert model output into Tasks, rejecting anything outside the vocabulary."""
        if not isinstance(steps, list) or not steps:
            return [], "empty or malformed plan"
        if len(steps) > MAX_STEPS:
            return [], f"plan longer than {MAX_STEPS} steps"
        object_labels = {o.label for o in self.env.objects}
        tasks: list[Task] = []
        for item in steps:
            if not isinstance(item, dict):
                return [], "step is not an object"
            step, target = item.get("step"), item.get("target")
            if step == "navigate" and target in self.env.places:
                tasks.append(Task("navigate", target))
            elif step == "scan" and target in object_labels:
                tasks.append(Task("scan", target))
            elif step == "grasp" and target in object_labels:
                tasks.append(Task("grasp", target, GRASP_S))
            elif step == "release" and target in object_labels:
                tasks.append(Task("release", target, RELEASE_S))
            elif step == "gesture" and target in KNOWN_GESTURES:
                tasks.append(Task("gesture", target, gesture_duration_s(target)))
            elif step == "dock":
                tasks.append(Task("dock", "dock"))
            else:
                return [], f"invalid step {item!r}"
        return tasks, ""
