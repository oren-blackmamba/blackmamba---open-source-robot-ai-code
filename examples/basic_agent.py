"""Give the simulated humanoid a few tasks, in Hebrew and English.

    python examples/basic_agent.py

To use a language model as the planner (needs `pip install anthropic` and an
ANTHROPIC_API_KEY), run with:  python examples/basic_agent.py --llm
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai_core.agent import HumanisAgent
from ai_core.llm_brain import AnthropicClient, LLMBrain, RuleBrain
from config.loader import load_config
from control.robot_interface import SimulatedRobot
from simulation.environments.home_environment import HomeEnvironment

GOALS = [
    "תביא לי את הכוס מהמטבח לסלון",
    "bring the toolbox to the bedroom",
    "wave hello",
    "do something",
]


def main() -> None:
    cfg = load_config()
    env = HomeEnvironment()
    robot = SimulatedRobot(cfg, start=env.places["desk"], dock=env.dock)
    agent = HumanisAgent(robot, env, cfg)
    if "--llm" in sys.argv:
        agent.brain = LLMBrain(env, AnthropicClient(), fallback=RuleBrain(env, agent.planner))

    for goal in GOALS:
        result = agent.handle_goal(goal)
        print(f"\n> {goal}")
        print(f"  {result.status}: {result.steps_done}/{result.steps_total} steps, "
              f"{result.duration_s:.0f} s, {result.energy_wh:.2f} Wh")
        if result.clarification:
            print(f"  robot asks: {result.clarification}")

    state = robot.state()
    print(f"\nBattery {state.soc:.1%}, walked {state.distance_m:.0f} m, "
          f"{state.time_s / 60:.1f} min of simulated time.")


if __name__ == "__main__":
    main()
