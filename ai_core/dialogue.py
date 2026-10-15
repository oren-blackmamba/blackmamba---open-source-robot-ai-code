"""Conversation: answering questions and understanding follow-ups.

People rarely give complete, isolated commands. They ask "where is the cup?", then say
"bring it to the kitchen". The dialogue manager keeps the thread of the conversation so the
robot can answer from its own knowledge and resolve "it" to the object just discussed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Optional

from ai_core.memory import EpisodicMemory
from ai_core.reasoning import is_hebrew
from ai_core.task_planner import (CHARGE_WORDS, FETCH_WORDS, GO_WORDS, Plan, find_alias)
from energy.power_estimator import PowerEstimator

_EN_PRONOUN = re.compile(r"\b(it|them|that one|this one)\b", re.IGNORECASE)
_HE_PRONOUNS = ("אותו", "אותה", "אותם", "אותן", "את זה", "את זאת")
WHERE_WORDS = ["where is", "where are", "where's", "איפה", "היכן", "מיקום"]
BATTERY_WORDS = ["battery", "סוללה", "בטרייה", "אנרגיה", "how long can you", "כמה זמן אתה יכול"]
HISTORY_WORDS = ["what did you do", "what have you done", "מה עשית", "מה עשית לאחרונה"]
THANKS_WORDS = ["thank", "thanks", "תודה"]
ACTION_WORDS = FETCH_WORDS + GO_WORDS + CHARGE_WORDS


@dataclass
class Turn:
    obj: Optional[str] = None
    place: Optional[str] = None


class DialogueManager:
    def __init__(self, env, memory: EpisodicMemory, estimator: PowerEstimator,
                 state_fn: Callable):
        self.env = env
        self.memory = memory
        self.estimator = estimator
        self.state_fn = state_fn          # returns the robot's current RobotState
        self.last = Turn()

    # -- follow-ups -----------------------------------------------------
    def resolve(self, goal: str) -> str:
        """Replace a pronoun by the object discussed last, e.g. 'bring it to the kitchen'."""
        if self.last.obj is None or self._mentions_object(goal):
            return goal
        if _EN_PRONOUN.search(goal) or any(p in goal for p in _HE_PRONOUNS):
            aliases = self.env.object_aliases[self.last.obj]
            name = aliases[0] if not is_hebrew(goal) else self.env.local_name(self.last.obj, True)
            if _EN_PRONOUN.search(goal) and not is_hebrew(goal):
                return _EN_PRONOUN.sub(f"the {name}", goal, count=1)
            return f"{goal} {name}"
        return goal

    def _mentions_object(self, text: str) -> bool:
        lowered = text.lower()
        return any(find_alias(lowered, a) is not None for a in self.env.object_aliases.values())

    def remember_turn(self, plan: Optional[Plan], goal: str) -> None:
        """Remember what the conversation was about, from the plan or the question asked."""
        if plan is not None:
            for task in plan.tasks:
                if task.kind in ("scan", "grasp", "release") and task.target:
                    self.last.obj = task.target
            places = [t.target for t in plan.tasks if t.kind == "navigate" and t.target]
            if places:
                self.last.place = places[-1]

    # -- questions ------------------------------------------------------
    def answer(self, goal: str) -> Optional[str]:
        """An answer if ``goal`` is a question the robot can answer from its own state."""
        text = goal.lower()
        he = is_hebrew(goal)
        if find_alias(text, THANKS_WORDS) is not None and len(text.split()) <= 4:
            return "בכיף!" if he else "You're welcome!"
        if find_alias(text, WHERE_WORDS) is not None:
            return self._where(text, he)
        if find_alias(text, HISTORY_WORDS) is not None:
            return self._history(he)
        if (find_alias(text, BATTERY_WORDS) is not None
                and find_alias(text, ACTION_WORDS) is None):
            return self._battery(he)
        return None

    def _where(self, text: str, he: bool) -> str:
        found = [(i, label) for label, aliases in self.env.object_aliases.items()
                 if (i := find_alias(text, aliases)) is not None]
        if not found and self.last.obj and (_EN_PRONOUN.search(text) or any(p in text for p in _HE_PRONOUNS)):
            found = [(0, self.last.obj)]
        if not found:
            return "על איזה חפץ אתה שואל?" if he else "Which object do you mean?"
        label = min(found)[1]
        self.last.obj = label                    # so that 'bring it' means this object
        place = self.env.object_place(label)
        seen = self.memory.last_sighting(label)
        if place == "carried":
            return (f"אני מחזיק את {self.env.local_name(label, True)} עכשיו." if he
                    else f"I am carrying the {label} right now.")
        if seen is None:
            note_he, note_en = " (לא ראיתי אותו בעצמי עדיין, זה לפי המפה שלי)", " (from my map; I have not seen it myself yet)"
        else:
            note_he = note_en = ""
        if he:
            return f"המיקום של {self.env.local_name(label, True)}: ב{self.env.local_name(place)}{note_he}."
        return f"The {label} is in the {place.replace('_', ' ')}{note_en}."

    def _battery(self, he: bool) -> str:
        state = self.state_fn()
        average = (state.total_drawn_wh / (state.time_s / 3600.0) if state.time_s > 300
                   else self.estimator.power_for("standing", ai_load=0.3))
        hours = state.usable_wh / average
        if he:
            return f"הסוללה על {state.soc:.0%}. בקצב הנוכחי זה מספיק לעוד כ-{hours:.1f} שעות עבודה."
        return f"Battery at {state.soc:.0%}. At my current pace that is about {hours:.1f} more hours of work."

    def _history(self, he: bool) -> str:
        goals = [e for e in self.memory.last(30) if e.kind == "goal"][-3:]
        if not goals:
            return "עוד לא עשיתי כלום." if he else "I have not done anything yet."
        lines = "; ".join(e.text for e in goals)
        return f"לאחרונה: {lines}" if he else f"Recently: {lines}"
