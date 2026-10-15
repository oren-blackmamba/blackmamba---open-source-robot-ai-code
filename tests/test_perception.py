import math

import pytest

from perception.environment_mapping import OccupancyGrid
from perception.object_detection import ObjectDetector
from perception.sensor_fusion import ComplementaryFilter, Kalman1D
from perception.vision import SimulatedCamera
from simulation.environments.home_environment import HomeEnvironment


def test_camera_sees_object_in_front_and_not_behind():
    camera = SimulatedCamera([("cup", 3.0, 0.0)], miss_rate=0.0)
    assert len(camera.capture((0.0, 0.0, 0.0)).detections) == 1
    assert camera.capture((0.0, 0.0, math.pi)).detections == []
    assert len(camera.capture((0.0, 0.0, math.pi), sweep=True).detections) == 1


def test_camera_range_limit():
    camera = SimulatedCamera([("cup", 20.0, 0.0)], miss_rate=0.0)
    assert camera.capture((0.0, 0.0, 0.0)).detections == []


def test_detector_recovers_world_position():
    camera = SimulatedCamera([("cup", 3.0, 2.0)], miss_rate=0.0, seed=1)
    frame = camera.capture((1.0, 1.0, 0.3), sweep=True)
    cup = ObjectDetector().find("cup", frame)
    assert cup is not None
    assert (cup.x, cup.y) == pytest.approx((3.0, 2.0), abs=0.15)


def test_occupancy_grid_and_inflation():
    grid = OccupancyGrid(10, 10, 0.5)
    grid.add_rect(4.0, 4.0, 5.0, 5.0)
    assert not grid.is_free_world(4.5, 4.5)
    assert grid.is_free_world(2.0, 2.0)
    assert grid.inflated(0.5).occupied_count() > grid.occupied_count()
    assert not grid.line_free(*grid.world_to_cell(1.0, 4.5), *grid.world_to_cell(8.0, 4.5))


def test_detections_update_the_map():
    grid = OccupancyGrid(10, 10, 0.25)
    camera = SimulatedCamera([("person", 3.0, 3.0)], miss_rate=0.0)
    detections = ObjectDetector().detect(camera.capture((1.0, 3.0, 0.0)))
    assert grid.update_from_detections(detections) == 1
    assert not grid.is_free_world(3.0, 3.0)


def test_home_environment_is_consistent():
    env = HomeEnvironment()
    grid = env.build_grid()
    for name, (x, y) in env.places.items():
        assert grid.is_free_world(x, y), f"{name} is inside an obstacle"
    for item in env.objects:
        assert grid.is_free_world(item.x, item.y), f"{item.label} is inside an obstacle"


def test_kalman_reduces_noise():
    import random
    rng = random.Random(3)
    filt = Kalman1D(x0=0.0, p0=1.0, q=1e-4, r=0.25)
    for _ in range(200):
        filt.predict()
        estimate = filt.update(5.0 + rng.gauss(0, 0.5))
    assert abs(estimate - 5.0) < 0.2 and filt.variance < 0.25


def test_complementary_filter_rejects_gyro_drift():
    filt = ComplementaryFilter()
    for _ in range(2000):
        angle = filt.update(gyro_rate_rad_s=0.01, accel_angle_rad=0.0, dt=0.01)  # biased gyro
    assert abs(angle) < 0.02
