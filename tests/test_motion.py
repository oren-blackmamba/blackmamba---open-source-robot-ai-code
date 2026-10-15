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


# ---- minimum-jerk motion ----------------------------------------------------

from motion import minimum_jerk as mj
from motion.gesture_controller import KEYFRAMES, _motion_stats, gesture_duration_s


def test_minimum_jerk_profile_is_smooth_and_has_the_known_peak():
    assert mj.position(0.0, 2.0, 1.0, 0.0) == 0.0
    assert mj.position(0.0, 2.0, 1.0, 1.0) == pytest.approx(2.0)
    assert mj.position(0.0, 2.0, 1.0, 0.5) == pytest.approx(1.0)
    assert mj.velocity(0.0, 2.0, 1.0, 0.0) == 0.0 and mj.velocity(0.0, 2.0, 1.0, 1.0) == 0.0
    assert mj.velocity(0.0, 2.0, 1.0, 0.5) == pytest.approx(mj.peak_speed(2.0, 1.0))
    assert mj.min_duration_s(1.8, 2.5) == pytest.approx(1.8 * 1.875 / 2.5)


@pytest.mark.parametrize("name", sorted(KEYFRAMES))
def test_every_gesture_returns_to_rest_within_joint_limits(name):
    model = HumanoidModel.default()
    actuators = ActuatorController(model.joint_limits())
    result = GestureController(actuators).perform(name)
    assert all(abs(p) < 0.02 for p in actuators.positions.values())
    assert result.duration_s == pytest.approx(gesture_duration_s(name))
    for joint, limit in actuators.limits.items():
        assert limit.min_rad <= actuators.positions[joint] <= limit.max_rad
    assert result.max_joint_speed_rad_s <= 3.0 + 1e-6


def test_gestures_are_far_smoother_than_a_constant_speed_ramp():
    actuators = ActuatorController(HumanoidModel.default().joint_limits())
    smooth = GestureController(actuators).perform("wave").max_jerk_rad_s3
    ramp_actuators = ActuatorController(HumanoidModel.default().joint_limits())
    history = [dict(ramp_actuators.positions)]
    for _ in range(300):                       # same joint, abrupt full-speed slew
        history.append(dict(ramp_actuators.step({"r_shoulder_pitch": -1.8}, 0.01)))
    _, ramp_jerk = _motion_stats(history, 0.01)
    assert smooth < ramp_jerk / 20
