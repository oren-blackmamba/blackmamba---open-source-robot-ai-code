# MuJoCo physics backend

`simulation/mujoco_backend.py` runs the HUMANIS body in [MuJoCo](https://mujoco.org) rigid-body
physics. Install with `pip install -e ".[mujoco]"` and run `python examples/mujoco_demo.py`.

## What is real physics

- A 70 kg, 1.75 m human-proportioned body with 19 torque-limited, position-controlled joints
  (`simulation/robot_model/mjcf.py`). The joint names and limits come from the same
  `HumanoidModel` the rest of HUMANIS uses, so poses and gestures are interchangeable.
- Contact and friction with the floor, gravity, balance under pushes.
- Electrical power from the simulated joint torques and speeds
  (mechanical power / efficiency + copper loss `(torque / Km)^2`), feeding the battery model.
- `MuJoCoRobot` implements the same `RobotInterface` as the lightweight simulation, so the AI
  agent, the safety monitor, the emergency stop and the battery all work unchanged. A fall
  (torso tilt above the limit) latches the emergency stop.

## Measured in this simulation (assumed body and motor parameters)

| Quantity | Result |
|---|---|
| Body mass / head height | 70.4 kg / 1.74 m |
| Joint power, standing straight-legged | about 1-2 W |
| Largest push survived by the passive stiff stance | forward 25 N·s, backward 10 N·s, sideways 25 N·s |
| Wave / nod / point (physics, whole robot) | 0.63 / 0.08 / 0.31 Wh; no fall |
| Holding an arm out straight | more than 20x the joint power of standing still |

These are numbers from a model with assumed parameters. They are useful for comparing designs
and finding problems, not as predictions for real hardware.

## What the physics says about the energy assumptions

- Static standing with straight legs needs almost no joint power. The 70 W "standing" figure in
  `config/robot_config.yaml` is therefore not explained by this model: it must come from things
  not modelled here (bent-knee posture, driver and controller losses) or be too high. It needs a
  measurement on hardware.
- Holding an arm out is expensive because copper loss grows with the square of torque. Gestures
  that keep the arm close to the body cost much less than the flat 100 W gesture assumption.

## What is NOT implemented

- **Walking.** `MuJoCoRobot` refuses `walk` with `unsupported` instead of faking it. A gait
  controller is the biggest open task.
- **Grasping and carrying.** `manipulate` is refused. Hands and a contact model are needed.
- **Active balance.** Two simple feedback strategies were tried (ankle and hip) and did *not*
  improve push recovery over the passive stiff stance, so none is included. The ankle torque is
  limited by the foot size, so real recovery needs stepping or whole-body control (for example
  capture-point stepping or a whole-body QP). This is a good first research contribution.
- Self-collision is disabled, and the body is rigid with no actuator dynamics beyond the PD law.
- The viewer and rendering were not tested in the cloud environment that built this. Export the
  model with `--export humanis.xml` and open it with `python -m mujoco.viewer --mjcf=humanis.xml`.

## Using the backend

```python
from config.loader import load_config
from control.robot_interface import Command
from simulation.mujoco_backend import MuJoCoRobot

robot = MuJoCoRobot(load_config())
robot.execute(Command("gesture", {"name": "wave"}))     # runs in physics, through the safety monitor
print(robot.state().soc, robot.body.tilt_deg)
push = robot.body.push(impulse_ns=15.0, direction_deg=0.0)
```
