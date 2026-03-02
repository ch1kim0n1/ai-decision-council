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

---

## Using Other Providers

By default the council routes through **OpenRouter** (which proxies dozens of models). You can alternatively connect directly to OpenAI, Anthropic, or a local Ollama instance.

### OpenAI Direct

```bash
export LLM_COUNCIL_PROVIDER=openai
export OPENAI_API_KEY="sk-..."
export LLM_COUNCIL_MODELS="gpt-4o,gpt-4o-mini,o1-mini"
```

### Anthropic Direct

```bash
export LLM_COUNCIL_PROVIDER=anthropic
export ANTHROPIC_API_KEY="sk-ant-..."
export LLM_COUNCIL_MODELS="claude-opus-4-5,claude-sonnet-4-5,claude-haiku-3-5"
```

### Ollama (local)

```bash
export LLM_COUNCIL_PROVIDER=ollama
# No API key needed — Ollama runs on localhost
export LLM_COUNCIL_MODELS="llama3.2,mistral,gemma3"
# Optional: point at a different host
export LLM_COUNCIL_API_URL=http://gpu-box:11434/v1/chat/completions
```

### Custom Proxy

Any OpenAI-compatible endpoint works with `openrouter` or `openai` provider + a custom
`LLM_COUNCIL_API_URL`:

```bash
export LLM_COUNCIL_PROVIDER=openai
export LLM_COUNCIL_API_KEY="my-proxy-token"
export LLM_COUNCIL_API_URL="https://my-internal-proxy/v1/chat/completions"
export LLM_COUNCIL_MODELS="my-model-a,my-model-b"
```

### In Python

```python
from ai_decision_council import Council, AnthropicAdapter
from ai_decision_council.config import CouncilConfig

cfg = CouncilConfig(
    api_key="sk-ant-...",
    provider="anthropic",
    models=["claude-opus-4-5", "claude-sonnet-4-5", "claude-haiku-3-5"],
)
council = Council(config=cfg)
print(council.run_sync("What are the tradeoffs of microservices?").final_response)
```

---

## Enabling Structured Logging

```bash
export LLM_COUNCIL_LOG_LEVEL=DEBUG     # DEBUG / INFO / WARNING / ERROR
export LLM_COUNCIL_LOG_JSON=1          # emit newline-delimited JSON logs
```

Or configure programmatically:

```python
from ai_decision_council import configure_logging

configure_logging(level="INFO", json_mode=True)
```

Each pipeline stage emits structured events (`stage1_start`, `model_call_complete`, etc.)
with duration, model name, and error details — ready for ingestion by Datadog, Loki,
CloudWatch, etc.
