"""Simulated camera: produces noisy raw detections of objects in the world."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Sequence


@dataclass(frozen=True)
class RawDetection:
    label: str
    range_m: float
    bearing_rad: float      # relative to the robot's heading
    confidence: float


@dataclass
class Frame:
    timestamp_s: float
    pose: tuple[float, float, float]     # x, y, heading
    detections: list[RawDetection] = field(default_factory=list)


def _wrap(angle: float) -> float:
    return (angle + math.pi) % (2 * math.pi) - math.pi


class SimulatedCamera:
    def __init__(self, world_objects: Sequence[tuple[str, float, float]],
                 fov_deg: float = 90.0, max_range_m: float = 5.0,
                 miss_rate: float = 0.02, seed: int = 0):
        self._objects = list(world_objects)
        self.fov_rad = math.radians(fov_deg)
        self.max_range_m = max_range_m
        self.miss_rate = miss_rate
        self._rng = random.Random(seed)

    def capture(self, pose: tuple[float, float, float], timestamp_s: float = 0.0,
                sweep: bool = False) -> Frame:
        """Capture a frame. ``sweep=True`` simulates turning on the spot (360 degrees)."""
        px, py, heading = pose
        detections: list[RawDetection] = []
        for label, ox, oy in self._objects:
            dx, dy = ox - px, oy - py
            distance = math.hypot(dx, dy)
            if distance > self.max_range_m:
                continue
            bearing = _wrap(math.atan2(dy, dx) - heading)
            if not sweep and abs(bearing) > self.fov_rad / 2:
                continue
            if self._rng.random() < self.miss_rate:
                continue
            confidence = 0.97 - 0.12 * distance / self.max_range_m + self._rng.gauss(0.0, 0.03)
            detections.append(RawDetection(
                label,
                max(0.0, distance + self._rng.gauss(0.0, 0.02)),
                bearing + self._rng.gauss(0.0, 0.01),
                min(1.0, max(0.0, confidence)),
            ))
        return Frame(timestamp_s, pose, detections)
