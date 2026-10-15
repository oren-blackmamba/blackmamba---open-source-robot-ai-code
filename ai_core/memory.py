"""Contextual and episodic memory."""

from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass
from typing import Any, Optional

_TOKEN = re.compile(r"\w+", re.UNICODE)


def _tokens(text: str) -> set[str]:
    return {token.lower() for token in _TOKEN.findall(text)}


@dataclass(frozen=True)
class Episode:
    time_s: float
    kind: str
    text: str
    tags: tuple = ()


class EpisodicMemory:
    """Time-ordered events, plus simple facts and last-seen object locations."""

    def __init__(self, capacity: int = 1000):
        self._episodes: deque[Episode] = deque(maxlen=capacity)
        self._facts: dict[str, Any] = {}
        self._sightings: dict[str, tuple[float, float, float]] = {}

    def add(self, time_s: float, kind: str, text: str, tags: tuple = ()) -> Episode:
        episode = Episode(time_s, kind, text, tuple(tags))
        self._episodes.append(episode)
        return episode

    def last(self, n: int = 5) -> list[Episode]:
        return list(self._episodes)[-n:]

    def recall(self, query: str, k: int = 3) -> list[Episode]:
        """Episodes sharing the most words with ``query`` (most recent first on ties)."""
        wanted = _tokens(query)
        scored = []
        for episode in self._episodes:
            overlap = len(wanted & (_tokens(episode.text) | {t.lower() for t in episode.tags}))
            if overlap:
                scored.append((overlap, episode.time_s, episode))
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [episode for _, _, episode in scored[:k]]

    def remember_fact(self, key: str, value: Any) -> None:
        self._facts[key] = value

    def fact(self, key: str, default: Any = None) -> Any:
        return self._facts.get(key, default)

    def remember_sighting(self, label: str, x: float, y: float, time_s: float) -> None:
        self._sightings[label] = (x, y, time_s)

    def last_sighting(self, label: str) -> Optional[tuple[float, float, float]]:
        return self._sightings.get(label)

    def __len__(self) -> int:
        return len(self._episodes)
