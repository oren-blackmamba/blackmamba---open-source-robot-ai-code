"""Human-inspired gestures as keyframed joint trajectories."""

from __future__ import annotations

from dataclasses import dataclass

from control.actuator_controller import ActuatorController

KEYFRAMES: dict[str, list[tuple[float, dict[str, float]]]] = {
    "wave": [
        (0.0, {"r_shoulder_pitch": -1.8, "r_elbow": -1.2}),
        (1.0, {"r_wrist": 0.6}), (1.5, {"r_wrist": -0.6}),
        (2.0, {"r_wrist": 0.6}), (2.5, {"r_wrist": -0.6}),
        (3.0, {"r_wrist": 0.0}),
        (3.5, {"r_shoulder_pitch": 0.0, "r_elbow": 0.0}),
    ],
    "nod": [
        (0.0, {"neck_pitch": 0.3}), (0.5, {"neck_pitch": -0.1}),
        (1.0, {"neck_pitch": 0.3}), (1.5, {"neck_pitch": 0.0}),
    ],
    "point": [
        (0.0, {"r_shoulder_pitch": -1.2, "r_elbow": -0.1}),
        (2.0, {"r_shoulder_pitch": 0.0, "r_elbow": 0.0}),
    ],
}


@dataclass
class GestureResult:
    name: str
    duration_s: float
    max_joint_speed_rad_s: float
    trajectory: list[tuple[float, dict[str, float]]]


class GestureController:
    def __init__(self, actuators: ActuatorController, dt: float = 0.02):
        self.actuators = actuators
        self.dt = dt

    def perform(self, name: str) -> GestureResult:
        if name not in KEYFRAMES:
            raise ValueError(f"Unknown gesture {name!r}; known: {sorted(KEYFRAMES)}")
        frames = KEYFRAMES[name]
        end_time = frames[-1][0] + 0.8   # settling time after the last keyframe
        targets: dict[str, float] = {}
        trajectory: list[tuple[float, dict[str, float]]] = []
        max_speed = 0.0
        t, next_frame, tick = 0.0, 0, 0
        while t < end_time:
            while next_frame < len(frames) and frames[next_frame][0] <= t + 1e-9:
                targets.update(frames[next_frame][1])
                next_frame += 1
            before = dict(self.actuators.positions)
            after = self.actuators.step(targets, self.dt)
            for joint, position in after.items():
                max_speed = max(max_speed, abs(position - before[joint]) / self.dt)
            if tick % 5 == 0:
                trajectory.append((round(t, 3), after))
            t += self.dt
            tick += 1
        return GestureResult(name, end_time, max_speed, trajectory)
