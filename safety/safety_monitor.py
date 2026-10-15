"""Validates every command before it reaches the actuators."""

from __future__ import annotations

from dataclasses import dataclass, field

from safety.emergency_stop import EmergencyStop
from safety.operating_limits import OperatingLimits

KNOWN_KINDS = frozenset({"walk", "stand", "manipulate", "gesture", "rest", "charge"})


@dataclass
class SafetyDecision:
    approved: bool
    params: dict = field(default_factory=dict)
    reasons: list = field(default_factory=list)
    code: str = "ok"


class SafetyMonitor:
    def __init__(self, limits: OperatingLimits, estop: EmergencyStop):
        self.limits = limits
        self.estop = estop

    def validate(self, kind: str, params: dict, soc: float, temperature_c: float) -> SafetyDecision:
        """Approve, clamp or reject a command. The AI cannot bypass this check."""
        if self.estop.is_active:
            return SafetyDecision(False, reasons=[f"emergency stop active: {self.estop.reason}"], code="estop")
        if kind not in KNOWN_KINDS:
            return SafetyDecision(False, reasons=[f"unknown command {kind!r}"], code="unknown_command")

        params = dict(params)
        reasons: list[str] = []

        duration = params.get("duration_s")
        if duration is not None and duration < 0:
            return SafetyDecision(False, reasons=["negative duration"], code="limit")

        if kind != "charge" and soc <= self.limits.min_soc_to_work + 1e-6:
            return SafetyDecision(False, reasons=["battery at protected reserve"], code="battery_protect")

        if kind in ("walk", "manipulate", "gesture") and temperature_c >= self.limits.max_battery_temp_c:
            return SafetyDecision(False, reasons=["battery too hot"], code="thermal")

        if kind == "walk":
            speed = float(params.get("speed", 1.0))
            if speed <= 0:
                return SafetyDecision(False, reasons=["walk speed must be positive"], code="limit")
            if speed > self.limits.max_walk_speed_m_s:
                reasons.append(f"walk speed clamped to {self.limits.max_walk_speed_m_s} m/s")
                speed = self.limits.max_walk_speed_m_s
            params["speed"] = speed

        return SafetyDecision(True, params, reasons)

    def check_state(self, tilt_deg: float, soc: float, temperature_c: float) -> bool:
        """Continuous check. Returns False and latches the E-stop on a violation."""
        if abs(tilt_deg) > self.limits.max_tilt_deg:
            self.estop.trigger(f"tilt {tilt_deg:.1f} deg exceeds limit", source="safety_monitor")
            return False
        if temperature_c > self.limits.max_battery_temp_c + 5.0:
            self.estop.trigger(f"battery temperature {temperature_c:.1f} C", source="safety_monitor")
            return False
        return True
