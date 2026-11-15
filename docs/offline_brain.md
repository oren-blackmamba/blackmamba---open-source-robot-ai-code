# HUMANIS Offline Brain

HUMANIS can use a local language model through Ollama. The model runs on the same computer as the robot software; this integration does not call a hosted AI API.

## One-time setup

1. Install Ollama for your operating system.
2. While internet is available, download a model, for example:

   ```bash
   ollama pull qwen2.5:3b
   ```

3. Start Ollama and verify that the model responds locally.
4. Disconnect from the internet and run HUMANIS again.

The model download requires internet access. After it is downloaded, local inference does not require internet access. RAM, VRAM, CPU/GPU performance, model size, and quantization affect response speed and quality.

## Configuration

- `HUMANIS_BRAIN_MODE=local` — default; use local Ollama with deterministic rule fallback.
- `HUMANIS_BRAIN_MODE=rules` — no model process and no network requests.
- `HUMANIS_LOCAL_MODEL=qwen2.5:3b` — select an already downloaded local model.
- `HUMANIS_OLLAMA_URL=http://127.0.0.1:11434` — local service address. Only loopback hosts are accepted.

HUMANIS rejects remote Ollama URLs. The optional Anthropic client in `ai_core/llm_brain.py` is a separate remote option and is not used by the default brain factory.

## Safety

The language model proposes a task plan; it never sends motor commands. The plan validator, energy checks, robot interface, and safety monitor remain in the execution path. Keep real actuators disconnected until hardware-specific safety controls are independently validated.

A local language model is not automatically intelligent enough for safe autonomy. Measure task success, hallucinations, latency, resource use, and fallback behavior in simulation.
