# Architecture & System Design

## Overview

ai-decision-council implements a **3-stage deliberation system** where multiple LLMs collaborate to reach a consensus answer through peer review.

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         User Query                               │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
        ┌────────────────────────────────────────┐
        │     Stage 1: Collect First Opinions    │
        ├────────────────────────────────────────┤
        │ • Query distributed to all models      │
        │ • Parallel execution (concurrent)      │
        │ • Partial failure tolerance            │
        └────────────────────────────────────────┘
                             │
                ┌────────────┴────────────┐
                │                         │
           Model 1               Model 2
          Response A           Response B
                │                         │
                └────────────┬────────────┘
                             ▼
        ┌────────────────────────────────────────┐
        │  Stage 2: Anonymous Peer Review        │
        ├────────────────────────────────────────┤
        │ • Responses anonymized (Response A, B) │
        │ • Each model ranks others              │
        │ • Parallel evaluation                  │
        │ • Prevents model favoritism            │
        └────────────────────────────────────────┘
                             │
                    ┌────────┴────────┐
                    │                 │
              Rankings from        Rankings from
               Model 1              Model 2
                    │                 │
                    └────────┬────────┘
                             ▼
        ┌────────────────────────────────────────┐
        │   Aggregate Rankings & Analysis        │
        ├────────────────────────────────────────┤
        │ • Parse rankings from each model       │
        │ • Calculate average position per resp. │
        │ • Sort by consensus quality            │
        └────────────────────────────────────────┘
                             │
                             ▼
        ┌────────────────────────────────────────┐
        │ Stage 3: Chairman Synthesis            │
        ├────────────────────────────────────────┤
        │ • Chairman model receives:             │
        │   - Original query                     │
        │   - All stage 1 responses              │
        │   - Aggregated rankings                │
        │ • Synthesizes final decision answer    │
        └────────────────────────────────────────┘
                             │
                             ▼
        ┌────────────────────────────────────────┐
        │         Return Structured Result       │
        ├────────────────────────────────────────┤
        │ {                                       │
        │   "stage1": [responses],               │
        │   "stage2": [rankings],                │
        │   "stage3": final_answer,              │
        │   "metadata": {aggregates, errors},    │
        │   "errors": [any failures]             │
        │ }                                       │
        └────────────────────────────────────────┘
```

## Execution Flow Detail

### Stage 1: First Opinions (Parallel)

```
┌─────────────────────────────────────────────────────────────┐
│                    User Query                                │
│            "Explain microservices"                           │
└─────────────────────────────────────────────────────────────┘
                             │
    ┌────────────────────────┼────────────────────────┐
    │                        │                        │
    ▼                        ▼                        ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│   Model 1       │  │   Model 2       │  │   Model 3       │
│  (GPT-5.1)      │  │  (Claude)       │  │  (Gemini)       │
│                 │  │                 │  │                 │
│ Responds with   │  │ Responds with   │  │ Responds with   │
│ detailed tech   │  │ pragmatic arch  │  │ cloud-first    │
│ explanation     │  │ patterns        │  │ perspective    │
└─────────────────┘  └─────────────────┘  └─────────────────┘
    │                        │                        │
    └────────────────────────┼────────────────────────┘
                             │
                        Collect All
                       Responses
```

### Stage 2: Anonymous Peer Review (Parallel)

```
Real Model Names: [Model 1, Model 2, Model 3]
                          │
                          ▼
            Anonymize: {A: Model 1, B: Model 2, C: Model 3}
                          │
    ┌─────────────────────┼─────────────────────┐
    │                     │                     │
    ▼                     ▼                     ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│  Model 1     │  │  Model 2     │  │  Model 3     │
│  Sees:       │  │  Sees:       │  │  Sees:       │
│  - A = ?     │  │  - A = ?     │  │  - A = ?     │
│  - B = ?     │  │  - B = ?     │  │  - B = ?     │
│  - C = ?     │  │  - C = ?     │  │  - C = ?     │
│              │  │              │  │              │
│ Rankings:    │  │ Rankings:    │  │ Rankings:    │
│ 1. C (best)  │  │ 1. A (best)  │  │ 1. B (best)  │
│ 2. A         │  │ 2. C         │  │ 2. C         │
│ 3. B         │  │ 3. B         │  │ 3. A         │
└──────────────┘  └──────────────┘  └──────────────┘
    │                     │                     │
    └─────────────────────┼─────────────────────┘
                          │
                 De-anonymize Results
              (A=Model 1, B=Model 2, C=Model 3)
                          │
                          ▼
            Calculate Consensus Rankings:
           Avg Position = Sum(positions) / count
```

### Stage 3: Chairman Synthesis (Sequential)

```
                    Aggregated Data
                          │
      ┌───────────────────┼───────────────────┐
      │                   │                   │
      ▼                   ▼                   ▼
  Stage 1 Responses  Consensus Rankings  Original Query
  ├─ Response A     ├─ Model 1: Avg 1.5  "Explain
  ├─ Response B     ├─ Model 2: Avg 2.8   microservices"
  └─ Response C     └─ Model 3: Avg 2.2
      │                   │                   │
      └───────────────────┼───────────────────┘
                          │
                          ▼
            ┌──────────────────────────────┐
            │   Chairman Model              │
            │   (e.g., GPT-5.1)             │
            │                              │
            │ "Look at what everyone said  │
            │  and their peer scores. Now  │
            │  synthesize the best answer" │
            │                              │
            │ Produces: Final Answer       │
            └──────────────────────────────┘
```

## Key Design Decisions

### 1. Anonymous Stage 2

**Why:** Prevents model bias. If Model A sees it's being evaluated by Model B, it might try to please Model B instead of being objective.

**How:**

- Models receive: "Response A", "Response B", "Response C"
- Backend maintains secret mapping: {A → Model 1, B → Model 2, C → Model 3}
- Frontend de-anonymizes for display only (with note that models saw anonymous labels)

### 2. Graceful Partial Failure

**Why:** Robustness. If 1 of 5 models times out, the council should still work.

**How:**

- Stage 1: If Model fails, skip it. Only cancel if ALL fail.
- Stage 2: If Model fails to rank, ignore its rankings. Aggregate from successful models.
- Stage 3: If Chairman fails, fall back to highest-ranked Stage 1 response.

**Result:** Response completed with errors recorded, not a full pipeline failure.

### 3. Retry Logic with Exponential Backoff

```
Attempt 1: Immediately
          ↓ (if rate limit)
Attempt 2: Wait 0.5s
          ↓ (if rate limit)
Attempt 3: Wait 1.0s
          ↓ (if timeout)
          Fail gracefully
```

### 4. Provider Abstraction

```
┌─────────────────────────────────────────┐
│     Council (highest level)             │
└──────────────────┬──────────────────────┘
                   │
┌──────────────────▼──────────────────────┐
│    ProviderAdapter (Protocol)           │
│  async def chat(model, messages, ...) │
└──────────────────┬──────────────────────┘
                   │
    ┌──────────────┴──────────────┐
    │                             │
    ▼                             ▼
OpenRouterAdapter          CustomAdapter
(Concrete impl.)          (Your own impl.)
```

This allows swapping providers without changing Stage 1/2/3 logic.

## Data Flow

### Through the Pipeline

```json
{
  "stage1_results": [
    {
      "model": "openai/gpt-5.1",
      "response": "Microservices are...",
      "error": null
    }
  ],
  "stage2_results": [
    {
      "model": "openai/gpt-5.1",
      "ranking": "FINAL RANKING:\n1. Response C\n2. Response A\n3. Response B",
      "parsed_ranking": ["C", "A", "B"],
      "error": null
    }
  ],
  "metadata": {
    "label_to_model": {
      "A": "openai/gpt-5.1",
      "B": "anthropic/claude-sonnet-4.5",
      "C": "google/gemini-3-pro-preview"
    },
    "aggregate_rankings": {
      "openai/gpt-5.1": { "avg_position": 1.33, "votes": 3 },
      "anthropic/claude-sonnet-4.5": { "avg_position": 2.0, "votes": 3 },
      "google/gemini-3-pro-preview": { "avg_position": 1.67, "votes": 3 }
    },
    "errors": []
  },
  "stage3_result": "Microservices are an architectural approach...",
  "errors": []
}
```

## Timeouts & Constraints

| Component        | Default | Configurable              |
| ---------------- | ------- | ------------------------- |
| Stage 1 timeout  | 120s    | `STAGE_TIMEOUT_SECONDS`   |
| Stage 2 timeout  | 120s    | `STAGE_TIMEOUT_SECONDS`   |
| Stage 3 timeout  | 120s    | `STAGE_TIMEOUT_SECONDS`   |
| Title generation | 30s     | `TITLE_TIMEOUT_SECONDS`   |
| Model count      | 2-20    | `LLM_COUNCIL_MODEL_COUNT` |
| Retry attempts   | 2       | `MAX_RETRIES`             |
| Retry backoff    | 0.5s    | `RETRY_BACKOFF_SECONDS`   |

## Scalability Considerations

### Current Limitations

- **Sequential model selection:** Models hardcoded or env-based, not dynamic
- **File-based storage:** JSON files, not database
- **Single instance:** No clustering, no horizontal scaling
- **Blocking I/O on Stage 3:** Waits for Stage 2 to complete before running

### Room for Improvement

- Implement model discovery (dynamic model pool)
- Swap FileStorage for PostgreSQL/MongoDB
- Add request deduplication (cache identical queries)
- Parallelize Stage 2 and Stage 3 (not strictly sequential)
- Add request tracing for observability

## Error Handling

```
Pipeline Execution
        │
        ├─ Stage 1 Failed?
        │  └─ All models failed → Fail pipeline
        │  └─ Some failed → Continue with successful responses
        │
        ├─ Stage 2 Failed?
        │  └─ No rankings → Skip aggregation, use raw responses
        │
        └─ Stage 3 Failed?
           └─ Return highest-ranked Stage 1 response as fallback
```

All errors collected in `result.errors` with structure:

```python
ModelRunError(
    model="openai/gpt-5.1",
    stage="stage_1",
    error_code="provider_timeout_error",
    message="Request exceeded 120s timeout"
)
```

## Performance Characteristics

**Best case (all models succeed, parallel):**

```
Stage 1: ~5-15s (longest model response time)
Stage 2: ~5-15s (longest ranking evaluation)
Stage 3: ~5-10s (synthesis)
Total:   ~15-40s
```

**Worst case (with retries, partial failures):**

```
Stage 1: ~(120s × 2 retries) = up to 240s
Stage 2: Same as stage 1
Stage 3: Same as stage 1
Total:   Could exceed 10 minutes with max retries
```

This is why configurable timeouts and retry counts are important.
