# Hardware

No physical hardware is supported yet. This folder is reserved for:

- `sensors/` — drivers and calibration for cameras, depth sensors, IMUs
- `actuators/` — motor driver interfaces and joint calibration
- `configuration/` — per-robot parameter files (measured masses, joint limits, battery data)

Before any real actuator is driven, the hardware must have an **independent emergency stop that
cuts actuator power without software**, and the first tests must be supervised with the robot
restrained. See `docs/safety_design.md`.

Every value in `config/robot_config.yaml` is an assumption until it is replaced with a measurement
from this folder.
