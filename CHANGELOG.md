# Changelog

All notable changes to `ai-decision-council` will be documented in this file.

## [Unreleased]

### Added

- `ai_decision_council.__version__`, single-sourced from installed package metadata.
- `CircuitBreaker.call_async()` to guard `async` provider calls.
- Per-execution cost/token metrics surfaced in `CouncilResult.metadata["metrics"]`
  when the provider returns usage data.

### Changed

- **Production features are now actually wired into the pipeline.** The
  response cache, cost/token metrics, and circuit breaker introduced in 1.4.0
  were previously defined but never invoked. They are now integrated:
  - `Council` runs are guarded by a `CircuitBreaker` by default (pass
    `circuit_breaker=False` to disable, or supply your own).
  - Pass a `ResponseCache` to `Council(cache=...)` to short-circuit identical
    repeated runs.
  - `CouncilResult.metadata["metrics"]` reports per-stage token counts and USD
    cost when the provider returns `usage`.

### Fixed

- `tomli` is now a runtime dependency on Python < 3.11, so `from_file()` TOML
  config loading works on a base install (previously crashed on Python 3.10).
- Bearer-token auth now uses constant-time digest comparison
  (`hmac.compare_digest`), removing a timing side channel.
- Corrected `OpenAIAdapter` and `normalize_config_keys` docstrings to match
  their implementations.

## [1.4.0] - 2025-03-09

### Added

- **Response caching layer**: In-memory and Redis-ready cache backends
  - `InMemoryCache` — TTL-aware with configurable expiration
  - `RedisCache` — Distributed cache backend
  - `ResponseCache` — High-level wrapper for caching LLM responses
  - `compute_cache_key()` — Deterministic SHA256-based key generation
- **Cost tracking module**: Per-call and pipeline-level expense tracking
  - `ModelMetrics` — Individual call metrics (duration, tokens, cost)
  - `ExecutionMetrics` — Full pipeline breakdown with stage costs
  - `MODEL_COSTS` — Pricing data for 12+ models (OpenAI, Anthropic, Google, Open Router, etc.)
  - Cost calculations in USD with token multipliers
- **Circuit breaker pattern**: Fault tolerance for provider failures
  - `CircuitBreaker` — Automatic fail-fast with recovery backoff
  - `CircuitState` — CLOSED / OPEN / HALF_OPEN state machine
  - Configurable failure threshold (default 5) and recovery timeout (60s)
- **Kubernetes deployment manifests** (`k8s-deployment.yaml`):
  - 3-replica deployment with autoscaling (3-10 replicas)
  - HorizontalPodAutoscaler (CPU/memory based)
  - PodDisruptionBudget for reliability
  - ServiceAccount, RBAC roles, and Secrets management
  - Health checks with readiness/liveness probes
- **Updated exports**: All new modules exposed in `__init__.py`

### Changed

- Removed Docker support (Dockerfile/docker-compose templates)
  - Docker files removed from CLI scaffolding
  - Documentation updated to focus on Kubernetes deployment
  - Users should provide their own container images to registries
- Updated deployment documentation with Kubernetes-first approach
- Enhanced CI/CD example to focus on kubectl deployment

### Fixed

- CLI template cleanup (removed Docker-related bootstrapping)
- Architecture documentation updated to reflect current module structure

## [1.3.0] - 2025-03-08

### Added

- **Type checking enforcement**: Integrated mypy with strict configuration in CI/CD pipeline
- **Configuration file support**: Load settings from TOML/YAML files with environment override precedence
  - `CouncilConfig.from_file()` — load from TOML/YAML
  - `CouncilConfig.from_file_and_env()` — merge file + environment with proper precedence
  - CLI: `--config` / `-c` flag for `run` and `api serve` commands
- **New config_loader module**: Utilities for file parsing and key normalization
- Updated documentation with configuration file examples and precedence rules
- 25 new tests for configuration file functionality (total: 232 tests)

### Changed

- Enhanced dev dependencies: Added `tomli` (Python 3.10 backport), `pyyaml`, `mypy`, `ruff`
- CLI commands now support `--config` argument for file-based configuration
- API server startup can now accept config file path

### Fixed

- Type annotations improved across codebase (8 mypy errors resolved)
- Removed unused `type: ignore` comments
- Better type safety for configuration loading functions

## [1.2.1] - 2025-03-07

### Fixed

- Linting cleanup: Resolved all 43 ruff check violations
- Fixed undefined variable warnings in `council.py`
- Renamed ambiguous variable names (e.g., `l` → `line`) in test_observability.py

## [1.0.0] - 2025-03-01

### Added

- Core 3-stage council orchestration package.
- CLI commands: `init`, `bridge`, `doctor`, `run`.
- Integration bridge API via `CouncilBridge`.
- Baseline unit tests for core logic, config, bridge, and CLI.
