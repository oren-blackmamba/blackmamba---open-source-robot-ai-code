# HUMANIS Offline Cognitive Brain

HUMANIS now supports a local-first planning brain. The model proposes a task plan; it does not
control motors or bypass energy checks, command validation, or the emergency stop.

## Modes

- `HUMANIS_BRAIN_MODE=local` (default): use a local Ollama model if its local service is
  available. If it is missing or unavailable, HUMANIS falls back to the deterministic rule brain.
- `HUMANIS_BRAIN_MODE=rules`: use only the built-in rule brain. No model service, API key, or
  network request is used.
- `HUMANIS_LOCAL_MODEL=qwen2.5:3b`: choose the local model. This is a configurable example,
  not a claim that this model is best for every machine or language.
- `HUMANIS_OLLAMA_URL=http://127.0.0.1:11434`: local Ollama endpoint. The client rejects
  non-loopback hosts to prevent sending robot context to a remote service.

## Run locally

1. Install Ollama and obtain a model while you have connectivity, for example:
   `ollama pull qwen2.5:3b`.
2. Start Ollama on the same computer as HUMANIS.
3. Set `HUMANIS_BRAIN_MODE=local` and run the normal HUMANIS example.
4. Disconnect the computer from the internet and test again. Local inference should continue
   while Ollama and the model are installed locally. If the local model is stopped or unavailable,
   the built-in rules can still handle supported, predefined intents.
5. For a strictly model-free run, set `HUMANIS_BRAIN_MODE=rules`.

The first model download requires connectivity. Running the downloaded model does not require
an internet connection. Performance depends on the model, available RAM/VRAM, and CPU/GPU.

## What “human-like” means here

The implementation adds a local language-model option, a small recent-event context, and
clarification-oriented instructions. It does **not** create human consciousness or general
human-level intelligence. The rule fallback understands only the intents and vocabulary
implemented in the project. Memory currently provides a short context window to the planner;
it is not yet a durable personal memory across restarts.

## Plan validation

Model output is treated as untrusted. The validator rejects unknown steps and targets, requires
an object to be scanned before grasping, prevents grasping a second object while already
carrying one, prevents releasing an object the robot is not carrying, and rejects plans that
end with an object still held. Valid plans still pass through the existing energy and robot
safety layers.

These checks are software safeguards for the current simulation, not certification for physical
robot operation. Keep physical actuators disconnected until hardware-specific controls and tests
have been independently reviewed.
