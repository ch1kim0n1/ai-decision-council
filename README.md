# ai-decision-council

`ai-decision-council` is a plug-and-play Python SDK for multi-model council workflows:

1. Collect first-pass answers from multiple models.
2. Run peer ranking across those answers.
3. Synthesize one final decision-style response.

Default behavior uses a curated set of **5 models** (configurable from 2 to 20).

## Install

```bash
pip install ai-decision-council
```

## 5-minute startup

```bash
# Use your OpenRouter API key here.
export LLM_COUNCIL_API_KEY="..."
ai-decision-council doctor
ai-decision-council run --prompt "Explain CAP theorem in simple terms"
```

## 5-minute API integration

```bash
pip install "ai-decision-council[api]"
export LLM_COUNCIL_API_KEY="..."
export LLM_COUNCIL_REFERENCE_API_TOKEN="replace-with-long-random-token"
ai-decision-council api serve
```

Then call `POST /v1/conversations` on `http://localhost:8001`.

## Python integration

```python
from ai_decision_council import Council

council = Council.from_env()
result = council.run_sync("Summarize vector databases in 5 bullets")
print(result.final_response)
```

## CLI

```bash
ai-decision-council doctor
ai-decision-council models --defaults
ai-decision-council models --defaults --count 7
ai-decision-council init
ai-decision-council init --api fastapi
ai-decision-council api bootstrap --path .
ai-decision-council api openapi --output ./openapi.json
ai-decision-council api sdk --output-dir ./sdk
ai-decision-council run --prompt "Your prompt" --json
```

Legacy alias remains supported:

```bash
llm-council ...
```

## Core configuration

- `LLM_COUNCIL_API_KEY` (preferred; your OpenRouter API key)
- `LLM_COUNCIL_MODELS` (explicit model list)
- `LLM_COUNCIL_MODEL_COUNT` (default 5)
- `LLM_COUNCIL_CHAIRMAN_MODEL`
- `LLM_COUNCIL_TITLE_MODEL`
- `LLM_COUNCIL_API_URL`
- `LLM_COUNCIL_REFERENCE_API_TOKEN` (required for packaged API auth)

Current provider scope is OpenRouter-first. Fallback key support: `OPENROUTER_API_KEY`.

## Documentation

- `docs/quickstart.md`
- `docs/python-integration.md`
- `docs/cli-usage.md`
- `docs/framework-snippets.md`
- `docs/troubleshooting.md`
- `docs/migration.md`
- `docs/openapi.json`
