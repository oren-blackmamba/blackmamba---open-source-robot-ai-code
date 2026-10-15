import pytest

from simulation.scenarios.work_shift import run_shift


@pytest.fixture(scope="module")
def shift():
    return run_shift(hours=12.0, seed=0)


def test_default_shift_lasts_12_hours_with_energy_left(shift):
    assert shift.completed_target and shift.hours_operated == pytest.approx(12.0)
    assert 0.0 < shift.energy_left_pct < 100.0
    assert shift.final_soc >= 0.10


def test_shift_does_real_work(shift):
    assert shift.goals_by_status.get("completed", 0) > 100
    assert shift.distance_m > 1000.0


def test_energy_accounting_is_consistent(shift):
    assert sum(shift.energy_by_mode_wh.values()) == pytest.approx(shift.energy_used_wh, rel=1e-6)
    assert sum(shift.time_by_mode_h.values()) == pytest.approx(shift.hours_operated, rel=1e-3)


def test_shift_is_reproducible():
    a, b = run_shift(2.0, seed=5), run_shift(2.0, seed=5)
    assert a.energy_used_wh == b.energy_used_wh and a.goals_by_status == b.goals_by_status


def test_a_smaller_battery_cannot_make_12_hours():
    from config.loader import load_config
    cfg = load_config()
    cfg["battery"]["capacity_wh"] = 800
    report = run_shift(12.0, seed=0, cfg=cfg)
    assert not report.completed_target and report.ended_reason == "battery reserve reached"
    assert report.final_soc >= cfg["battery"]["reserve_fraction"] - 1e-9
