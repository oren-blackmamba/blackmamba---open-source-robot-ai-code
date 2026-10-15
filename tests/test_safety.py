from config.loader import load_config
from control.actuator_controller import ActuatorController
from control.realtime_bridge import RealtimeBridge
from control.robot_interface import Command, SimulatedRobot
from safety.emergency_stop import EmergencyStop
from safety.operating_limits import OperatingLimits
from safety.safety_monitor import SafetyMonitor
from simulation.robot_model.humanoid_model import HumanoidModel

CFG = load_config()


def monitor():
    estop = EmergencyStop()
    return SafetyMonitor(OperatingLimits.from_config(CFG), estop), estop


def test_walk_speed_is_clamped():
    safety, _ = monitor()
    decision = safety.validate("walk", {"speed": 5.0}, soc=0.8, temperature_c=30)
    assert decision.approved and decision.params["speed"] == 1.4


def test_unknown_and_invalid_commands_are_rejected():
    safety, _ = monitor()
    assert not safety.validate("fly", {}, 0.8, 30).approved
    assert not safety.validate("walk", {"speed": -1.0}, 0.8, 30).approved


def test_battery_reserve_blocks_work_but_not_charging():
    safety, _ = monitor()
    assert safety.validate("walk", {}, soc=0.05, temperature_c=30).code == "battery_protect"
    assert safety.validate("charge", {}, soc=0.05, temperature_c=30).approved


def test_tilt_triggers_latched_estop():
    safety, estop = monitor()
    assert safety.check_state(5.0, 0.8, 30)
    assert not safety.check_state(40.0, 0.8, 30)
    assert estop.is_active
    assert safety.validate("stand", {}, 0.8, 30).code == "estop"


def test_estop_needs_a_named_operator_to_reset():
    estop = EmergencyStop()
    estop.trigger("test")
    assert not estop.reset("")
    assert estop.is_active
    assert estop.reset("oren")
    assert not estop.is_active


def test_robot_refuses_commands_while_estopped():
    robot = SimulatedRobot(CFG)
    robot.estop.trigger("test")
    result = robot.execute(Command("walk", {"to": (1.0, 1.0)}))
    assert not result.ok and result.code == "estop"
    assert robot.state().distance_m == 0.0


def test_robot_stops_at_battery_reserve():
    robot = SimulatedRobot(CFG)
    robot.battery.energy_wh = robot.battery.reserve_wh + 1.0   # 1 Wh of usable energy
    result = robot.execute(Command("stand", {"duration_s": 3600.0}))
    assert not result.ok and result.code == "battery_protect"
    assert robot.battery.usable_energy_wh < 1e-6
    assert robot.battery.soc >= robot.battery.reserve_fraction - 1e-9


def test_actuators_respect_position_and_speed_limits():
    actuators = ActuatorController(HumanoidModel.default().joint_limits())
    positions = actuators.step({"r_knee": 10.0}, dt=0.1)
    assert positions["r_knee"] <= 2.5 * 0.1 + 1e-9          # speed limit
    for _ in range(200):
        positions = actuators.step({"r_knee": 10.0}, dt=0.1)
    assert positions["r_knee"] == 2.4                        # position limit


def test_joint_speeds_stay_within_safety_limit():
    limit = OperatingLimits.from_config(CFG).max_joint_speed_rad_s
    assert all(j.max_speed_rad_s <= limit for j in HumanoidModel.default().joints)


def test_watchdog_triggers_estop():
    bridge = RealtimeBridge(rate_hz=100, watchdog_s=0.05)
    stats = bridge.run(1.0, lambda t, dt: t < 0.2)
    assert stats.estop_triggered and bridge.estop.is_active
    assert RealtimeBridge().run(0.5, lambda t, dt: True).estop_triggered is False


def test_controller_fault_triggers_estop():
    def broken(t, dt):
        raise RuntimeError("boom")
    bridge = RealtimeBridge()
    assert bridge.run(1.0, broken).estop_triggered
