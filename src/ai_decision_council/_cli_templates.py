"""Template strings used by CLI scaffold commands."""

from __future__ import annotations

ENV_TEMPLATE = """# AI Decision Council runtime configuration
# Core provider key:
LLM_COUNCIL_API_KEY=

# Legacy key name (optional fallback):
# OPENROUTER_API_KEY=

# FastAPI auth token (required when using API module):
LLM_COUNCIL_REFERENCE_API_TOKEN=
# Optional frontend token override:
# VITE_REFERENCE_API_TOKEN=

# Option A: Explicit model list (recommended for full control)
# LLM_COUNCIL_MODELS=openai/gpt-5.1,anthropic/claude-sonnet-4.5,google/gemini-3-pro-preview,x-ai/grok-4,deepseek/deepseek-r1

# Option B: Use curated defaults by count (2-20, default 5)
LLM_COUNCIL_MODEL_COUNT=5

# Optional model overrides:
LLM_COUNCIL_CHAIRMAN_MODEL=openai/gpt-5.1
LLM_COUNCIL_TITLE_MODEL=openai/gpt-5.1

# Provider config (openrouter | openai | anthropic | ollama):
LLM_COUNCIL_PROVIDER=openrouter
LLM_COUNCIL_API_URL=https://openrouter.ai/api/v1/chat/completions
# Provider-specific key env vars (used automatically when PROVIDER is set):
# OPENAI_API_KEY=
# ANTHROPIC_API_KEY=
# OPENROUTER_API_KEY=
# For Ollama no key needed; set LLM_COUNCIL_API_URL=http://localhost:11434/v1/chat/completions

# Observability:
# LLM_COUNCIL_LOG_LEVEL=INFO
# LLM_COUNCIL_LOG_JSON=0

# API routing/cors:
LLM_COUNCIL_API_PREFIX=/v1
# LLM_COUNCIL_CORS_ORIGINS=http://localhost:5173,http://localhost:3000

# Reliability tuning:
LLM_COUNCIL_MAX_RETRIES=2
LLM_COUNCIL_RETRY_BACKOFF_SECONDS=0.5
LLM_COUNCIL_STAGE_TIMEOUT_SECONDS=120
LLM_COUNCIL_TITLE_TIMEOUT_SECONDS=30

# API abuse controls:
LLM_COUNCIL_REFERENCE_RATE_LIMIT_WINDOW_SECONDS=60
LLM_COUNCIL_REFERENCE_RATE_LIMIT_MAX_REQUESTS=8
LLM_COUNCIL_REFERENCE_RATE_LIMIT_MAX_CONCURRENT=2
"""


BRIDGE_TEMPLATE = '''"""Project-local bridge for ai-decision-council integration.

Quickstart:
1) Fill env vars (run `ai-decision-council init` if needed)
2) Verify setup with `ai-decision-council doctor`
3) Call `ask_council(...)` or `run_council(...)` from your app
"""

from ai_decision_council import Council


council = Council.from_env()


async def ask_council(prompt: str) -> str:
    """Return only the final synthesized response."""
    return await council.ask(prompt)


async def run_council(prompt: str) -> dict:
    """Return full structured council output."""
    result = await council.run(prompt)
    return result.to_dict()
'''


FASTAPI_STANDALONE_TEMPLATE = '''"""Standalone FastAPI app using ai-decision-council API module."""

from ai_decision_council.api.fastapi import create_app


app = create_app()
'''


FASTAPI_EMBED_TEMPLATE = '''"""Embedded FastAPI router example for existing applications."""

from fastapi import FastAPI
from ai_decision_council.api.fastapi import APISettings, create_router, FileStorageBackend, StaticTokenAuthBackend, InMemoryRateLimiter
from ai_decision_council import Council


app = FastAPI(title="My Existing App")
settings = APISettings.from_env()
router = create_router(
    settings=settings,
    storage_backend=FileStorageBackend(settings.data_dir),
    rate_limiter=InMemoryRateLimiter(),
    council_factory=Council.from_env,
)
app.include_router(router, prefix=settings.api_prefix)
'''

