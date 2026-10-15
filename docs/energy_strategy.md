# Energy strategy: the 12-hour target

The target is **up to 12 hours of useful operation**. This repository models how the software
manages energy toward that target. It does **not** show that any hardware reaches it.

## Model (`config/robot_config.yaml`)

Total power = mechanical (by activity) + compute (idle→active by AI load) + sensors.
Walking power is `standing + k·v²`, so energy per metre has a minimum at a moderate speed.
A fraction of the pack (10 %) is a protected reserve that is never used for work.

> Every number is an **assumption** (3 kWh pack, 220 W walking, 70 W standing, …) chosen to be
> plausible, not measured. Replace them with measurements before drawing conclusions.

## What the software does

| Mechanism | Module |
|---|---|
| Track charge, protected reserve, temperature | `energy/battery_monitor.py` |
| Estimate power and energy per activity and per walk | `energy/power_estimator.py` |
| Pick walking speed / plan by energy plus value of time | `energy/energy_optimizer.py` |
| Project runtime; scale a workload back until it fits N hours | `energy/runtime_planner.py` |
| Refuse tasks that do not fit the usable energy (with a 15 % margin) | `ai_core/decision_engine.py` |
| Choose stand-by or low power so energy stays on schedule | `DecisionEngine.idle_mode` |
| Never work below the reserve; stop safely | `safety/safety_monitor.py` |

## Reference result (simulation, assumed power model)

`python examples/energy_estimation.py` — a 12 h shift of ~280 requests (fetching, walking,
gestures), seed 0: completed 12 h, about 1.6 kWh used (average ≈ 137 W), ≈ 39 % of the usable
energy left. Continuous walking would last about 9.6 h on the same pack.

The robot spends most of its time standing by (≈ 10.6 h), which is why the average is low. A
workload with more walking and lifting would need a bigger pack, a lower-power design, or
charging breaks — `RuntimePlanner.fit_duty_cycle` quantifies that trade-off.

## What would turn this into a measured result

1. Measure real power per activity on a prototype and update the config.
2. Replace the linear battery with a voltage/resistance/temperature/ageing model.
3. Run the shift benchmark with the real workload and publish the raw logs.
