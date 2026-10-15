"""2D occupancy grid used for navigation."""

from __future__ import annotations

import math
from typing import Iterable


class OccupancyGrid:
    def __init__(self, width_m: float, height_m: float, resolution_m: float = 0.25):
        self.resolution_m = resolution_m
        self.cols = int(round(width_m / resolution_m))
        self.rows = int(round(height_m / resolution_m))
        self._occ = [[False] * self.cols for _ in range(self.rows)]
        self._inflated: dict[float, "OccupancyGrid"] = {}

    # -- coordinates ----------------------------------------------------
    def in_bounds(self, col: int, row: int) -> bool:
        return 0 <= col < self.cols and 0 <= row < self.rows

    def world_to_cell(self, x: float, y: float) -> tuple[int, int]:
        return int(x // self.resolution_m), int(y // self.resolution_m)

    def cell_to_world(self, col: int, row: int) -> tuple[float, float]:
        return (col + 0.5) * self.resolution_m, (row + 0.5) * self.resolution_m

    # -- occupancy ------------------------------------------------------
    def is_occupied(self, col: int, row: int) -> bool:
        return (not self.in_bounds(col, row)) or self._occ[row][col]

    def is_free_world(self, x: float, y: float) -> bool:
        return not self.is_occupied(*self.world_to_cell(x, y))

    def add_rect(self, x0: float, y0: float, x1: float, y1: float) -> None:
        """Mark every cell whose centre lies inside the rectangle (metres) as occupied."""
        res = self.resolution_m
        for row in range(self.rows):
            cy = (row + 0.5) * res
            if not y0 <= cy <= y1:
                continue
            for col in range(self.cols):
                if x0 <= (col + 0.5) * res <= x1:
                    self._occ[row][col] = True
        self._inflated.clear()

    def mark_point(self, x: float, y: float, radius_m: float = 0.0) -> None:
        res = self.resolution_m
        reach = int(math.ceil(radius_m / res))
        col0, row0 = self.world_to_cell(x, y)
        for row in range(row0 - reach, row0 + reach + 1):
            for col in range(col0 - reach, col0 + reach + 1):
                if not self.in_bounds(col, row):
                    continue
                cx, cy = self.cell_to_world(col, row)
                if math.hypot(cx - x, cy - y) <= max(radius_m, res / 2):
                    self._occ[row][col] = True
        self._inflated.clear()

    def occupied_count(self) -> int:
        return sum(cell for row in self._occ for cell in row)

    def update_from_detections(self, detections: Iterable, obstacle_labels=("person", "box"),
                               radius_m: float = 0.3) -> int:
        """Mark detected obstacles on the map. Returns how many were added."""
        added = 0
        for detection in detections:
            if detection.label in obstacle_labels:
                self.mark_point(detection.x, detection.y, radius_m)
                added += 1
        return added

    # -- navigation helpers ---------------------------------------------
    def inflated(self, radius_m: float) -> "OccupancyGrid":
        """Copy of the grid with obstacles grown by ``radius_m`` (robot clearance)."""
        key = round(radius_m, 4)
        cached = self._inflated.get(key)
        if cached is not None:
            return cached
        reach = int(math.ceil(radius_m / self.resolution_m - 1e-9)) if radius_m > 0 else 0
        out = OccupancyGrid(self.cols * self.resolution_m, self.rows * self.resolution_m,
                            self.resolution_m)
        for row in range(self.rows):
            for col in range(self.cols):
                if not self._occ[row][col]:
                    continue
                for dr in range(-reach, reach + 1):
                    for dc in range(-reach, reach + 1):
                        if out.in_bounds(col + dc, row + dr):
                            out._occ[row + dr][col + dc] = True
        self._inflated[key] = out
        return out

    def line_free(self, col0: int, row0: int, col1: int, row1: int) -> bool:
        """True if the straight line between two cells crosses no occupied cell.

        The starting cell itself is not checked, so a robot standing close to a
        wall can still plan a way out.
        """
        dc, dr = abs(col1 - col0), abs(row1 - row0)
        step_c = 1 if col0 < col1 else -1
        step_r = 1 if row0 < row1 else -1
        err = dc - dr
        col, row = col0, row0
        while (col, row) != (col1, row1):
            twice = 2 * err
            if twice > -dr:
                err -= dr
                col += step_c
            if twice < dc:
                err += dc
                row += step_r
            if self.is_occupied(col, row):
                return False
        return True
