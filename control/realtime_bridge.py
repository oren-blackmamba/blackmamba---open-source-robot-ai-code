"""Fixed-rate control loop with a watchdog (simulated time, no sleeping)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from safety.emergency_stop import EmergencyStop


@dataclass
class BridgeStats:
    ticks: int
    estop_triggered: bool
    reason: str = ""


class RealtimeBridge:
    """Runs a control step at ``rate_hz`` and latches the E-stop if it misbehaves.

    The step function returns True when healthy and False when it missed its
    heartbeat. If it stays unhealthy for ``watchdog_s`` or raises an exception,
    the bridge triggers the emergency stop.
    """

    def __init__(self, rate_hz: float = 100.0, watchdog_s: float = 0.05,
                 estop: Optional[EmergencyStop] = None):
        self.dt = 1.0 / rate_hz
        self.watchdog_s = watchdog_s
        self.estop = estop or EmergencyStop()

    def run(self, duration_s: float, step: Callable[[float, float], bool]) -> BridgeStats:
        ticks = 0
        missed_s = 0.0
        t = 0.0
        while t < duration_s - 1e-12:
            try:
                healthy = step(t, self.dt)
            except Exception as error:  # a controller fault must stop the robot
                reason = f"controller fault: {error}"
                self.estop.trigger(reason, source="realtime_bridge")
                return BridgeStats(ticks, True, reason)
            ticks += 1
            missed_s = 0.0 if healthy else missed_s + self.dt
            if missed_s >= self.watchdog_s:
                reason = "watchdog timeout"
                self.estop.trigger(reason, source="realtime_bridge")
                return BridgeStats(ticks, True, reason)
            t += self.dt
        return BridgeStats(ticks, False)
