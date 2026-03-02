"""Configuration File Format and Precedence

This guide explains how to configure ai-decision-council using file-based configuration
instead of environment variables.
"""

# Configuration File Support

ai-decision-council supports configuration via **TOML** and **YAML** files, providing
a convenient alternative to environment variable management.

## Supported File Formats

### TOML Format

TOML is recommended for single-environment configurations.

**Example: `council.toml`**

```toml
[ai-decision-council]
api_key = "your-api-key-here"
provider = "openai"
models = ["gpt-4o", "gpt-4o-mini", "o1-mini"]
model_count = 3
max_retries = 2
retry_backoff_seconds = 0.5
stage_timeout_seconds = 120.0
title_timeout_seconds = 30.0
chairman_model = "gpt-4o"
title_model = "gpt-4o"
```

The `[ai-decision-council]` section header is optional — all top-level keys will be used.

### YAML Format

YAML is useful for complex deployments or multi-environment setups.

**Example: `council.yaml`**

```yaml
api_key: your-api-key-here
provider: anthropic
models:
  - claude-opus-4-5
  - claude-sonnet-4-5
  - claude-haiku-3-5
model_count: 3
max_retries: 2
retry_backoff_seconds: 0.5
stage_timeout_seconds: 120.0
title_timeout_seconds: 30.0
```

YAML requires the `pyyaml` package. Install it with:

```bash
pip install pyyaml
```

## Configuration Parameters

All settings from environment variables can be used in config files.
Key names are lowercase, underscore-separated versions of the env var names:

| Config File Key         | Environment Variable                | Type           | Default           |
| ----------------------- | ----------------------------------- | -------------- | ----------------- |
| `api_key`               | `LLM_COUNCIL_API_KEY`               | string         | (required)        |
| `api_url`               | `LLM_COUNCIL_API_URL`               | string         | provider-specific |
| `models`                | `LLM_COUNCIL_MODELS`                | string or list | (from catalog)    |
| `model_count`           | `LLM_COUNCIL_MODEL_COUNT`           | integer        | 5                 |
| `provider`              | `LLM_COUNCIL_PROVIDER`              | string         | "openrouter"      |
| `chairman_model`        | `LLM_COUNCIL_CHAIRMAN_MODEL`        | string         | first model       |
| `title_model`           | `LLM_COUNCIL_TITLE_MODEL`           | string         | chairman model    |
| `max_retries`           | `LLM_COUNCIL_MAX_RETRIES`           | integer        | 2                 |
| `retry_backoff_seconds` | `LLM_COUNCIL_RETRY_BACKOFF_SECONDS` | float          | 0.5               |
| `stage_timeout_seconds` | `LLM_COUNCIL_STAGE_TIMEOUT_SECONDS` | float          | 120.0             |
| `title_timeout_seconds` | `LLM_COUNCIL_TITLE_TIMEOUT_SECONDS` | float          | 30.0              |

## Usage

### CLI

Use the `--config` / `-c` flag with `run` and `api serve` commands:

```bash
# Run a prompt with config file
ai-decision-council run --prompt "Your question" --config council.toml

# Run API server with config file
ai-decision-council api serve --host 0.0.0.0 --port 8001 --config council.yaml
```

### Python

Load config programmatically with `CouncilConfig.from_file()`:

```python
from ai_decision_council import Council
from ai_decision_council.config import CouncilConfig

# Load from file with full environment override support
config = CouncilConfig.from_file_and_env("council.toml")
council = Council(config=config)

result = council.run_sync("Explain microservices")
print(result.final_response)
```

Or load just the file without environment fallback:

```python
config = CouncilConfig.from_file("council.toml")
council = Council(config=config)
```

## Configuration Precedence

When using `CouncilConfig.from_file_and_env()`, settings are applied in this priority order
(highest to lowest):

1. **Environment Variables** — `LLM_COUNCIL_*` env vars override everything
2. **Config File** — Values from the TOML or YAML file
3. **Defaults** — Built-in package defaults

### Example

Given these layers:

- Config file: `provider = "openai"`, `api_key = "file-key"`
- Environment: `LLM_COUNCIL_PROVIDER=anthropic` (no API key env var)

Result: `provider = "anthropic"` (from env), `api_key = "file-key"` (from file)

This allows you to use a config file for most settings while overriding specific
values per-environment via environment variables.

## Type Conversion

Configuration files support numeric types natively:

**TOML:**

```toml
model_count = 3          # integer
max_retries = 2          # integer
retry_backoff_seconds = 0.5   # float
stage_timeout_seconds = 120.0 # float
```

**YAML:**

```yaml
model_count: 3 # integer
max_retries: 2 # integer
retry_backoff_seconds: 0.5 # float
stage_timeout_seconds: 120.0 # float
```

Models can be specified as either a string (comma-separated) or a list:

**TOML string:**

```toml
models = "gpt-4o,gpt-4o-mini,o1-mini"
```

**YAML list:**

```yaml
models:
  - gpt-4o
  - gpt-4o-mini
  - o1-mini
```

## Error Handling

If a config file cannot be found or parsed, an error is raised:

```python
import pytest
from ai_decision_council.config import CouncilConfig

with pytest.raises(FileNotFoundError):
    CouncilConfig.from_file("nonexistent.toml")

with pytest.raises(ValueError):
    CouncilConfig.from_file("invalid.toml")  # Invalid TOML syntax
```

## Best Practices

1. **Separate secrets** — Use environment variables for API keys in production:

   ```bash
   export LLM_COUNCIL_API_KEY="$SECRET_KEY"
   ai-decision-council run --prompt "..." --config council.toml
   ```

2. **Version control** — Commit basic config files; add API keys only via environment:

   ```toml
   # council.toml (safe to commit)
   provider = "openai"
   models = ["gpt-4o", "gpt-4o-mini"]
   max_retries = 2
   ```

3. **Per-environment configs** — Use separate files for different deployment environments:
   - `council.prod.toml`
   - `council.staging.yaml`
   - `council.local.toml`

4. **Documentation** — Include example config files in your project:
   ```bash
   cp council.example.toml council.local.toml  # User customizes locally
   ```
