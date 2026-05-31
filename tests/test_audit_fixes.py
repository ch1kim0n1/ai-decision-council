"""Regression tests for audit fixes (issues #21, #22, #23, #25)."""

from __future__ import annotations

import importlib.metadata
import inspect
from pathlib import Path

import pytest

import ai_decision_council
from ai_decision_council.api.fastapi.backends import StaticTokenAuthBackend
from ai_decision_council.config import CouncilConfig
from ai_decision_council.config_loader import normalize_config_keys
from ai_decision_council.providers.openai import OpenAIAdapter


# ---------------------------------------------------------------------------
# Issue #22 — __version__ exposed and single-sourced from metadata
# ---------------------------------------------------------------------------
class TestVersion:
    def test_version_attribute_exists(self) -> None:
        assert hasattr(ai_decision_council, "__version__")
        assert isinstance(ai_decision_council.__version__, str)
        assert ai_decision_council.__version__

    def test_version_in_all(self) -> None:
        assert "__version__" in ai_decision_council.__all__

    def test_version_matches_installed_metadata(self) -> None:
        try:
            expected = importlib.metadata.version("ai-decision-council")
        except importlib.metadata.PackageNotFoundError:
            pytest.skip("package not installed")
        assert ai_decision_council.__version__ == expected


# ---------------------------------------------------------------------------
# Issue #21 — tomli is a runtime dependency on Python < 3.11 and TOML loads
# ---------------------------------------------------------------------------
class TestTomlRuntimeDep:
    def test_tomli_in_runtime_dependencies(self) -> None:
        """tomli must be declared in base runtime deps (not just dev)."""
        meta = importlib.metadata.metadata("ai-decision-council")
        requires = meta.get_all("Requires-Dist") or []
        tomli_runtime = [
            r
            for r in requires
            if r.lower().startswith("tomli")
            and "extra ==" not in r.replace('"', "").replace("'", "")
        ]
        assert tomli_runtime, f"tomli not in runtime deps; got: {requires}"

    def test_from_file_toml_loads(self, tmp_path: Path) -> None:
        """TOML config loads on any supported Python (exercises tomllib/tomli)."""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            '[ai-decision-council]\n'
            'api_key = "k"\n'
            'models = ["m1", "m2"]\n'
        )
        config = CouncilConfig.from_file(config_file)
        assert config.api_key == "k"
        assert config.models == ["m1", "m2"]


# ---------------------------------------------------------------------------
# Issue #23 — constant-time token comparison
# ---------------------------------------------------------------------------
class TestConstantTimeTokenComparison:
    def test_uses_hmac_compare_digest(self) -> None:
        src = inspect.getsource(StaticTokenAuthBackend)
        assert "compare_digest" in src

    def test_valid_token_accepted(self) -> None:
        backend = StaticTokenAuthBackend(tokens={"secret"})
        assert backend._is_valid("secret") is True

    def test_invalid_token_rejected(self) -> None:
        backend = StaticTokenAuthBackend(tokens={"secret"})
        assert backend._is_valid("wrong") is False

    def test_no_tokens_rejects(self) -> None:
        backend = StaticTokenAuthBackend(tokens=set())
        assert backend._is_valid("anything") is False

    def test_one_of_many_accepted(self) -> None:
        backend = StaticTokenAuthBackend(tokens={"a", "b", "c"})
        assert backend._is_valid("b") is True
        assert backend._is_valid("z") is False


# ---------------------------------------------------------------------------
# Issue #25 — docstrings match implementation
# ---------------------------------------------------------------------------
class TestDocstringAccuracy:
    def test_openai_adapter_docstring_no_auth_header_claim(self) -> None:
        doc = OpenAIAdapter.__doc__ or ""
        # Must not claim it changes the auth header.
        assert "change the default base URL and auth header" not in doc
        assert "only override the default base URL" in doc

    def test_normalize_config_keys_examples_are_prefixed(self) -> None:
        doc = normalize_config_keys.__doc__ or ""
        assert "api_key -> LLM_COUNCIL_API_KEY" in doc
        # The old, wrong example must be gone.
        assert "api_key -> API_KEY" not in doc

    def test_normalize_config_keys_actual_mapping(self) -> None:
        result = normalize_config_keys({"api_key": "k", "model_count": 3})
        assert result["LLM_COUNCIL_API_KEY"] == "k"
        assert result["LLM_COUNCIL_MODEL_COUNT"] == 3
