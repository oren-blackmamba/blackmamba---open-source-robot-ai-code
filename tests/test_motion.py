import math

import pytest

from config.loader import load_config
from control.actuator_controller import ActuatorController
from energy.power_estimator import PowerEstimator
from motion.balance_controller import BalanceController
from motion.gesture_controller import GestureController
from motion.locomotion import GaitGenerator, Locomotion
from motion.motion_planner import MotionPlanner
from perception.environment_mapping import OccupancyGrid
from simulation.environments.home_environment import HomeEnvironment
from simulation.robot_model.humanoid_model import HumanoidModel

CFG = load_config()


def test_path_avoids_obstacles_and_is_near_optimal():
    grid = OccupancyGrid(10, 10, 0.25)
    grid.add_rect(4.0, 0.0, 5.0, 7.0)          # wall with a gap above y = 7
    planner = MotionPlanner(grid, clearance_m=0.25)
    path = planner.plan((1.0, 1.0), (9.0, 1.0))
    assert path is not None
    inflated = grid.inflated(0.25)
    position = (1.0, 1.0)
    for waypoint in path:                       # every segment must be collision free
        assert inflated.line_free(*inflated.world_to_cell(*position), *inflated.world_to_cell(*waypoint))
        position = waypoint
    straight = 8.0
    length = planner.path_length((1.0, 1.0), path)
    assert length > straight and length < straight + 14.0


def test_no_route_returns_none():
    grid = OccupancyGrid(10, 10, 0.25)
    grid.add_rect(4.0, 0.0, 5.0, 10.0)
    assert MotionPlanner(grid).plan((1.0, 5.0), (9.0, 5.0)) is None


def test_goal_inside_obstacle_returns_none():
    grid = OccupancyGrid(10, 10, 0.25)
    grid.add_rect(4.0, 4.0, 6.0, 6.0)
    assert MotionPlanner(grid).plan((1.0, 1.0), (5.0, 5.0)) is None


def test_every_place_in_the_home_is_reachable():
    env = HomeEnvironment()
    planner = MotionPlanner(env.build_grid())
    names = list(env.places)
    for a in names:
        for b in names:
            if a != b:
                assert planner.plan(env.places[a], env.places[b]) is not None, f"{a} -> {b}"


def test_balance_recovers_from_a_push_but_not_from_a_huge_one():
    controller = BalanceController()
    assert not controller.simulate_push(impulse_ns=30.0).fell
    assert controller.simulate_push(impulse_ns=5000.0).fell
    assert controller.simulate_push(impulse_ns=30.0).max_tilt_deg < 25.0


def test_gait_footsteps_cover_the_distance():
    steps = GaitGenerator().footsteps((0.0, 0.0), (6.0, 0.0), speed=1.0)
    assert steps[-1].x == pytest.approx(6.0)
    assert {s.foot for s in steps} == {"left", "right"}
    assert all(b.time_s > a.time_s for a, b in zip(steps, steps[1:]))


def test_walk_plan_energy_matches_estimator():
    estimator = PowerEstimator.from_config(CFG)
    plan = Locomotion(estimator).plan_walk((0.0, 0.0), [(10.0, 0.0)], speed=1.0)
    assert plan.duration_s == pytest.approx(10.0)
    assert plan.energy_wh == pytest.approx(estimator.walk_energy_wh(10.0, 1.0))


def test_gestures_move_joints_within_limits():
    actuators = ActuatorController(HumanoidModel.default().joint_limits())
    result = GestureController(actuators).perform("wave")
    assert result.max_joint_speed_rad_s <= 3.0 + 1e-9
    assert actuators.positions["r_wrist"] == pytest.approx(0.0, abs=0.05)
    with pytest.raises(ValueError):
        GestureController(actuators).perform("backflip")
