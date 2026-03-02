# Migration Guide

## Package and command name

Current package: `ai-decision-council`

Legacy command alias still supported:

```bash
llm-council ...
```

Primary command:

```bash
ai-decision-council ...
```

## API migration

Preferred API now:

```python
from ai_decision_council import Council
council = Council.from_env()
```

Legacy API still supported:

```python
from ai_decision_council import CouncilBridge
bridge = CouncilBridge()
```

## FastAPI module migration

New packaged API module:

```python
from ai_decision_council import create_fastapi_app
app = create_fastapi_app()
```

Versioned API contract is served under `/v1/*`.

## Environment compatibility

Preferred key:

- `LLM_COUNCIL_API_KEY`

Fallback key:

- `OPENROUTER_API_KEY`
