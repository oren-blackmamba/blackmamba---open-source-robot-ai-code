"""Physics demo: the HUMANIS body in MuJoCo. Headless, prints measurements.

    pip install mujoco
    python examples/mujoco_demo.py [--export humanis.xml]

With --export the model is written as MJCF; open it in the MuJoCo viewer with
    python -m mujoco.viewer --mjcf=humanis.xml

All body, motor and gain parameters are ASSUMED values, not measurements of real hardware.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.loader import load_config
from control.robot_interface import Command
from simulation.mujoco_backend import MuJoCoHumanoid, MuJoCoRobot
from simulation.robot_model.mjcf import write_mjcf

DIRECTIONS = {"forward": 0, "backward": 180, "left": 90}


def settled() -> MuJoCoHumanoid:
    body = MuJoCoHumanoid()
    for _ in range(100):
        body.step({name: 0.0 for name in body.joint_names})
    return body


def max_survived_impulse(direction_deg: float) -> int:
    best = 0
    for impulse in range(5, 65, 5):
        if settled().push(impulse, direction_deg).fell:
            break
        best = impulse
    return best


def main() -> None:
    if "--export" in sys.argv:
        path = sys.argv[sys.argv.index("--export") + 1]
        print(f"Model written to {write_mjcf(path)}")

    cfg = load_config()
    body = settled()
    print(f"Body: {body.total_mass_kg:.1f} kg, {len(body.joint_names)} joints, "
          f"pelvis at {body.pelvis_height_m:.2f} m, tilt {body.tilt_deg:.2f} deg")
    print(f"Standing joint power (straight legs): {body.step({n: 0.0 for n in body.joint_names}):.2f} W")

    print("\nPush recovery of the passive stiff stance (largest impulse survived, N*s):")
    for name, angle in DIRECTIONS.items():
        print(f"  {name:<9}{max_survived_impulse(angle):>3}")

    print("\nGestures executed in physics:")
    for gesture in ("wave", "nod", "point"):
        robot = MuJoCoRobot(cfg)
        result = robot.execute(Command("gesture", {"name": gesture}))
        print(f"  {gesture:<6}{result.duration_s:5.1f} s  {result.energy_wh:6.3f} Wh  "
              f"tilt at the end: {robot.body.tilt_deg:.2f} deg  e-stop: {robot.estop.is_active}")

    robot = MuJoCoRobot(cfg)
    print("\nWhat the backend refuses to fake:")
    print(f"  walk        -> {robot.execute(Command('walk', {'to': (2.0, 0.0)})).reason}")
    print(f"  manipulate  -> {robot.execute(Command('manipulate', {'duration_s': 2.0})).reason}")


if __name__ == "__main__":
    main()
