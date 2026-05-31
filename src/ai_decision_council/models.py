"""Model catalog and model-selection defaults."""

from typing import List

DEFAULT_MODEL_CATALOG: List[str] = [
    "openai/gpt-4o",
    "anthropic/claude-3-5-sonnet",
    "google/gemini-flash-1.5",
    "meta-llama/llama-3-70b-instruct",
    "mistralai/mistral-large",
]

DEFAULT_MODEL_COUNT = 5
MIN_MODELS = 2
MAX_MODELS = 20
