"""Physics-backend tests. Skipped automatically when MuJoCo is not installed."""

import pytest

pytest.importorskip("mujoco")

from ai_core.agent import HumanisAgent
from config.loader import load_config
from control.robot_interface import Command
from simulation.environments.home_environment import HomeEnvironment
from simulation.mujoco_backend import MuJoCoHumanoid, MuJoCoRobot
from simulation.robot_model.humanoid_model import HumanoidModel
from simulation.robot_model.mjcf import build_mjcf, write_mjcf

CFG = load_config()
REST = {name: 0.0 for name in (j.name for j in HumanoidModel.default().joints)}


def settled(seconds=1.0):
    body = MuJoCoHumanoid()
    for _ in range(int(seconds / body.control_dt)):
        body.step(REST)
    return body


# ---- the body ---------------------------------------------------------------

def test_model_has_human_proportions_and_the_software_joints():
    body = MuJoCoHumanoid()
    assert body.total_mass_kg == pytest.approx(70.0, abs=1.0)
    assert body.model.nu == len(HumanoidModel.default().joints) == 19
    assert body.joint_names == [j.name for j in HumanoidModel.default().joints]
    for limit in HumanoidModel.default().joints:                # same limits as the software model
        lo, hi = body.model.joint(limit.name).range
        assert (lo, hi) == pytest.approx((limit.min_rad, limit.max_rad))
    head = body.model.body("head").id
    assert body.data.xpos[head][2] + 0.24 == pytest.approx(1.74, abs=0.02)    # head top


def test_the_model_can_be_exported_for_the_viewer(tmp_path):
    path = write_mjcf(str(tmp_path / "humanis.xml"))
    assert "<mujoco" in open(path, encoding="utf-8").read() and build_mjcf().count("<position") == 19


def test_robot_stands_upright_with_almost_no_joint_effort():
    body = settled(5.0)
    assert body.tilt_deg < 1.0 and body.pelvis_height_m == pytest.approx(0.93, abs=0.02)
    assert body.step(REST) < 5.0                                 # watts of joint power
    assert abs(body.com_xy[0]) < 0.05 and abs(body.com_xy[1]) < 0.05


# ---- disturbance ------------------------------------------------------------

def test_small_push_is_survived_and_a_large_one_topples_the_robot():
    small = settled().push(impulse_ns=10.0, direction_deg=0.0)
    assert not small.fell and small.max_tilt_deg > 0.5 and small.final_tilt_deg < 3.0
    large = settled().push(impulse_ns=100.0, direction_deg=0.0)
    assert large.fell


def test_physics_is_deterministic():
    a = settled().push(15.0).max_tilt_deg
    b = settled().push(15.0).max_tilt_deg
    assert a == b


# ---- robot interface --------------------------------------------------------

def test_standing_drains_the_battery_through_the_physics_power_model():
    robot = MuJoCoRobot(CFG)
    result = robot.execute(Command("stand", {"duration_s": 30.0, "ai_load": 0.3}))
    assert result.ok and result.duration_s == pytest.approx(30.0, abs=0.02)
    state = robot.state()
    assert 0.0 < result.energy_wh < 2.0 and state.soc < 1.0
    assert sum(robot.energy_by_mode.values()) == pytest.approx(state.total_drawn_wh, rel=1e-6)


@pytest.mark.parametrize("name", ["wave", "nod", "point"])
def test_gestures_run_in_physics_without_falling_and_return_to_rest(name):
    robot = MuJoCoRobot(CFG)
    result = robot.execute(Command("gesture", {"name": name}))
    assert result.ok and not robot.estop.is_active
    assert robot.body.tilt_deg < 5.0
    assert max(abs(v) for v in robot.actuators.positions.values()) < 0.02


def test_holding_an_arm_out_costs_much_more_than_standing_still():
    robot = MuJoCoRobot(CFG)
    standing_w = robot.body.step(REST)
    arm_out = {**REST, "r_shoulder_pitch": -1.5}
    for _ in range(300):
        power_w = robot.body.step(arm_out)
    assert power_w > 20 * max(standing_w, 0.1)


def test_a_fall_latches_the_emergency_stop_and_blocks_later_commands():
    robot = MuJoCoRobot(CFG)
    assert robot.body.push(100.0).fell
    first = robot.execute(Command("stand", {"duration_s": 1.0}))
    assert not first.ok and first.code == "estop" and robot.estop.is_active
    assert robot.execute(Command("gesture", {"name": "wave"})).code == "estop"


def test_unimplemented_abilities_are_refused_not_faked():
    robot = MuJoCoRobot(CFG)
    assert robot.execute(Command("walk", {"to": (2.0, 0.0)})).code == "unsupported"
    assert robot.execute(Command("manipulate", {"duration_s": 2.0})).code == "unsupported"
    assert robot.state().distance_m == 0.0 and robot.battery.soc == pytest.approx(1.0)


def test_safety_monitor_still_stands_in_front_of_the_physics():
    robot = MuJoCoRobot(CFG)
    assert robot.execute(Command("fly", {})).code == "unknown_command"
    robot.battery.energy_wh = robot.battery.reserve_wh + 0.001
    assert robot.execute(Command("gesture", {"name": "wave"})).code == "battery_protect"


def test_the_ai_agent_can_drive_the_physical_body():
    env = HomeEnvironment()
    robot = MuJoCoRobot(CFG, start=env.places["desk"], dock=env.dock)
    agent = HumanisAgent(robot, env, CFG)
    assert agent.handle_goal("wave hello").status == "completed"
    assert agent.handle_goal("where is the cup?").status == "answered"
    walk = agent.handle_goal("go to the kitchen")                 # walking is not implemented yet
    assert walk.status == "failed" and "not implemented" in walk.message
