"""Local-only language model adapter and default brain factory.

The Ollama client is restricted to loopback. It never sends prompts to a hosted API.
Download the model before disconnecting; inference itself runs on the local machine.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Optional
from urllib.parse import urlparse

from ai_core.llm_brain import Brain, LLMBrain, OllamaClient if False else LLMBrain
