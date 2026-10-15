"""Human-inspired gestures as minimum-jerk joint trajectories."""

from __future__ import annotations

from dataclasses import dataclass

from control.actuator_controller import ActuatorController
from motion import minimum_jerk

SETTLE_S = 0.5

# Each keyframe is (arrival time in s, {joint: target angle in rad}). A listed joint moves
# from where it was at the previous keyframe to the target, arriving exactly at the keyframe time
# with a minimum-jerk profile. Joints not listed hold their last target.
KEYFRAMES: dict[str, list[tuple[float, dict[str, float]]]] = {
    "wave": [
        (1.4, {"r_shoulder_pitch": -1.8, "r_elbow": -1.2}),
        (2.2, {"r_wrist": 0.6}), (3.0, {"r_wrist": -0.6}),
        (3.8, {"r_wrist": 0.6}), (4.6, {"r_wrist": -0.6}),
        (5.2, {"r_wrist": 0.0}),
        (6.6, {"r_shoulder_pitch": 0.0, "r_elbow": 0.0}),
    ],
    "nod": [
        (0.4, {"neck_pitch": 0.3}), (0.8, {"neck_pitch": -0.1}),
        (1.2, {"neck_pitch": 0.3}), (1.6, {"neck_pitch": 0.0}),
    ],
    "point": [
        (1.2, {"r_shoulder_pitch": -1.2, "r_elbow": -0.1}),
        (2.0, {"r_shoulder_pitch": -1.2}),
        (3.2, {"r_shoulder_pitch": 0.0, "r_elbow": 0.0}),
    ],
}


def gesture_duration_s(name: str) -> float:
    """Time the robot needs to perform a gesture, including settling."""
    if name not in KEYFRAMES:
        raise ValueError(f"Unknown gesture {name!r}; known: {sorted(KEYFRAMES)}")
    return KEYFRAMES[name][-1][0] + SETTLE_S


@dataclass
class GestureResult:
    name: str
    duration_s: float
    max_joint_speed_rad_s: float
    max_jerk_rad_s3: float
    trajectory: list[tuple[float, dict[str, float]]]


class GestureController:
    def __init__(self, actuators: ActuatorController, dt: float = 0.01):
        self.actuators = actuators
        self.dt = dt

    def perform(self, name: str) -> GestureResult:
        end_time = gesture_duration_s(name)

        # Build segments (t_start, t_end, {joint: (from, to)}). A joint starts each segment
        # from its previous target, or from its current position the first time it moves.
        last_target = dict(self.actuators.positions)
        segments: list[tuple[float, float, dict[str, tuple[float, float]]]] = []
        prev_time = 0.0
        for arrival, targets in KEYFRAMES[name]:
            moves = {joint: (last_target.get(joint, 0.0), goal) for joint, goal in targets.items()}
            segments.append((prev_time, arrival, moves))
            last_target.update(targets)
            prev_time = arrival

        desired = dict(self.actuators.positions)
        history: list[dict[str, float]] = [dict(self.actuators.positions)]
        trajectory: list[tuple[float, dict[str, float]]] = []
        steps = int(round(end_time / self.dt))
        for tick in range(1, steps + 1):
            t = tick * self.dt
            for t0, t1, moves in segments:
                if t0 <= t <= t1 + 1e-9:
                    for joint, (x0, x1) in moves.items():
                        desired[joint] = minimum_jerk.position(x0, x1, t1 - t0, t - t0)
            self.actuators.step(desired, self.dt)
            history.append(dict(self.actuators.positions))
            if tick % 5 == 0:
                trajectory.append((round(t, 3), dict(self.actuators.positions)))

        speed, jerk = _motion_stats(history, self.dt)
        return GestureResult(name, end_time, speed, jerk, trajectory)


def _motion_stats(history: list[dict[str, float]], dt: float) -> tuple[float, float]:
    """Peak joint speed and peak jerk from finite differences of the executed motion."""
    peak_speed = peak_jerk = 0.0
    for joint in history[0]:
        series = [frame[joint] for frame in history]
        vel = [(b - a) / dt for a, b in zip(series, series[1:])]
        acc = [(b - a) / dt for a, b in zip(vel, vel[1:])]
        jerk = [(b - a) / dt for a, b in zip(acc, acc[1:])]
        peak_speed = max(peak_speed, max((abs(v) for v in vel), default=0.0))
        peak_jerk = max(peak_jerk, max((abs(j) for j in jerk), default=0.0))
    return peak_speed, peak_jerk
