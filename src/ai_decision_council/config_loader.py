"""Configuration file loading utilities for ai-decision-council.

Supports YAML and TOML configuration files with environment variable precedence.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, cast

try:
    import tomllib
except ModuleNotFoundError:
    # Python 3.10 compatibility
    import tomli as tomllib


def _load_toml_file(path: Path) -> dict[str, Any]:
    """Load configuration from a TOML file."""
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    if not path.is_file():
        raise ValueError(f"Config path is not a file: {path}")

    with open(path, "rb") as f:
        config: dict[str, Any] = tomllib.load(f)
    return cast(dict[str, Any], config.get("ai-decision-council", config))


def _load_yaml_file(path: Path) -> dict[str, Any]:
    """Load configuration from a YAML file."""
    try:
        import yaml
    except ImportError:
        raise ImportError(
            "PyYAML is required for YAML config file support. "
            "Install with: pip install pyyaml"
        )

    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    if not path.is_file():
        raise ValueError(f"Config path is not a file: {path}")

    with open(path, "r", encoding="utf-8") as f:
        raw_config = yaml.safe_load(f)
    config: dict[str, Any] = raw_config or {}
    return cast(dict[str, Any], config.get("ai-decision-council", config))


def load_config_file(path: str | Path) -> dict[str, Any]:
    """Load configuration from a file.

    Supports .toml and .yaml/.yml file extensions.
    Configuration will be extracted from the 'ai-decision-council' section if present.

    Parameters
    ----------
    path : str | Path
        Path to the configuration file.  Will be resolved relative to current directory.

    Returns
    -------
    dict[str, Any]
        Configuration dictionary with environment variable names as keys.
        Environment variable names follow the pattern: LLM_COUNCIL_*

    Raises
    ------
    FileNotFoundError
        If the file does not exist.
    ValueError
        If the file path is not a file or file type is unsupported.
    """
    path = Path(path).resolve()

    # Check if path is a file first (before checking extension)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    if not path.is_file():
        raise ValueError(f"Config path is not a file: {path}")

    if path.suffix.lower() == ".toml":
        try:
            return _load_toml_file(path)
        except FileNotFoundError:
            raise
        except Exception as exc:
            raise ValueError(f"Failed to parse TOML config file: {exc}") from exc

    if path.suffix.lower() in (".yaml", ".yml"):
        try:
            return _load_yaml_file(path)
        except ImportError:
            raise
        except Exception as exc:
            raise ValueError(f"Failed to parse YAML config file: {exc}") from exc

    raise ValueError(
        f"Unsupported config file type: {path.suffix}. "
        "Supported: .toml, .yaml, .yml"
    )


def merge_config_sources(
    config_file: dict[str, Any] | None = None,
    env_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge configuration from multiple sources with proper precedence.

    Precedence (highest to lowest):
    1. env_overrides (direct overrides, typically from CLI args)
    2. config_file (from TOML/YAML file)
    3. Empty (use defaults during CouncilConfig resolution)

    Parameters
    ----------
    config_file : dict[str, Any] | None
        Configuration loaded from file.
    env_overrides : dict[str, Any] | None
        CLI or programmatic overrides.

    Returns
    -------
    dict[str, Any]
        Merged configuration dictionary.
    """
    merged: dict[str, Any] = {}

    # Start with file config (if provided)
    if config_file:
        merged.update(config_file)

    # Layer in CLI overrides (if provided)
    if env_overrides:
        merged.update(env_overrides)

    return merged


def normalize_config_keys(config: dict[str, Any]) -> dict[str, Any]:
    """Normalize configuration keys to environment variable format.

    Converts underscore-separated keys to uppercase environment variable names.

    Examples:
        api_key -> API_KEY
        model_count -> MODEL_COUNT
        models -> MODELS
        provider -> PROVIDER

    Parameters
    ----------
    config : dict[str, Any]
        Configuration dictionary with lowercase keys.

    Returns
    -------
    dict[str, Any]
        Configuration dictionary with uppercase keys suitable for CouncilConfig.from_env().
    """
    normalized: dict[str, Any] = {}

    key_mapping = {
        "api_key": "LLM_COUNCIL_API_KEY",
        "api_url": "LLM_COUNCIL_API_URL",
        "models": "LLM_COUNCIL_MODELS",
        "model_count": "LLM_COUNCIL_MODEL_COUNT",
        "chairman_model": "LLM_COUNCIL_CHAIRMAN_MODEL",
        "title_model": "LLM_COUNCIL_TITLE_MODEL",
        "provider": "LLM_COUNCIL_PROVIDER",
        "max_retries": "LLM_COUNCIL_MAX_RETRIES",
        "retry_backoff_seconds": "LLM_COUNCIL_RETRY_BACKOFF_SECONDS",
        "stage_timeout_seconds": "LLM_COUNCIL_STAGE_TIMEOUT_SECONDS",
        "title_timeout_seconds": "LLM_COUNCIL_TITLE_TIMEOUT_SECONDS",
    }

    for key, value in config.items():
        # Use explicit mapping if available
        if key in key_mapping:
            normalized[key_mapping[key]] = value
        else:
            # For unmapped keys, assume they're already in env var format
            normalized[key] = value

    return normalized
