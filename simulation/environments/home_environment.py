"""A 24 m x 14 m indoor environment: four areas, doorways, furniture and a charging dock.

          x: 0            10             18            24
  y: 0    +--------------+--------------+-------------+
          |  living room |   kitchen    |  workshop   |
  y: 8    +----door------+-----door-----+----door-----+
          |   bedroom area  .  hallway  .  dock       |
  y: 14   +-------------------------------------------+
"""

from __future__ import annotations

from dataclasses import dataclass

from perception.environment_mapping import OccupancyGrid


@dataclass(frozen=True)
class WorldObject:
    label: str
    place: str
    x: float
    y: float


class HomeEnvironment:
    WIDTH_M = 24.0
    HEIGHT_M = 14.0
    RESOLUTION_M = 0.25

    def __init__(self) -> None:
        self.places: dict[str, tuple[float, float]] = {
            "living_room": (5.0, 4.0),
            "kitchen": (14.0, 4.0),
            "workshop": (21.0, 4.0),
            "bedroom": (4.0, 11.0),
            "hallway": (14.0, 11.0),
            "door": (14.0, 10.0),
            "dock": (22.0, 12.0),
            "desk": (7.0, 2.0),
        }
        self.place_aliases: dict[str, list[str]] = {
            "living_room": ["living room", "living_room", "livingroom", "סלון"],
            "kitchen": ["kitchen", "מטבח"],
            "workshop": ["workshop", "סדנה"],
            "bedroom": ["bedroom", "חדר שינה", "חדר השינה", "שינה"],
            "hallway": ["hallway", "מסדרון"],
            "door": ["door", "entrance", "דלת", "כניסה"],
            "dock": ["dock", "charging station", "עגינה", "מטען", "תחנת טעינה"],
            "desk": ["desk", "שולחן"],
        }
        self.objects: list[WorldObject] = [
            WorldObject("cup", "kitchen", 14.6, 4.4),
            WorldObject("book", "living_room", 5.5, 4.5),
            WorldObject("toolbox", "workshop", 21.6, 4.5),
            WorldObject("medicine_box", "bedroom", 4.6, 11.4),
        ]
        self.object_aliases: dict[str, list[str]] = {
            "cup": ["cup", "mug", "כוס"],
            "book": ["book", "ספר"],
            "toolbox": ["toolbox", "tool box", "ארגז כלים", "ארגז הכלים"],
            "medicine_box": ["medicine box", "medicine", "תרופות", "תרופה"],
        }
        self.dock = self.places["dock"]

    def object_place(self, label: str) -> str | None:
        for item in self.objects:
            if item.label == label:
                return item.place
        return None

    def world_objects(self) -> list[tuple[str, float, float]]:
        return [(item.label, item.x, item.y) for item in self.objects]

    def build_grid(self) -> OccupancyGrid:
        """The robot's map: outer walls, interior walls with doorways, furniture."""
        w, h, t = self.WIDTH_M, self.HEIGHT_M, 0.25
        grid = OccupancyGrid(w, h, self.RESOLUTION_M)
        # outer walls
        for rect in ((0, 0, w, t), (0, h - t, w, h), (0, 0, t, h), (w - t, 0, w, h)):
            grid.add_rect(*rect)
        # vertical walls between the upper rooms (doorway at y = 3.25 .. 4.75)
        for x in (10.0, 18.0):
            grid.add_rect(x, 0, x + t, 3.25)
            grid.add_rect(x, 4.75, x + t, 8.0)
        # horizontal wall at y = 8 with three doorways
        for x0, x1 in ((0, 4.25), (5.75, 13.25), (14.75, 20.25), (21.75, w)):
            grid.add_rect(x0, 8.0, x1, 8.25)
        # furniture
        grid.add_rect(6.0, 5.0, 8.0, 6.0)      # living-room table
        grid.add_rect(11.0, 0.25, 17.5, 1.0)   # kitchen counter
        grid.add_rect(19.0, 6.5, 20.5, 7.5)    # workshop bench
        grid.add_rect(1.0, 12.0, 3.0, 13.7)    # bed
        return grid
