# Python Integration

Current provider scope is OpenRouter-first. `Council.from_env()` expects
`LLM_COUNCIL_API_KEY` (or legacy `OPENROUTER_API_KEY`) to contain your OpenRouter key.

## Canonical API (`Council`)

```python
from ai_decision_council import Council

council = Council.from_env()
result = council.run_sync("Your prompt")
print(result.final_response)
print(result.to_dict())
```

## Async usage

```python
from ai_decision_council import Council

council = Council.from_env()

async def run():
    result = await council.run("Your prompt")
    return result.final_response
```

## Explicit config

```python
from ai_decision_council import Council, CouncilConfig

config = CouncilConfig.from_env(model_count=7)
council = Council(config=config)
```

## Compatibility API (`CouncilBridge`)

```python
from ai_decision_council import CouncilBridge

bridge = CouncilBridge()
text = bridge.ask_sync("Your prompt")
```

## Packaged FastAPI app

```python
from ai_decision_council import create_fastapi_app

app = create_fastapi_app()
```

For embedded routers, use:

```python
from ai_decision_council.api.fastapi import create_router
```

## Result shape

- `stage1`: per-model first-pass responses
- `stage2`: per-model ranking analyses
- `stage3`: final synthesized output
- `metadata`: label mapping, aggregate ranking, error records
- `errors`: list of structured `ModelRunError`
