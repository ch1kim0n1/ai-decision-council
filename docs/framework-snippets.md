# Framework Snippets

## FastAPI

```python
from fastapi import FastAPI
from ai_decision_council import Council

app = FastAPI()
council = Council.from_env()

@app.post("/ask")
async def ask(payload: dict):
    result = await council.run(payload["prompt"])
    return result.to_dict()
```

## FastAPI (packaged API module, embedded)

```python
from fastapi import FastAPI
from ai_decision_council.api.fastapi import (
    APISettings,
    FileStorageBackend,
    InMemoryRateLimiter,
    StaticTokenAuthBackend,
    create_router,
)
from ai_decision_council import Council

app = FastAPI()
settings = APISettings.from_env()
router = create_router(
    settings=settings,
    storage_backend=FileStorageBackend(settings.data_dir),
    rate_limiter=InMemoryRateLimiter(),
    council_factory=Council.from_env,
)
app.include_router(router, prefix=settings.api_prefix)
```

## Flask

```python
from flask import Flask, request, jsonify
from ai_decision_council import Council

app = Flask(__name__)
council = Council.from_env()

@app.post("/ask")
def ask():
    prompt = request.json["prompt"]
    result = council.run_sync(prompt)
    return jsonify(result.to_dict())
```

## Django view

```python
from django.http import JsonResponse
from ai_decision_council import Council

council = Council.from_env()

def ask(request):
    prompt = request.GET.get("prompt", "")
    result = council.run_sync(prompt)
    return JsonResponse(result.to_dict())
```

## Celery task

```python
from celery import shared_task
from ai_decision_council import Council

@shared_task
def run_council(prompt: str):
    council = Council.from_env()
    return council.run_sync(prompt).to_dict()
```
