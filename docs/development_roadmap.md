# Development roadmap

Status as of this commit. "Done" means working code with tests in simulation.

## Phase 1 — Software foundation: done
Module interfaces, agent and task planner (Hebrew/English), pluggable LLM brain, configuration,
81 automated tests, documentation.

## Phase 2 — Perception and simulation: started
Done: simulated camera, detections, occupancy grid, sensor fusion filters, indoor environment.
Done: MuJoCo backend with a human-proportioned body (standing, gestures, push tests, physics-based
power). Next: walking in physics, hands and grasping, URDF import, real camera pipeline.

## Phase 3 — Movement and control: started
Done: A* planner, gait footsteps, linear-inverted-pendulum balance, minimum-jerk gestures (the
profile of human reaching), joint limits.
Next: gait controller in MuJoCo, active balance (stepping / whole-body control; simple ankle and hip
feedback did not help, see docs/mujoco.md), grasp planning, imitation learning.

## Phase 4 — Energy intelligence: started
Done: battery model, per-activity power model, energy-aware planning, runtime projection,
12-hour shift benchmark (modelled).
Next: realistic battery model, measured power data, learned power predictors.

## Phase 5 — Physical integration: not started
Hardware selection, controller interfaces, supervised tests, real power measurements.

## Phase 6 — Extended operation: not started
Measured 12-hour benchmark on hardware, with published raw logs and limitations.
