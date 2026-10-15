import pytest

from config.loader import load_config
from energy.battery_monitor import BatteryMonitor
from energy.energy_optimizer import EnergyOptimizer, PlanOption
from energy.power_estimator import PowerEstimator
from energy.runtime_planner import RuntimePlanner

CFG = load_config()


def make():
    battery = BatteryMonitor.from_config(CFG)
    estimator = PowerEstimator.from_config(CFG)
    return battery, estimator, RuntimePlanner(battery, estimator)


def test_battery_draw_and_reserve():
    battery, _, _ = make()
    assert battery.soc == pytest.approx(1.0)
    wh = battery.draw(300.0, 3600.0)
    assert wh == pytest.approx(300.0)
    assert battery.soc == pytest.approx(0.9)
    battery.draw(1e6, 3600.0)
    assert battery.is_depleted and battery.energy_wh >= 0.0


def test_battery_charge_is_capped():
    battery, _, _ = make()
    battery.draw(600.0, 3600.0)
    battery.charge(10_000.0, 3600.0)
    assert battery.soc == pytest.approx(1.0)


def test_walking_costs_more_than_standing():
    _, estimator, _ = make()
    assert estimator.power_for("walking") > estimator.power_for("standing")
    assert estimator.power_for("low_power") < estimator.power_for("standing")


def test_energy_per_metre_has_an_interior_minimum():
    _, estimator, _ = make()
    best = estimator.most_efficient_speed(max_speed=1.4)
    per_m = lambda v: estimator.walk_energy_wh(100.0, v) / 100.0
    assert per_m(best) <= per_m(0.4)
    assert per_m(best) <= per_m(1.4)


def test_duty_cycle_must_sum_to_one():
    _, _, planner = make()
    with pytest.raises(ValueError):
        planner.average_power_w({"standing": 0.5})


def test_light_workload_fits_12_hours():
    _, _, planner = make()
    duty = {"standing": 0.6, "walking": 0.1, "manipulating": 0.1, "low_power": 0.2}
    assert planner.projected_runtime_h(duty) >= 12.0
    assert planner.fit_duty_cycle(duty, 12.0).feasible


def test_heavy_workload_is_scaled_back_to_fit():
    _, _, planner = make()
    heavy = {"walking": 1.0}
    assert planner.projected_runtime_h(heavy) < 12.0
    fit = planner.fit_duty_cycle(heavy, 12.0)
    assert fit.feasible and 0.0 < fit.useful_fraction < 1.0
    assert planner.projected_runtime_h(fit.duty) == pytest.approx(12.0, rel=1e-3)


def test_optimizer_respects_budget_and_time_value():
    optimizer = EnergyOptimizer(time_weight_wh_per_min=1.0)
    options = [PlanOption("slow", 600, 5.0), PlanOption("fast", 60, 7.0)]
    assert optimizer.choose(options).name == "fast"
    assert optimizer.choose(options, energy_budget_wh=6.0).name == "slow"
    assert optimizer.choose(options, energy_budget_wh=1.0) is None
