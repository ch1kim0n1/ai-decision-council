"""Model catalog and model-selection defaults."""

from typing import List


DEFAULT_MODEL_CATALOG: List[str] = [
    "openai/gpt-5.1",
    "anthropic/claude-sonnet-4.5",
    "google/gemini-3-pro-preview",
    "x-ai/grok-4",
    "deepseek/deepseek-r1",
]

DEFAULT_MODEL_COUNT = 5
MIN_MODELS = 2
MAX_MODELS = 20
