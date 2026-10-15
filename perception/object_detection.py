"""Turns raw camera detections into world-coordinate object detections."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from perception.vision import Frame


@dataclass(frozen=True)
class Detection:
    label: str
    x: float
    y: float
    confidence: float
    range_m: float


class ObjectDetector:
    def __init__(self, min_confidence: float = 0.6):
        self.min_confidence = min_confidence

    def detect(self, frame: Frame) -> list[Detection]:
        px, py, heading = frame.pose
        found = []
        for raw in frame.detections:
            if raw.confidence < self.min_confidence:
                continue
            angle = heading + raw.bearing_rad
            found.append(Detection(
                raw.label,
                px + raw.range_m * math.cos(angle),
                py + raw.range_m * math.sin(angle),
                raw.confidence,
                raw.range_m,
            ))
        found.sort(key=lambda d: -d.confidence)
        return found

    def find(self, label: str, frame: Frame) -> Optional[Detection]:
        for detection in self.detect(frame):
            if detection.label == label:
                return detection
        return None
