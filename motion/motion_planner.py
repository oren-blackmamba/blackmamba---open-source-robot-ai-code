"""A* path planning on an occupancy grid, with line-of-sight smoothing."""

from __future__ import annotations

import heapq
import math
from typing import Optional

from perception.environment_mapping import OccupancyGrid

_SQRT2 = math.sqrt(2.0)
_NEIGHBOURS = (
    (1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
    (1, 1, _SQRT2), (1, -1, _SQRT2), (-1, 1, _SQRT2), (-1, -1, _SQRT2),
)


def _octile(a: tuple[int, int], b: tuple[int, int]) -> float:
    dx, dy = abs(a[0] - b[0]), abs(a[1] - b[1])
    return (dx + dy) + (_SQRT2 - 2.0) * min(dx, dy)


class MotionPlanner:
    def __init__(self, grid: OccupancyGrid, clearance_m: float = 0.25):
        self.grid = grid
        self.clearance_m = clearance_m

    def plan(self, start: tuple[float, float],
             goal: tuple[float, float]) -> Optional[list[tuple[float, float]]]:
        """Waypoints (metres) from ``start`` to ``goal``, or None if no route exists."""
        grid = self.grid.inflated(self.clearance_m)
        s = grid.world_to_cell(*start)
        g = grid.world_to_cell(*goal)
        if not grid.in_bounds(*s) or grid.is_occupied(*g):
            return None

        best = {s: 0.0}
        came: dict[tuple[int, int], tuple[int, int]] = {}
        closed: set[tuple[int, int]] = set()
        heap = [(_octile(s, g), 0.0, s)]
        while heap:
            _, cost, cur = heapq.heappop(heap)
            if cur in closed:
                continue
            if cur == g:
                break
            closed.add(cur)
            for dc, dr, step in _NEIGHBOURS:
                nxt = (cur[0] + dc, cur[1] + dr)
                if grid.is_occupied(*nxt):
                    continue
                if dc and dr and (grid.is_occupied(cur[0] + dc, cur[1])
                                  or grid.is_occupied(cur[0], cur[1] + dr)):
                    continue  # do not cut corners
                new_cost = cost + step
                if new_cost < best.get(nxt, float("inf")):
                    best[nxt] = new_cost
                    came[nxt] = cur
                    heapq.heappush(heap, (new_cost + _octile(nxt, g), new_cost, nxt))
        else:
            return None

        cells = [g]
        while cells[-1] != s:
            cells.append(came[cells[-1]])
        cells.reverse()

        smoothed: list[tuple[int, int]] = []
        i = 0
        while i < len(cells) - 1:
            j = len(cells) - 1
            while j > i + 1 and not grid.line_free(*cells[i], *cells[j]):
                j -= 1
            smoothed.append(cells[j])
            i = j
        waypoints = [grid.cell_to_world(*cell) for cell in smoothed[:-1]]
        waypoints.append(goal)
        return waypoints

    @staticmethod
    def path_length(start: tuple[float, float], waypoints: list[tuple[float, float]]) -> float:
        total, (x, y) = 0.0, start
        for wx, wy in waypoints:
            total += math.hypot(wx - x, wy - y)
            x, y = wx, wy
        return total
