"""Configuration loader.

Uses PyYAML when it is installed and falls back to a tiny built-in parser that
understands the two-level ``section: key: value`` layout of robot_config.yaml.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

DEFAULT_CONFIG_PATH = Path(__file__).with_name("robot_config.yaml")


def _scalar(text: str) -> Any:
    text = text.strip()
    if text.lower() in ("true", "false"):
        return text.lower() == "true"
    for cast in (int, float):
        try:
            return cast(text)
        except ValueError:
            pass
    return text.strip("'\"")


def _parse_minimal(text: str) -> dict[str, dict[str, Any]]:
    data: dict[str, dict[str, Any]] = {}
    section: dict[str, Any] | None = None
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if not line.startswith((" ", "\t")):
            section = data.setdefault(line.rstrip(":").strip(), {})
        else:
            if section is None:
                raise ValueError(f"Key outside a section: {raw!r}")
            key, _, value = line.strip().partition(":")
            section[key.strip()] = _scalar(value)
    return data


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """Load the robot configuration as a nested dictionary."""
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    text = config_path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore
    except ImportError:
        return _parse_minimal(text)
    return yaml.safe_load(text)
