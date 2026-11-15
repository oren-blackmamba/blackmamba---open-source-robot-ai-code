import pytest

from ai_core.local_model import OllamaClient, build_default_brain
from ai_core.llm_brain import RuleBrain


def test_ollama_client_rejects_non_loopback_hosts():
    with pytest.raises(ValueError):
        OllamaClient(base_url="https://example.com")


def test_ollama_client_accepts_loopback_host():
    client = OllamaClient(model="local-test", base_url="http://127.0.0.1:11434")
    assert client.model == "local-test"


def test_rules_mode_never_constructs_a_model_client(monkeypatch):
    from simulation.environments.home_environment import HomeEnvironment
    from config.loader import load_config
    from control.robot_interface import SimulatedRobot
    from ai_core.agent import HumanisAgent

    monkeypatch.setenv("HUMANIS_BRAIN_MODE", "rules")
    env = HomeEnvironment()
    robot = SimulatedRobot(load_config(), start=env.places["desk"], dock=env.dock)
    agent = HumanisAgent(robot, env, load_config())
    assert isinstance(agent.brain, RuleBrain)
