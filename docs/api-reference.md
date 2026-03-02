# Complete API Reference

## Table of Contents

1. [Client API](#client-api)
2. [CouncilResult](#councilresult)
3. [CouncilConfig](#councilconfig)
4. [HTTP Endpoints](#http-endpoints)
5. [Error Codes](#error-codes)
6. [Types & Schemas](#types--schemas)

---

## Client API

### Council Class

Primary synchronized and asynchronous client for running the council pipeline.

#### Constructor

```python
from ai_decision_council import Council, CouncilConfig

# Option 1: From environment
council = Council.from_env()

# Option 2: With explicit config
config = CouncilConfig(
    api_key="sk-openrouter-key",
    models=["openai/gpt-5.1", "anthropic/claude-sonnet-4.5"],
    chairman_model="openai/gpt-5.1"
)
council = Council(config=config)

# Option 3: With custom provider
from ai_decision_council.providers.openrouter import OpenRouterAdapter

adapter = OpenRouterAdapter(api_key="sk-...")
council = Council(config=config, provider_adapter=adapter)
```

#### Class Method: `from_env()`

```python
@classmethod
def from_env(cls, **overrides) -> "Council":
    """
    Create Council instance from environment variables.

    Environment variables:
    - LLM_COUNCIL_API_KEY: OpenRouter API key (required)
    - LLM_COUNCIL_MODELS: Comma-separated model list (optional)
    - LLM_COUNCIL_MODEL_COUNT: Number of models to use (default: 5)
    - LLM_COUNCIL_CHAIRMAN_MODEL: Model for Stage 3 (optional)
    - LLM_COUNCIL_TITLE_MODEL: Model for title generation (optional)
    - LLM_COUNCIL_API_URL: Provider endpoint (default: OpenRouter)

    Args:
        **overrides: Override specific config values

    Example:
        council = Council.from_env(model_count=3)

    Returns:
        Council: Configured instance

    Raises:
        ValueError: If required env vars missing or invalid
    """
```

#### Method: `run()` (Async)

```python
async def run(self, prompt: str) -> CouncilResult:
    """
    Run the full 3-stage council pipeline asynchronously.

    Executes:
    1. Stage 1: Parallel queries to all models
    2. Stage 2: Parallel ranking evaluations
    3. Stage 3: Chairman synthesis

    Args:
        prompt (str): User query/question (max 10,000 characters)

    Returns:
        CouncilResult: Complete pipeline output

    Raises:
        ValueError: If prompt is empty or all Stage 1 models fail

    Example:
        council = Council.from_env()
        result = await council.run("Explain microservices")
        print(result.final_response)
    """
```

#### Method: `run_sync()`

```python
def run_sync(self, prompt: str) -> CouncilResult:
    """
    Synchronous wrapper around run(). Calls asyncio.run() internally.

    Args:
        prompt (str): User query

    Returns:
        CouncilResult: Pipeline output

    Raises:
        ValueError: If called inside active event loop
        RuntimeError: If prompt invalid

    Example:
        council = Council.from_env()
        result = council.run_sync("Your question")
    """
```

#### Method: `ask()` (Async)

```python
async def ask(self, prompt: str) -> str:
    """
    Shorthand: Run council and return ONLY final_response.

    Equivalent to:
        result = await council.run(prompt)
        return result.final_response

    Args:
        prompt (str): User query

    Returns:
        str: Final synthesized answer

    Example:
        answer = await council.ask("What is AI?")
    """
```

#### Method: `ask_sync()`

```python
def ask_sync(self, prompt: str) -> str:
    """
    Synchronous version of ask().

    Args:
        prompt (str): User query

    Returns:
        str: Final answer

    Raises:
        RuntimeError: If called inside active event loop
    """
```

---

## CouncilResult

Complete output from a council run.

### Properties

```python
@dataclass
class CouncilResult:
    """Full council pipeline output."""

    # Stage outputs
    stage1: List[Dict[str, Any]]
    """
    First opinions from all models.

    Example:
        [
            {
                "model": "openai/gpt-5.1",
                "response": "Microservices are...",
                "error": None
            },
            {
                "model": "anthropic/claude-sonnet-4.5",
                "response": "From an architectural perspective...",
                "error": None
            }
        ]
    """

    stage2: List[Dict[str, Any]]
    """
    Peer ranking evaluations from each model.

    Example:
        [
            {
                "model": "openai/gpt-5.1",
                "ranking": "FINAL RANKING:\n1. Response B\n2. Response A",
                "parsed_ranking": ["B", "A"],
                "error": None
            }
        ]
    """

    stage3: str
    """
    Final synthesized answer from chairman model.

    Example:
        "Microservices is an architectural approach where..."
    """

    metadata: Dict[str, Any]
    """
    Pipeline metadata and aggregations.

    Keys:
    - label_to_model: {"A": "openai/gpt-5.1", "B": "anthropic/claude-..."}
    - aggregate_rankings: Per-model consensus scores
    - errors: Any pipeline-level errors

    Example:
        {
            "label_to_model": {
                "A": "openai/gpt-5.1",
                "B": "anthropic/claude-sonnet-4.5"
            },
            "aggregate_rankings": {
                "openai/gpt-5.1": {
                    "avg_position": 1.5,
                    "votes": 2
                }
            },
            "errors": []
        }
    """

    errors: List[ModelRunError]
    """
    Errors encountered during execution.

    Each error is a ModelRunError with:
    - model: Which model failed
    - stage: stage_1, stage_2, or stage_3
    - error_code: machine-readable error type
    - message: human-readable error message
    """

    @property
    def final_response(self) -> str:
        """Alias for stage3 (the final answer)."""

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert result to dictionary (JSON-serializable).

        Returns:
            dict: All fields converted to basic types

        Example:
            result_dict = result.to_dict()
            json_str = json.dumps(result_dict)
        """
```

### Usage Examples

```python
# Get just the answer
answer = result.final_response

# See what each model said
for response in result.stage1:
    print(f"{response['model']}: {response['response']}")

# See consensus rankings
print(result.metadata["aggregate_rankings"])

# Check for errors
if result.errors:
    for error in result.errors:
        print(f"{error.model} failed in {error.stage}: {error.message}")

# Serialize for storage
import json
data = result.to_dict()
json.dump(data, open("result.json", "w"))
```

---

## CouncilConfig

Runtime configuration for Council execution.

### Constructor

```python
from ai_decision_council import CouncilConfig

config = CouncilConfig(
    api_key="sk-...",                              # Required
    models=["openai/gpt-5.1", "anthropic/claude-sonnet-4.5"],
    model_count=5,                                 # If models not explicit
    chairman_model="openai/gpt-5.1",               # Defaults to first model
    title_model="openai/gpt-5.1",                  # Defaults to chairman
    api_url="https://openrouter.ai/api/v1/chat/completions",
    provider="openrouter",                         # Only "openrouter" supported
    max_retries=2,                                 # Retry attempts
    retry_backoff_seconds=0.5,                     # Backoff between retries
    stage_timeout_seconds=120,                     # Max time per stage
    title_timeout_seconds=30                       # Title generation timeout
)
```

### Class Method: `from_env()`

```python
@classmethod
def from_env(cls, **overrides) -> "CouncilConfig":
    """
    Load config from environment variables.

    Environment variables read:
    - LLM_COUNCIL_API_KEY (required)
    - LLM_COUNCIL_MODELS (optional, comma-separated)
    - LLM_COUNCIL_MODEL_COUNT (optional, default 5)
    - LLM_COUNCIL_CHAIRMAN_MODEL (optional)
    - LLM_COUNCIL_TITLE_MODEL (optional)
    - LLM_COUNCIL_API_URL (optional, default OpenRouter)
    - LLM_COUNCIL_PROVIDER (optional, default "openrouter")
    - LLM_COUNCIL_MAX_RETRIES (optional, default 2)
    - LLM_COUNCIL_RETRY_BACKOFF_SECONDS (optional, default 0.5)
    - LLM_COUNCIL_STAGE_TIMEOUT_SECONDS (optional, default 120)
    - LLM_COUNCIL_TITLE_TIMEOUT_SECONDS (optional, default 30)
    - OPENROUTER_API_KEY (legacy fallback for LLM_COUNCIL_API_KEY)

    Args:
        **overrides: Override specific values

    Example:
        config = CouncilConfig.from_env(model_count=3)

    Returns:
        CouncilConfig: Parsed configuration

    Raises:
        ValueError: If required env vars missing
    """
```

### Method: `with_resolved_defaults()`

```python
def with_resolved_defaults(self) -> "CouncilConfig":
    """
    Validate and apply defaults to config.

    - If only model_count is set, fills models from DEFAULT_MODEL_CATALOG
    - Validates chairman_model is in selected models
    - Validates title_model is set (defaults to chairman)
    - Validates model count is 2-20
    - Ensures all required fields set

    Returns:
        CouncilConfig: Resolved configuration

    Raises:
        ValueError: If config is invalid

    Example:
        resolved = config.with_resolved_defaults()
    """
```

---

## HTTP Endpoints

### POST /v1/conversations

Start a new conversation.

**Request:**

```json
{
  "messages": [
    {
      "role": "user",
      "content": "Explain microservices"
    }
  ]
}
```

**Response:**

```json
{
  "conversation_id": "550e8400-e29b-41d4-a716-446655440000",
  "messages": [
    {
      "role": "user",
      "content": "Explain microservices",
      "created_at": "2026-03-02T10:30:00Z",
      "id": "msg-001"
    }
  ],
  "created_at": "2026-03-02T10:30:00Z"
}
```

**Status Codes:**

- `201 Created`: Conversation started
- `400 Bad Request`: Invalid request body
- `401 Unauthorized`: Missing/invalid bearer token
- `429 Too Many Requests`: Rate limit exceeded

---

### POST /v1/conversations/{conversation_id}/message

Send message to existing conversation. Triggers council run.

**Request:**

```json
{
  "content": "Your follow-up message"
}
```

**Response (Streaming - SSE):**

```
event: stage1
data: {"model": "openai/gpt-5.1", "response": "...", "error": null}

event: stage1
data: {"model": "anthropic/claude-sonnet-4.5", "response": "...", "error": null}

event: stage2
data: {"model": "openai/gpt-5.1", "ranking": "FINAL RANKING:\n...", "error": null}

event: stage3
data: {"response": "Synthesized answer from chairman..."}

event: metadata
data: {"label_to_model": {...}, "aggregate_rankings": {...}}

event: done
data: {}
```

**Status Codes:**

- `200 OK`: Event stream returned
- `404 Not Found`: Conversation doesn't exist
- `401 Unauthorized`: Token mismatch or invalid

---

### GET /v1/conversations/{conversation_id}

Retrieve conversation details.

**Response:**

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "created_at": "2026-03-02T10:30:00Z",
  "messages": [
    {
      "role": "user",
      "id": "msg-001",
      "content": "Explain microservices",
      "created_at": "2026-03-02T10:30:00Z"
    },
    {
      "role": "assistant",
      "id": "msg-002",
      "content": {
        "stage1": [...],
        "stage2": [...],
        "stage3": "...",
        "metadata": {...}
      },
      "created_at": "2026-03-02T10:35:00Z"
    }
  ]
}
```

---

### GET /v1/conversations

List conversations (with owner isolation).

**Query Parameters:**

- `limit`: Max results (default 20, max 100)
- `offset`: Pagination offset (default 0)
- `created_after`: ISO 8601 timestamp filter

**Response:**

```json
{
  "conversations": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "created_at": "2026-03-02T10:30:00Z",
      "title": "Microservices Explanation"
    }
  ],
  "total": 42,
  "limit": 20,
  "offset": 0
}
```

---

### PATCH /v1/conversations/{conversation_id}

Update conversation title.

**Request:**

```json
{
  "title": "New Title"
}
```

**Response:**

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "title": "New Title",
  "updated_at": "2026-03-02T10:40:00Z"
}
```

---

## Error Codes

### Provider Errors

```python
class ModelRunError:
    model: str           # Which model failed
    stage: str          # stage_1, stage_2, stage_3, or stage_title
    error_code: str     # Machine-readable code below
    message: str        # Human-readable description

# Possible error_codes:
"provider_config_error"      # Missing/invalid API key
"provider_auth_error"        # Authentication failed
"provider_rate_limit_error"  # Rate limited
"provider_timeout_error"     # Request exceeded timeout
"provider_connection_error"  # Network error
"provider_response_error"    # Invalid response from provider
```

**Example:**

```json
{
  "model": "openai/gpt-5.1",
  "stage": "stage_1",
  "error_code": "provider_timeout_error",
  "message": "Request exceeded 120s timeout"
}
```

### HTTP Status Codes

| Code | Meaning           | When                       |
| ---- | ----------------- | -------------------------- |
| 200  | OK                | Request succeeded          |
| 201  | Created           | Conversation created       |
| 400  | Bad Request       | Invalid input              |
| 401  | Unauthorized      | Missing/invalid token      |
| 404  | Not Found         | Conversation not found     |
| 429  | Too Many Requests | Rate limit exceeded        |
| 500  | Internal Error    | Server error (brief retry) |
| 503  | Unavailable       | Provider temporarily down  |

---

## Types & Schemas

### ModelRunError

```python
@dataclass
class ModelRunError:
    """Represents a single model failure."""

    model: str
    """Model identifier that failed (e.g., "openai/gpt-5.1")"""

    stage: str
    """Which stage failed: "stage_1", "stage_2", "stage_3", "stage_title"."""

    error_code: str
    """
    Machine-readable error type.
    Values:
    - provider_config_error
    - provider_auth_error
    - provider_rate_limit_error
    - provider_timeout_error
    - provider_connection_error
    - provider_response_error
    """

    message: str
    """Human-readable error description."""
```

### ProviderResponse

```python
@dataclass
class ProviderResponse:
    """Standardized response from any provider."""

    content: str
    """The text response from the model."""

    reasoning_details: Any = None
    """Optional reasoning/thinking (for reasoning models)."""

    raw: Dict[str, Any] | None = None
    """Raw response from provider (for debugging)."""
```

### AuthContext

```python
@dataclass
class AuthContext:
    """Authentication context for API requests."""

    owner_id: str
    """Unique identifier of the authenticated user/token."""

    token_fingerprint: str
    """Hash of the API token (for audit logging)."""
```

---

## Full Example: Python Integration

```python
import asyncio
from ai_decision_council import Council, CouncilConfig

async def main():
    # Option 1: From env
    council = Council.from_env()

    # Option 2: Explicit config
    config = CouncilConfig.from_env(model_count=3)
    council = Council(config=config)

    # Run
    result = await council.run("Explain quantum computing")

    # Inspect output
    print("=" * 50)
    print("STAGE 1: Individual Responses")
    print("=" * 50)
    for resp in result.stage1:
        print(f"\n{resp['model']}:")
        print(resp['response'][:200] + "...")

    print("\n" + "=" * 50)
    print("STAGE 2: Peer Rankings")
    print("=" * 50)
    for rank in result.stage2:
        print(f"\n{rank['model']}:")
        print(rank['ranking'])

    print("\n" + "=" * 50)
    print("STAGE 3: Final Answer")
    print("=" * 50)
    print(result.final_response)

    print("\n" + "=" * 50)
    print("METADATA: Consensus")
    print("=" * 50)
    import json
    print(json.dumps(result.metadata['aggregate_rankings'], indent=2))

    # Check for errors
    if result.errors:
        print(f"\n⚠️ {len(result.errors)} error(s):")
        for err in result.errors:
            print(f"  - {err.model} ({err.stage}): {err.message}")

asyncio.run(main())
```

---

## Python SDK Types (TypeScript Available Too)

See `docs/sdk/` for:

- `council_api_client.py` (Python SDK client)
- `councilApiClient.ts` (TypeScript SDK client)
- `council_api_types.py` (Python type definitions)
- `councilApiTypes.ts` (TypeScript type definitions)
