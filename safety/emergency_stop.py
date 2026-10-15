"""Software emergency stop.

This is a software latch for the simulation. On real hardware it must be backed
by an independent hardware E-stop that cuts actuator power without software.
"""

from __future__ import annotations


class EmergencyStop:
    def __init__(self) -> None:
        self._active = False
        self._reason = ""
        self.history: list[tuple[str, str, str]] = []

    @property
    def is_active(self) -> bool:
        return self._active

    @property
    def reason(self) -> str:
        return self._reason

    def trigger(self, reason: str, source: str = "software") -> None:
        self._active = True
        self._reason = reason
        self.history.append(("trigger", reason, source))

    def reset(self, operator: str) -> bool:
        """Release the stop. Only a named operator may do this."""
        if not operator or not operator.strip():
            return False
        self._active = False
        self._reason = ""
        self.history.append(("reset", "", operator.strip()))
        return True
