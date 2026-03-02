# Changelog

All notable changes to `ai-decision-council` will be documented in this file.

## [1.3.0] - 2026-03-08

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

## [1.2.1] - 2026-03-07

### Fixed

- Linting cleanup: Resolved all 43 ruff check violations
- Fixed undefined variable warnings in `council.py`
- Renamed ambiguous variable names (e.g., `l` → `line`) in test_observability.py

## [1.0.0] - 2026-03-01

### Added

- Core 3-stage council orchestration package.
- CLI commands: `init`, `bridge`, `doctor`, `run`.
- Integration bridge API via `CouncilBridge`.
- Baseline unit tests for core logic, config, bridge, and CLI.
