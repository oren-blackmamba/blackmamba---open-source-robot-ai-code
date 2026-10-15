"""Minimum-jerk trajectories.

Human reaching movements closely follow the minimum-jerk profile (Flash & Hogan,
1985): position changes smoothly from start to end with zero velocity and zero
acceleration at both ends, giving the characteristic bell-shaped speed curve.
Robots that move this way look and feel more natural, and are gentler on the
mechanics than constant-speed ramps.
"""

from __future__ import annotations

PEAK_VELOCITY_FACTOR = 1.875   # peak speed = 1.875 * distance / duration


def blend(tau: float) -> float:
    """Normalised position s(tau) = 10 tau^3 - 15 tau^4 + 6 tau^5, for tau in [0, 1]."""
    tau = min(max(tau, 0.0), 1.0)
    return tau ** 3 * (10.0 - 15.0 * tau + 6.0 * tau ** 2)


def position(x0: float, x1: float, duration_s: float, t: float) -> float:
    if duration_s <= 0.0:
        return x1
    return x0 + (x1 - x0) * blend(t / duration_s)


def velocity(x0: float, x1: float, duration_s: float, t: float) -> float:
    if duration_s <= 0.0 or t <= 0.0 or t >= duration_s:
        return 0.0
    tau = t / duration_s
    return (x1 - x0) / duration_s * 30.0 * tau ** 2 * (1.0 - tau) ** 2


def peak_speed(distance: float, duration_s: float) -> float:
    return PEAK_VELOCITY_FACTOR * abs(distance) / duration_s


def min_duration_s(distance: float, max_speed: float) -> float:
    """Shortest duration that keeps the peak speed within ``max_speed``."""
    return PEAK_VELOCITY_FACTOR * abs(distance) / max_speed
