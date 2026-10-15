"""Run a full simulated work shift and print the energy report.

    python examples/energy_estimation.py [hours] [seed]

All numbers come from the ASSUMED power model in config/robot_config.yaml. They
show how the software manages energy, not how long real hardware would last.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.loader import load_config
from energy.battery_monitor import BatteryMonitor
from energy.power_estimator import PowerEstimator
from energy.runtime_planner import RuntimePlanner
from simulation.scenarios.work_shift import run_shift


def main() -> None:
    hours = float(sys.argv[1]) if len(sys.argv) > 1 else 12.0
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    cfg = load_config()

    report = run_shift(hours, seed, cfg)
    print(f"Shift: {report.hours_operated:.2f} h of {report.hours_target:.0f} h target "
          f"-> {report.ended_reason}")
    print(f"Requests handled: {report.goals_total}  {report.goals_by_status}")
    print(f"Distance walked: {report.distance_m:.0f} m")
    print(f"Energy used: {report.energy_used_wh:.0f} Wh (average {report.average_power_w:.0f} W)")
    print(f"Battery at end: {report.final_soc:.0%}  (usable energy left: {report.energy_left_pct:.0f}%)")
    print("Energy by activity:")
    for mode, wh in sorted(report.energy_by_mode_wh.items(), key=lambda kv: -kv[1]):
        print(f"  {mode:<13}{wh:8.0f} Wh   {report.time_by_mode_h.get(mode, 0):5.2f} h")

    planner = RuntimePlanner(BatteryMonitor.from_config(cfg), PowerEstimator.from_config(cfg))
    print("\nWhat-if: could the battery sustain 12 h of continuous walking?")
    fit = planner.fit_duty_cycle({"walking": 1.0}, 12.0)
    print(f"  continuous walking would last {planner.projected_runtime_h({'walking': 1.0}):.1f} h; "
          f"to reach 12 h only {fit.useful_fraction:.0%} of the time can be spent walking.")


if __name__ == "__main__":
    main()
