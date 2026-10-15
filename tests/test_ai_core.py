import json

import pytest

from ai_core.agent import HumanisAgent
from ai_core.decision_engine import DecisionEngine
from ai_core.llm_brain import LLMBrain, RuleBrain
from ai_core.memory import EpisodicMemory
from ai_core.task_planner import Task, parse_goal
from config.loader import load_config
from control.robot_interface import SimulatedRobot
from energy.energy_optimizer import EnergyOptimizer
from simulation.environments.home_environment import HomeEnvironment

CFG = load_config()
ENV = HomeEnvironment()


def make_agent(brain_factory=None):
    env = HomeEnvironment()          # every test gets its own world: objects can be moved
    robot = SimulatedRobot(CFG, start=env.places["desk"], dock=env.dock)
    agent = HumanisAgent(robot, env, CFG)
    if brain_factory:
        agent.brain = brain_factory(agent)
    return robot, agent


class FakeClient:
    def __init__(self, reply=None, error=None):
        self.reply, self.error, self.calls = reply, error, []

    def complete(self, system, user):
        self.calls.append((system, user))
        if self.error:
            raise self.error
        return self.reply


def test_parse_hebrew_and_english_goals():
    he = parse_goal("תביא לי את הכוס מהמטבח לסלון", ENV)
    assert (he.intent, he.obj, he.places) == ("fetch", "cup", ["kitchen", "living_room"])
    en = parse_goal("bring the toolbox to the bedroom", ENV)
    assert (en.intent, en.obj) == ("fetch", "toolbox") and en.places[-1] == "bedroom"
    assert parse_goal("do something", ENV).intent == "unknown"


def test_fetch_goal_is_completed_and_remembered():
    robot, agent = make_agent()
    result = agent.handle_goal("bring me the cup from the kitchen to the living room")
    assert result.status == "completed" and result.steps_done == result.steps_total == 5
    assert agent.memory.last_sighting("cup") is not None
    x, y = agent.env.places["living_room"]
    assert (robot.state().x, robot.state().y) == pytest.approx((x, y), abs=0.01)


def test_unclear_goal_asks_for_clarification_in_the_users_language():
    _, agent = make_agent()
    assert "?" in agent.handle_goal("תעשה משהו").clarification
    english = agent.handle_goal("do something")
    assert english.status == "needs_clarification" and "rephrase" in english.clarification


def test_low_energy_plan_is_deferred_not_attempted():
    robot, agent = make_agent()
    robot.battery.energy_wh = robot.battery.reserve_wh + 2.0
    result = agent.handle_goal("bring the toolbox to the bedroom")
    assert result.status == "deferred_low_energy"
    assert robot.state().distance_m == 0.0


def test_recharging_agent_charges_when_deferring():
    robot, agent = make_agent()
    agent.allow_charging = True
    robot.battery.energy_wh = robot.battery.reserve_wh + 2.6
    assert agent.handle_goal("bring the toolbox to the bedroom").status == "deferred_low_energy"
    assert robot.battery.soc > 0.9


def test_decision_engine_margin():
    engine = DecisionEngine(EnergyOptimizer(), margin_fraction=0.15)
    assert engine.approve(10.0, usable_wh=12.0).approved
    assert not engine.approve(10.0, usable_wh=11.0).approved
    assert engine.idle_mode(usable_fraction=0.9, time_fraction_remaining=0.9) == "stand"
    assert engine.idle_mode(usable_fraction=0.5, time_fraction_remaining=0.9) == "rest"


def test_memory_recall_and_capacity():
    memory = EpisodicMemory(capacity=3)
    memory.add(1.0, "goal", "brought the cup to the kitchen")
    memory.add(2.0, "goal", "waved hello")
    assert memory.recall("cup")[0].time_s == 1.0
    for i in range(5):
        memory.add(3.0 + i, "goal", f"event {i}")
    assert len(memory) == 3


# ---- language-model brain -------------------------------------------------

GOOD_PLAN = {"plan": [
    {"step": "navigate", "target": "kitchen"}, {"step": "scan", "target": "cup"},
    {"step": "grasp", "target": "cup"}, {"step": "navigate", "target": "bedroom"},
    {"step": "release", "target": "cup"}]}


def test_llm_brain_plan_is_executed_through_the_safety_layer():
    client = FakeClient(reply="Sure! " + json.dumps(GOOD_PLAN))
    robot, agent = make_agent(lambda a: LLMBrain(a.env, client))
    result = agent.handle_goal("I am thirsty, put a cup in the bedroom")
    assert result.status == "completed" and result.steps_total == 5
    assert len(client.calls) == 1 and "kitchen" in client.calls[0][0]
    robot.estop.trigger("test")
    assert agent.handle_goal("again").status == "failed"       # E-stop beats the LLM


def test_llm_clarification_is_passed_through():
    client = FakeClient(reply=json.dumps({"clarification": "Which cup?"}))
    _, agent = make_agent(lambda a: LLMBrain(a.env, client))
    result = agent.handle_goal("bring the cup")
    assert result.status == "needs_clarification" and result.clarification == "Which cup?"


@pytest.mark.parametrize("reply", [
    "not json at all",
    json.dumps({"plan": [{"step": "navigate", "target": "moon"}]}),
    json.dumps({"plan": [{"step": "self_destruct"}]}),
    json.dumps({"plan": []}),
    json.dumps({"plan": [{"step": "dock"}] * 50}),
])
def test_invalid_llm_output_is_rejected_and_falls_back_to_rules(reply):
    client = FakeClient(reply=reply)
    brain_holder = {}

    def factory(agent):
        brain_holder["b"] = LLMBrain(agent.env, client, fallback=RuleBrain(agent.env, agent.planner))
        return brain_holder["b"]

    _, agent = make_agent(factory)
    result = agent.handle_goal("go to the kitchen")
    assert result.status == "completed"                         # the rule brain did it
    assert brain_holder["b"].last_error


def test_llm_outage_without_fallback_fails_safely():
    client = FakeClient(error=ConnectionError("offline"))
    robot, agent = make_agent(lambda a: LLMBrain(a.env, client))
    result = agent.handle_goal("go to the kitchen")
    assert result.status == "failed" and robot.state().distance_m == 0.0


# ---- persistent world and dialogue -----------------------------------------

def test_carried_objects_really_move_and_are_found_at_their_new_place():
    robot, agent = make_agent()
    assert agent.handle_goal("bring the cup from the kitchen to the living room").status == "completed"
    assert agent.env.object_place("cup") == "living_room"
    cup = next(o for o in agent.env.world_objects() if o[0] == "cup")
    assert cup[1:] == pytest.approx(agent.env.places["living_room"], abs=0.01)   # where the robot put it
    # the robot now finds the cup in the living room, not in the kitchen
    result = agent.handle_goal("bring the cup to the bedroom")
    assert result.status == "completed" and agent.env.object_place("cup") == "bedroom"


def test_a_failed_task_never_leaves_an_object_stuck_in_the_hand():
    robot, agent = make_agent()
    agent._grasp(Task("grasp", "cup", 8.0))
    assert agent.env.object_place("cup") == "carried"
    agent._drop_if_carrying()
    assert agent.env.object_place("cup") != "carried"
    assert ("cup" in [o[0] for o in agent.env.world_objects()])


def test_where_is_questions_are_answered_in_both_languages_without_moving():
    robot, agent = make_agent()
    en = agent.handle_goal("where is the cup?")
    he = agent.handle_goal("איפה הכוס?")
    assert en.status == he.status == "answered"
    assert "kitchen" in en.message and "במטבח" in he.message
    assert robot.state().distance_m == 0.0


def test_the_robot_knows_what_it_has_moved():
    _, agent = make_agent()
    agent.handle_goal("bring the book to the bedroom")
    assert "bedroom" in agent.handle_goal("where is the book?").message


def test_follow_up_with_a_pronoun_refers_to_the_last_object():
    robot, agent = make_agent()
    agent.handle_goal("where is the toolbox?")
    result = agent.handle_goal("bring it to the living room")
    assert result.status == "completed" and agent.env.object_place("toolbox") == "living_room"
    robot2, agent2 = make_agent()
    agent2.handle_goal("איפה הספר?")
    assert agent2.handle_goal("תביא אותו לחדר שינה").status == "completed"
    assert agent2.env.object_place("book") == "bedroom"


def test_pronoun_without_context_asks_what_to_bring():
    _, agent = make_agent()
    assert agent.handle_goal("bring it to the kitchen").status == "needs_clarification"


def test_battery_and_history_questions():
    _, agent = make_agent()
    agent.handle_goal("wave hello")
    battery = agent.handle_goal("how much battery do you have?")
    assert battery.status == "answered" and "%" in battery.message and "hours" in battery.message
    assert agent.handle_goal("כמה סוללה נשארה?").status == "answered"
    assert "wave hello" in agent.handle_goal("what did you do?").message
    assert agent.handle_goal("thank you").message == "You're welcome!"
    assert agent.handle_goal("go charge the battery").status != "answered"
