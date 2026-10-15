# Simulation

A lightweight, dependency-free simulation that runs anywhere.

| Path | Contents |
|---|---|
| `robot_model/humanoid_model.py` | 19 joints with position and speed limits, mass and centre-of-mass height |
| `environments/home_environment.py` | 24 m × 14 m indoor map: four areas, doorways, furniture, objects, charging dock |
| `scenarios/work_shift.py` | A full shift of Hebrew/English requests handled on one battery charge |

`control.robot_interface.SimulatedRobot` is the simulated body. It is time- and energy-accurate
*within the power model in `config/robot_config.yaml`*; it does not simulate joint dynamics.

To plug in a physics engine (MuJoCo, Isaac Sim), implement `RobotInterface` and keep the safety
monitor in front of it.
