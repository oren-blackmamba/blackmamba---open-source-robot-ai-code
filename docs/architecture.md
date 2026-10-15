# Architecture

```
 request ──► BRAIN (rules or LLM) ──► Plan ──► energy check ──► steps
                                                                  │
 AI CORE  (ai_core/)         plans, remembers, decides            ▼
 PERCEPTION (perception/)    camera → detections → map      RobotInterface.execute
 MOTION   (motion/)          A* paths, gait, balance, gestures    │
 ENERGY   (energy/)          battery, power model, runtime plan   ▼
 SAFETY   (safety/)          limits, E-stop, state checks    SafetyMonitor.validate
 CONTROL  (control/)         actuators, watchdog, robot API       │
                                                                  ▼
                                                      SimulatedRobot / real hardware
```

## The rule that shapes everything

**The brain proposes, the body disposes.** The planner — rule-based or a large language model —
only produces a list of steps from a fixed vocabulary. Each step is turned into a `Command` and
sent through `RobotInterface.execute`, where `SafetyMonitor` approves, clamps or rejects it.
Nothing the AI says can skip that check.

## Brain (`ai_core/`)

| Module | Role |
|---|---|
| `agent.py` | `HumanisAgent.handle_goal`: understand → plan → energy check → execute → remember |
| `llm_brain.py` | `Brain` interface, offline `RuleBrain`, and `LLMBrain` for a language model |
| `task_planner.py` | Hebrew/English goal parsing, task decomposition, time and energy estimates |
| `reasoning.py` | Confidence and clarification questions (asks instead of guessing) |
| `decision_engine.py` | Energy-aware approval with a safety margin; stand-by vs. low power pacing |
| `dialogue.py` | Answers questions (where is X, battery, what did you do) and resolves follow-ups ("bring *it*") |
| `memory.py` | Episodic memory, facts and last-seen object positions |

### Using a language model as the brain

`LLMBrain` sends the request, the map vocabulary and the battery level to the model and demands
JSON. The reply is validated: every step must be one of `navigate, scan, grasp, release,
gesture, dock`, with a target that exists on the map, and at most 12 steps. Invalid output, an
outage or a timeout falls back to the offline `RuleBrain`, or fails safely with no motion.
The model name comes from `HUMANIS_LLM_MODEL`.

## Interfaces to implement for new backends

- `control.robot_interface.RobotInterface` — `execute(Command)` and `state()`; a physics
  simulator or real robot goes here, and must keep the safety monitor in front of it.
- `ai_core.llm_brain.Brain` — `propose(goal, context) -> BrainProposal`.
- `ai_core.llm_brain.LLMClient` — `complete(system, user) -> str`; any model provider.

## What is modelled and what is not

The world is persistent: objects the robot carries really move, so later requests and questions
reflect what it did. Gestures use minimum-jerk trajectories (the speed profile of human reaching).

Modelled: time, distance, energy per activity, battery reserve and temperature, collision-free
paths, a linear-inverted-pendulum balance response, keyframed gestures within joint limits.
Not modelled: joint dynamics, contact physics, real sensors and noise beyond simple Gaussian
models, grasp mechanics. See `docs/development_roadmap.md`.
