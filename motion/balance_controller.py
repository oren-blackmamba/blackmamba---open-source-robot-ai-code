"""Balance control on a linear inverted pendulum model with a PD ankle controller."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class BalanceResult:
    fell: bool
    max_tilt_deg: float
    settle_time_s: float
    peak_torque_nm: float


class BalanceController:
    """theta'' = (g / l) * theta + torque / (m * l^2), stabilised by a PD law."""

    def __init__(self, mass_kg: float = 70.0, com_height_m: float = 0.9,
                 kp: float = 900.0, kd: float = 200.0, max_torque_nm: float = 150.0,
                 g: float = 9.81):
        self.mass = mass_kg
        self.length = com_height_m
        self.kp, self.kd = kp, kd
        self.max_torque = max_torque_nm
        self.g = g

    def torque(self, theta: float, omega: float) -> float:
        tau = -(self.kp * theta + self.kd * omega)
        return min(max(tau, -self.max_torque), self.max_torque)

    def simulate_push(self, impulse_ns: float, duration_s: float = 6.0, dt: float = 0.005,
                      max_tilt_deg: float = 25.0) -> BalanceResult:
        """Simulate a horizontal push (N*s) on the upright robot."""
        theta = 0.0
        omega = impulse_ns / (self.mass * self.length)
        limit = math.radians(max_tilt_deg)
        max_tilt = peak_torque = 0.0
        last_unsettled = 0.0
        t = 0.0
        while t < duration_s:
            tau = self.torque(theta, omega)
            alpha = (self.g / self.length) * theta + tau / (self.mass * self.length ** 2)
            omega += alpha * dt
            theta += omega * dt
            t += dt
            max_tilt = max(max_tilt, abs(theta))
            peak_torque = max(peak_torque, abs(tau))
            if abs(theta) > limit:
                return BalanceResult(True, math.degrees(max_tilt), float("inf"), peak_torque)
            if abs(theta) > math.radians(0.5):
                last_unsettled = t
        return BalanceResult(False, math.degrees(max_tilt), last_unsettled, peak_torque)
