# 5-Minute Quickstart

## 1) Install

```bash
pip install ai-decision-council
```

## 2) Configure environment

`LLM_COUNCIL_API_KEY` should be your OpenRouter API key.

```bash
export LLM_COUNCIL_API_KEY="..."
export LLM_COUNCIL_MODEL_COUNT=5
```

Legacy fallback key name is also supported:

```bash
export OPENROUTER_API_KEY="..."
```

Optional:

```bash
export LLM_COUNCIL_MODELS="openai/gpt-5.1,anthropic/claude-sonnet-4.5,google/gemini-3-pro-preview,x-ai/grok-4,deepseek/deepseek-r1"
export LLM_COUNCIL_CHAIRMAN_MODEL="openai/gpt-5.1"
export LLM_COUNCIL_TITLE_MODEL="openai/gpt-5.1"
```

## 3) Validate setup

```bash
ai-decision-council doctor
```

## 4) Run one prompt

```bash
ai-decision-council run --prompt "Explain retrieval-augmented generation in 5 bullets"
```

For full JSON output:

```bash
ai-decision-council run --prompt "Explain RAG" --json
```

## 5) Integrate in Python

```python
from ai_decision_council import Council

council = Council.from_env()
result = council.run_sync("Explain vector embeddings simply")
print(result.final_response)
```

## 6) Run Versioned API (`/v1`)

Install API extras once:

```bash
pip install "ai-decision-council[api]"
```

Set required API auth token:

```bash
export LLM_COUNCIL_REFERENCE_API_TOKEN="replace-with-long-random-token"
```

Run hosted API:

```bash
ai-decision-council api serve --host 0.0.0.0 --port 8001
```

Or bootstrap everything in one command:

```bash
ai-decision-council api bootstrap --path .
```

Generate OpenAPI + typed SDK explicitly:

```bash
ai-decision-council api openapi --output ./openapi.json
ai-decision-council api sdk --output-dir ./sdk
```
