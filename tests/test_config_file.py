"""Tests for configuration file loading and support."""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_decision_council.config import CouncilConfig
from ai_decision_council.config_loader import (
    load_config_file,
    merge_config_sources,
    normalize_config_keys,
)


class TestConfigLoader:
    """Tests for the config_loader module."""

    def test_load_toml_minimal(self, tmp_path: Path) -> None:
        """Test loading minimal TOML configuration."""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            """
[ai-decision-council]
api_key = "test-key"
models = ["model1", "model2"]
"""
        )

        result = load_config_file(config_file)
        assert result["api_key"] == "test-key"
        assert result["models"] == ["model1", "model2"]

    def test_load_toml_full(self, tmp_path: Path) -> None:
        """Test loading complete TOML configuration."""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            """
[ai-decision-council]
api_key = "test-key"
api_url = "https://api.example.com/v1"
models = ["model1", "model2", "model3"]
model_count = 3
provider = "openai"
max_retries = 3
retry_backoff_seconds = 1.0
stage_timeout_seconds = 60.0
title_timeout_seconds = 15.0
"""
        )

        result = load_config_file(config_file)
        assert result["api_key"] == "test-key"
        assert result["api_url"] == "https://api.example.com/v1"
        assert result["models"] == ["model1", "model2", "model3"]
        assert result["model_count"] == 3
        assert result["provider"] == "openai"
        assert result["max_retries"] == 3
        assert result["retry_backoff_seconds"] == 1.0
        assert result["stage_timeout_seconds"] == 60.0
        assert result["title_timeout_seconds"] == 15.0

    def test_load_yaml_minimal(self, tmp_path: Path) -> None:
        """Test loading minimal YAML configuration."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            """
ai-decision-council:
  api_key: test-key
  models:
    - model1
    - model2
"""
        )

        result = load_config_file(config_file)
        assert result["api_key"] == "test-key"
        assert result["models"] == ["model1", "model2"]

    def test_load_yml_file(self, tmp_path: Path) -> None:
        """Test loading .yml file extension."""
        config_file = tmp_path / "config.yml"
        config_file.write_text(
            """
api_key: test-key
provider: openai
"""
        )

        result = load_config_file(config_file)
        assert result["api_key"] == "test-key"
        assert result["provider"] == "openai"

    def test_load_config_no_section(self, tmp_path: Path) -> None:
        """Test loading config file without ai-decision-council section."""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            """
api_key = "test-key"
provider = "openai"
"""
        )

        result = load_config_file(config_file)
        assert result["api_key"] == "test-key"
        assert result["provider"] == "openai"

    def test_load_config_file_not_found(self, tmp_path: Path) -> None:
        """Test error when config file doesn't exist."""
        config_file = tmp_path / "nonexistent.toml"

        with pytest.raises(FileNotFoundError, match="Config file not found"):
            load_config_file(config_file)

    def test_load_config_is_directory(self, tmp_path: Path) -> None:
        """Test error when config path is a directory."""
        with pytest.raises(ValueError, match="not a file"):
            load_config_file(tmp_path)

    def test_load_config_unsupported_extension(self, tmp_path: Path) -> None:
        """Test error with unsupported file extension."""
        config_file = tmp_path / "config.json"
        config_file.write_text("{}")

        with pytest.raises(ValueError, match="Unsupported config file type"):
            load_config_file(config_file)

    def test_load_invalid_toml(self, tmp_path: Path) -> None:
        """Test error with invalid TOML syntax."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("invalid toml content [[[")

        with pytest.raises(ValueError, match="Failed to parse TOML"):
            load_config_file(config_file)

    def test_load_invalid_yaml(self, tmp_path: Path) -> None:
        """Test error with invalid YAML syntax."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("  invalid:\n    yaml: [broken")

        with pytest.raises(ValueError, match="Failed to parse YAML"):
            load_config_file(config_file)


class TestNormalizeConfigKeys:
    """Tests for normalizing configuration keys."""

    def test_normalize_all_known_keys(self) -> None:
        """Test normalization of all known configuration keys."""
        config = {
            "api_key": "key",
            "api_url": "url",
            "models": ["m1", "m2"],
            "model_count": 2,
            "chairman_model": "m1",
            "title_model": "m1",
            "provider": "openai",
            "max_retries": 3,
            "retry_backoff_seconds": 1.0,
            "stage_timeout_seconds": 60.0,
            "title_timeout_seconds": 15.0,
        }

        result = normalize_config_keys(config)
        assert result["LLM_COUNCIL_API_KEY"] == "key"
        assert result["LLM_COUNCIL_API_URL"] == "url"
        assert result["LLM_COUNCIL_MODELS"] == ["m1", "m2"]
        assert result["LLM_COUNCIL_MODEL_COUNT"] == 2
        assert result["LLM_COUNCIL_CHAIRMAN_MODEL"] == "m1"
        assert result["LLM_COUNCIL_TITLE_MODEL"] == "m1"
        assert result["LLM_COUNCIL_PROVIDER"] == "openai"
        assert result["LLM_COUNCIL_MAX_RETRIES"] == 3
        assert result["LLM_COUNCIL_RETRY_BACKOFF_SECONDS"] == 1.0
        assert result["LLM_COUNCIL_STAGE_TIMEOUT_SECONDS"] == 60.0
        assert result["LLM_COUNCIL_TITLE_TIMEOUT_SECONDS"] == 15.0

    def test_normalize_partial_keys(self) -> None:
        """Test normalization with partial configuration."""
        config = {
            "api_key": "test-key",
            "provider": "ollama",
        }

        result = normalize_config_keys(config)
        assert result["LLM_COUNCIL_API_KEY"] == "test-key"
        assert result["LLM_COUNCIL_PROVIDER"] == "ollama"
        assert "LLM_COUNCIL_MODEL_COUNT" not in result

    def test_normalize_already_normalized_keys(self) -> None:
        """Test that already-normalized keys are preserved."""
        config = {
            "LLM_COUNCIL_API_KEY": "key",
            "LLM_COUNCIL_PROVIDER": "openai",
        }

        result = normalize_config_keys(config)
        assert result["LLM_COUNCIL_API_KEY"] == "key"
        assert result["LLM_COUNCIL_PROVIDER"] == "openai"


class TestMergeConfigSources:
    """Tests for merging configuration sources."""

    def test_merge_file_and_overrides(self) -> None:
        """Test merging file config with explicit overrides."""
        file_config = {
            "api_key": "file-key",
            "provider": "openai",
            "models": ["m1", "m2"],
        }
        overrides = {
            "provider": "anthropic",
            "max_retries": 5,
        }

        result = merge_config_sources(file_config, overrides)
        assert result["api_key"] == "file-key"
        assert result["provider"] == "anthropic"  # Overrides take precedence
        assert result["models"] == ["m1", "m2"]
        assert result["max_retries"] == 5

    def test_merge_only_file(self) -> None:
        """Test merging with only file config."""
        file_config = {
            "api_key": "key",
            "provider": "openai",
        }

        result = merge_config_sources(file_config, None)
        assert result["api_key"] == "key"
        assert result["provider"] == "openai"

    def test_merge_only_overrides(self) -> None:
        """Test merging with only overrides."""
        overrides = {
            "api_key": "key",
            "max_retries": 3,
        }

        result = merge_config_sources(None, overrides)
        assert result["api_key"] == "key"
        assert result["max_retries"] == 3

    def test_merge_both_none(self) -> None:
        """Test merging with no sources."""
        result = merge_config_sources(None, None)
        assert result == {}


class TestCouncilConfigFromFile:
    """Tests for CouncilConfig.from_file() method."""

    def test_from_file_toml(self, tmp_path: Path) -> None:
        """Test loading config from TOML file."""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            """
[ai-decision-council]
api_key = "test-key"
models = ["gpt-4", "gpt-3.5-turbo", "claude-3-opus"]
provider = "openai"
"""
        )

        config = CouncilConfig.from_file(config_file)
        assert config.api_key == "test-key"
        assert config.provider == "openai"
        assert config.models == ["gpt-4", "gpt-3.5-turbo", "claude-3-opus"]

    def test_from_file_yaml(self, tmp_path: Path) -> None:
        """Test loading config from YAML file."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            """
api_key: test-key
provider: anthropic
models:
  - claude-3-opus
  - claude-3-sonnet
"""
        )

        config = CouncilConfig.from_file(config_file)
        assert config.api_key == "test-key"
        assert config.provider == "anthropic"
        assert len(config.models) == 2

    def test_from_file_with_overrides(self, tmp_path: Path) -> None:
        """Test file config with explicit overrides."""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            """
[ai-decision-council]
api_key = "file-key"
provider = "openai"
max_retries = 2
"""
        )

        config = CouncilConfig.from_file(config_file, api_key="override-key", max_retries=5)
        assert config.api_key == "override-key"  # Override takes precedence
        assert config.provider == "openai"
        assert config.max_retries == 5  # Override takes precedence


class TestCouncilConfigFromFileAndEnv:
    """Tests for CouncilConfig.from_file_and_env() method."""

    def test_from_file_and_env_env_precedence(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that env vars take precedence over file config."""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            """
[ai-decision-council]
api_key = "file-key"
provider = "openai"
"""
        )

        # Set env var to override file config
        monkeypatch.setenv("LLM_COUNCIL_PROVIDER", "anthropic")

        config = CouncilConfig.from_file_and_env(config_file)
        # Provider from env takes precedence
        assert config.provider == "anthropic"
        # API key from file when no env var
        assert config.api_key == "file-key"

    def test_from_file_and_env_file_only(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test loading config from file when no env vars are set."""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            """
[ai-decision-council]
api_key = "file-key"
provider = "openai"
models = ["gpt-4", "gpt-3.5-turbo"]
"""
        )

        # Make sure relevant env vars are not set
        monkeypatch.delenv("LLM_COUNCIL_API_KEY", raising=False)
        monkeypatch.delenv("LLM_COUNCIL_PROVIDER", raising=False)
        monkeypatch.delenv("LLM_COUNCIL_MODELS", raising=False)

        config = CouncilConfig.from_file_and_env(config_file)
        assert config.api_key == "file-key"
        assert config.provider == "openai"

    def test_from_file_and_env_no_file(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test fallback to env when no file is provided."""
        monkeypatch.setenv("LLM_COUNCIL_API_KEY", "env-key")
        monkeypatch.setenv("LLM_COUNCIL_PROVIDER", "openai")

        config = CouncilConfig.from_file_and_env(None)
        assert config.api_key == "env-key"
        assert config.provider == "openai"

    def test_from_file_and_env_type_conversion(
        self, tmp_path: Path
    ) -> None:
        """Test that numeric strings in config are converted to correct types."""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            """
[ai-decision-council]
api_key = "test-key"
model_count = 3
max_retries = 2
retry_backoff_seconds = 0.5
stage_timeout_seconds = 120.0
"""
        )

        config = CouncilConfig.from_file_and_env(config_file)
        assert isinstance(config.model_count, int)
        assert isinstance(config.max_retries, int)
        assert isinstance(config.retry_backoff_seconds, float)
        assert isinstance(config.stage_timeout_seconds, float)

    def test_from_file_and_env_models_string_conversion(
        self, tmp_path: Path
    ) -> None:
        """Test that models as comma-separated string is converted to list."""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            """
[ai-decision-council]
api_key = "test-key"
models = "gpt-4,gpt-3.5-turbo,claude"
"""
        )

        config = CouncilConfig.from_file_and_env(config_file)
        assert isinstance(config.models, list)
        assert len(config.models) == 3
