# Safety design

## Layers

1. **AI layer** — may only propose steps from a fixed vocabulary (validated in `llm_brain.py`).
2. **Command validation** — `SafetyMonitor.validate` approves, clamps or rejects every command:
   unknown commands, negative durations, walk speed above the limit (clamped), work below the
   battery reserve, and work when the battery is too hot.
3. **State monitoring** — `SafetyMonitor.check_state` latches the emergency stop on excessive
   tilt or over-temperature.
4. **Emergency stop** — `EmergencyStop` is a latch: while active every command is refused, and
   only a named operator can reset it.
5. **Watchdog** — `RealtimeBridge` triggers the stop if the controller misses its heartbeat or
   raises an exception.
6. **Joint limits** — `ActuatorController` clamps position and speed per joint.

Limits live in `config/robot_config.yaml` under `safety:` and are covered by `tests/test_safety.py`.

## What this is not

This is a **software** safety design for a simulation. Software alone is not safe enough for a
physical humanoid. Before any real actuator moves, the platform needs:

- an independent hardware emergency stop that cuts actuator power without software;
- hardware current and torque limits, thermal protection and a battery management system;
- supervised testing with the robot restrained, then in a controlled area;
- review by professional robotics-safety engineers (for example against ISO 10218 / ISO 13482).

## Privacy

Camera and microphone data must stay on the device by default. If a cloud language model is used
as the brain (`LLMBrain`), only the text request, map vocabulary and battery level are sent — not
sensor data.
