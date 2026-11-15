# HUMANIS Long-Term Learning

## What the system learns

HUMANIS separates three different capabilities:

1. **Local inference** — a downloaded language model runs on the same computer through Ollama. No hosted API is required at runtime.
2. **Long-term memory** — SQLite stores robot episodes and explicit feedback so useful context survives restarts.
3. **Model training** — changing model weights is a separate, deliberate training workflow. HUMANIS does not continuously rewrite its own model weights while controlling a robot.

The first two are supported by this software layer. Online-free operation requires the local model and Ollama to be installed before disconnecting from the internet.

## Enable persistent memory

Set an environment variable before starting HUMANIS:

- Windows PowerShell: `$env:HUMANIS_MEMORY_DB="data/humanis_memory.sqlite3"`
- Linux/macOS: `export HUMANIS_MEMORY_DB="data/humanis_memory.sqlite3"`

If the variable is not set, the existing in-memory behavior is preserved. The database contains episode text, tags, and explicit feedback. Treat it as private robot/user data and protect the file with normal operating-system permissions.

## Provide feedback

Applications can call:

```python
agent.record_feedback(
    goal="bring the cup to the kitchen",
    rating=-1,
    correction="The cup was on the dining table, not in the kitchen.",
)
```

Use rating `1` for helpful behavior and `-1` for incorrect behavior. Relevant feedback is retrieved for later planning prompts. Feedback is advisory context, never permission to perform an unsafe action.

## Important limitations

- Retrieval is lexical and lightweight; it is not yet vector/semantic memory.
- Stored feedback does not automatically change model weights.
- The robot only learns from information it actually observes or from feedback explicitly supplied to it.
- A language model can still make mistakes. Every plan must continue through plan validation, energy checks, and the independent safety layer.
- Do not connect physical actuators until hardware-specific safety controls have been independently validated.

## Offline model

See [offline_brain.md](offline_brain.md) for the local Ollama setup. Download the selected model while connected, then disconnect and verify that the local service and model still work.
