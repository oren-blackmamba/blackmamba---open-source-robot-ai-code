"""Pluggable cognitive brain: local Ollama first, with a deterministic offline fallback.

The language model proposes plans; it never controls actuators directly. Plans are
validated here and are still checked by the agent's energy and safety layers.
Ollama is restricted to loopback addresses so this client never sends robot context
to a remote server.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Optional, Protocol
from urllib.parse import urlparse

from ai_core.task_planner import (GRASP_S, RELEASE_S, ParsedGoal, Plan, Task, TaskPlanner,
                                  parse_goal)
from motion.gesture_controller import gesture_duration_s
from ai_core.reasoning import Reasoner

DEFAULT_MODEL = "claude-sonnet-5-5"
DEFAULT_LOCAL_MODEL = "qwen2.5:3b"
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


class OllamaClient:
    """Talk to an Ollama model running locally; never sends requests over the internet."""

    def __init__(self, model: Optional[str] = None, base_url: Optional[str] = None,
                 timeout_s: float = 45.0):
        self.model = model or os.environ.get("HUMANIS_LOCAL_MODEL", DEFAULT_LOCAL_MODEL)
        self.base_url = (base_url or os.environ.get(
            "HUMANIS_OLLAMA_URL", "http://127.0.0.1:11434")).rstrip("/")
        parsed = urlparse(self.base_url)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("HUMANIS Ollama endpoint must be local loopback HTTP only")
        if not self.model or timeout_s <= 0:
            raise ValueError("model must be non-empty and timeout_s must be positive")
        self.timeout_s = timeout_s

    def complete(self, system: str, user: str) -> str:
        payload = json.dumps({
            "model": self.model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "options": {"temperature": 0.2},
        }).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/api/chat", data=payload,
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            raise ConnectionError(f"local Ollama is unavailable: {error}") from error
        message = data.get("message", {})
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise ValueError("local Ollama returned an empty or malformed response")
        return content


class AnthropicClient:
    """Optional remote client. It is not used by the offline default brain."""

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
        return "".join(block.text for block in message.content
                       if getattr(block, "type", "") == "text")


class RuleBrain:
    """Deterministic offline brain: known intents, Hebrew/English parsing and clarification."""

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


SYSTEM_PROMPT = """You are HUMANIS, a careful, socially aware humanoid robot's planning brain.
Understand the user's intent, use the recent conversation only when relevant, and be honest
about what you know. If a request is ambiguous, unsafe, or impossible in this simulated world,
ask one concise clarification question in the user's language rather than guessing.
You do not have human feelings or physical abilities beyond the tools represented below.
Plan only with these steps:
  {"step": "navigate", "target": <place>}
  {"step": "scan", "target": <object>}
  {"step": "grasp", "target": <object>}
  {"step": "release", "target": <object>}
  {"step": "gesture", "target": "wave" | "nod" | "point"}
  {"step": "dock"}
Places: %(places)s
Objects and their current map locations: %(objects)s
To fetch an object, navigate to its known location, scan it, grasp it, navigate to the destination,
then release it. Do not claim to have seen an object unless the plan includes a scan.
Never invent places, objects, sensors, memories, or completed actions. Use at most %(max_steps)d steps.
Reply with JSON only:
  {"plan": [...]} or {"clarification": "one short question"}
"""


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
    """Language-model planner with strict plan validation and an offline fallback."""

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
        recent = context.get("recent_events", [])
        if not isinstance(recent, list):
            recent = []
        user = (f"Request: {goal}\nRobot is at: {context.get('place', 'unknown')}\n"
                f"Battery: {context.get('soc_pct', '?')}% charged\n"
                f"Last discussed object: {context.get('last_object') or 'none'}\n"
                f"Recent memory (observations, not guaranteed current): {recent[-5:]}")
        try:
            raw = self.client.complete(self.system_prompt(), user)
        except Exception as error:
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
        return BrainProposal(source=f"rejected ({error})")

    def validate_steps(self, steps: Any) -> tuple[list[Task], str]:
        """Validate vocabulary, targets, and basic object-handling sequence."""
        if not isinstance(steps, list) or not steps:
            return [], "empty or malformed plan"
        if len(steps) > MAX_STEPS:
            return [], f"plan longer than {MAX_STEPS} steps"
        object_labels = {o.label for o in self.env.objects}
        tasks: list[Task] = []
        scanned: set[str] = set()
        carrying: Optional[str] = None
        for item in steps:
            if not isinstance(item, dict):
                return [], "step is not an object"
            step, target = item.get("step"), item.get("target")
            if step == "navigate" and target in self.env.places:
                tasks.append(Task("navigate", target))
            elif step == "scan" and target in object_labels:
                scanned.add(target)
                tasks.append(Task("scan", target))
            elif step == "grasp" and target in object_labels:
                if carrying is not None:
                    return [], "cannot grasp another object while already carrying one"
                if target not in scanned:
                    return [], f"must scan {target!r} before grasping it"
                carrying = target
                tasks.append(Task("grasp", target, GRASP_S))
            elif step == "release" and target in object_labels:
                if carrying != target:
                    return [], f"cannot release {target!r} unless the robot is carrying it"
                carrying = None
                tasks.append(Task("release", target, RELEASE_S))
            elif step == "gesture" and target in KNOWN_GESTURES:
                tasks.append(Task("gesture", target, gesture_duration_s(target)))
            elif step == "dock" and carrying is None:
                tasks.append(Task("dock", "dock"))
            else:
                return [], f"invalid or unsafe step {item!r}"
        if carrying is not None:
            return [], f"plan ends while still carrying {carrying!r}; add a release step"
        return tasks, ""


def build_default_brain(env, planner: TaskPlanner) -> Brain:
    """Use a local language model when enabled; always retain a no-network rule fallback."""
    fallback = RuleBrain(env, planner)
    mode = os.environ.get("HUMANIS_BRAIN_MODE", "local").strip().lower()
    if mode in {"rules", "offline-rules", "disabled"}:
        return fallback
    if mode in {"local", "auto", "ollama"}:
        try:
            return LLMBrain(env, OllamaClient(), fallback=fallback)
        except (ValueError, RuntimeError):
            return fallback
    # Unknown modes fail closed to the deterministic, network-free implementation.
    return fallback
