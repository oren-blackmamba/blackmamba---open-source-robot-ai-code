"""Durable, searchable episodic memory and explicit feedback for HUMANIS.

Memory improves context retrieval; it does not silently fine-tune model weights.
Only validated robot outcomes and explicitly supplied human feedback are stored.
"""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from ai_core.memory import Episode, EpisodicMemory


class PersistentEpisodicMemory(EpisodicMemory):
    """SQLite-backed memory that survives process restarts."""

    def __init__(self, db_path: str, capacity: int = 1000):
        super().__init__(capacity=capacity)
        self.db_path = str(Path(db_path).expanduser())
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.db_path)
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS episodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                time_s REAL NOT NULL,
                kind TEXT NOT NULL,
                text TEXT NOT NULL,
                tags_json TEXT NOT NULL
            )
        """)
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                goal TEXT NOT NULL,
                rating INTEGER NOT NULL CHECK (rating IN (-1, 1)),
                correction TEXT NOT NULL DEFAULT ''
            )
        """)
        self._db.execute("CREATE INDEX IF NOT EXISTS idx_episodes_time ON episodes(time_s)")
        self._db.commit()
        rows = self._db.execute(
            "SELECT time_s, kind, text, tags_json FROM episodes ORDER BY id DESC LIMIT ?",
            (capacity,),
        ).fetchall()
        for time_s, kind, text, tags_json in reversed(rows):
            try:
                tags = tuple(json.loads(tags_json))
            except (TypeError, ValueError):
                tags = ()
            super().add(float(time_s), str(kind), str(text), tags)

    def add(self, time_s: float, kind: str, text: str, tags: tuple = ()) -> Episode:
        episode = super().add(time_s, kind, text, tags)
        self._db.execute(
            "INSERT INTO episodes(time_s, kind, text, tags_json) VALUES (?, ?, ?, ?)",
            (float(time_s), str(kind), str(text), json.dumps(list(tags), ensure_ascii=False)),
        )
        self._db.commit()
        return episode

    def recall(self, query: str, k: int = 3) -> list[Episode]:
        rows = self._db.execute(
            "SELECT time_s, kind, text, tags_json FROM episodes ORDER BY id DESC LIMIT 5000"
        ).fetchall()
        searchable = EpisodicMemory(capacity=max(1, len(rows)))
        for time_s, kind, text, tags_json in reversed(rows):
            try:
                tags = tuple(json.loads(tags_json))
            except (TypeError, ValueError):
                tags = ()
            searchable.add(float(time_s), str(kind), str(text), tags)
        return searchable.recall(query, k)

    def add_feedback(self, goal: str, rating: int, correction: str = "") -> None:
        """Store explicit feedback: rating must be +1 (helpful) or -1 (incorrect)."""
        if rating not in (-1, 1):
            raise ValueError("rating must be -1 or 1")
        if not goal.strip():
            raise ValueError("goal must not be empty")
        self._db.execute(
            "INSERT INTO feedback(goal, rating, correction) VALUES (?, ?, ?)",
            (goal.strip(), rating, correction.strip()),
        )
        self._db.commit()

    def relevant_feedback(self, query: str, k: int = 3) -> list[dict[str, Any]]:
        from ai_core.memory import _tokens

        wanted = _tokens(query)
        rows = self._db.execute(
            "SELECT goal, rating, correction, created_at FROM feedback "
            "ORDER BY id DESC LIMIT 1000"
        ).fetchall()
        scored = []
        for goal, rating, correction, created_at in rows:
            overlap = len(wanted & (_tokens(goal) | _tokens(correction)))
            if overlap:
                scored.append((overlap, created_at, {
                    "goal": goal, "rating": int(rating),
                    "correction": correction, "created_at": created_at,
                }))
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [item[2] for item in scored[:k]]

    def close(self) -> None:
        self._db.close()


def build_default_memory() -> EpisodicMemory:
    """Enable durable memory only when HUMANIS_MEMORY_DB is explicitly configured."""
    path = os.environ.get("HUMANIS_MEMORY_DB", "").strip()
    return PersistentEpisodicMemory(path) if path else EpisodicMemory()
