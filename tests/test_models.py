"""Tests for the model catalog constants and boundary values."""

from __future__ import annotations

from ai_decision_council.models import (
    DEFAULT_MODEL_CATALOG,
    DEFAULT_MODEL_COUNT,
    MAX_MODELS,
    MIN_MODELS,
)


class TestModelCatalogConstants:
    def test_default_count_within_bounds(self):
        assert MIN_MODELS <= DEFAULT_MODEL_COUNT <= MAX_MODELS

    def test_catalog_length_at_least_default_count(self):
        assert len(DEFAULT_MODEL_CATALOG) >= DEFAULT_MODEL_COUNT

    def test_catalog_entries_are_strings(self):
        for entry in DEFAULT_MODEL_CATALOG:
            assert isinstance(entry, str)

    def test_catalog_entries_have_slash(self):
        """All entries should follow provider/model-name format."""
        for entry in DEFAULT_MODEL_CATALOG:
            assert "/" in entry, f"{entry!r} is not in provider/model format"

    def test_catalog_entries_no_whitespace(self):
        for entry in DEFAULT_MODEL_CATALOG:
            assert entry == entry.strip(), f"{entry!r} has leading/trailing whitespace"

    def test_no_duplicate_models(self):
        assert len(DEFAULT_MODEL_CATALOG) == len(set(DEFAULT_MODEL_CATALOG))

    def test_min_models_is_positive(self):
        assert MIN_MODELS >= 1

    def test_max_models_greater_than_min(self):
        assert MAX_MODELS > MIN_MODELS
