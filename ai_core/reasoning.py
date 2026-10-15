"""Reasoning: how well was the goal understood, and what is missing?"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ai_core.task_planner import ParsedGoal


def is_hebrew(text: str) -> bool:
    return any("֐" <= ch <= "׿" for ch in text)


@dataclass
class Assessment:
    confidence: float
    notes: list = field(default_factory=list)
    clarification: Optional[str] = None

    @property
    def understood(self) -> bool:
        return self.clarification is None


class Reasoner:
    """Estimates uncertainty and asks for clarification instead of guessing."""

    def __init__(self, env):
        self.env = env

    def assess(self, parsed: ParsedGoal, goal_text: str) -> Assessment:
        hebrew = is_hebrew(goal_text)

        def ask(he: str, en: str, notes: list[str]) -> Assessment:
            return Assessment(0.2, notes, he if hebrew else en)

        if parsed.intent == "unknown":
            return ask("לא הבנתי מה לעשות. אפשר לנסח מחדש? למשל: ״תביא את הכוס מהמטבח״",
                       "I did not understand the task. Could you rephrase it? "
                       "For example: 'bring the cup from the kitchen'.",
                       ["no recognised intent"])
        if parsed.intent == "fetch" and parsed.obj is None:
            return ask("מה להביא?", "What should I bring?", ["fetch without a known object"])
        if parsed.intent == "go" and not parsed.places:
            return ask("לאן ללכת?", "Where should I go?", ["go without a known place"])

        notes = []
        confidence = 0.95
        if parsed.intent == "fetch" and not any(p != self.env.object_place(parsed.obj)
                                                for p in parsed.places):
            confidence = 0.8
            notes.append("no destination given; defaulting to the desk")
        return Assessment(confidence, notes)
