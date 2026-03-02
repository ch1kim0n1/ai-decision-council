"""Tests for council utility functions: ranking parsing, aggregation, index-to-label."""

from __future__ import annotations

import pytest

from ai_decision_council.council import (
    _index_to_label,
    calculate_aggregate_rankings,
    parse_ranking_from_text,
)

# ---------------------------------------------------------------------------
# _index_to_label
# ---------------------------------------------------------------------------

class TestIndexToLabel:
    def test_zero_is_A(self):
        assert _index_to_label(0) == "A"

    def test_25_is_Z(self):
        assert _index_to_label(25) == "Z"

    def test_26_is_AA(self):
        assert _index_to_label(26) == "AA"

    def test_27_is_AB(self):
        assert _index_to_label(27) == "AB"

    def test_51_is_AZ(self):
        assert _index_to_label(51) == "AZ"

    def test_52_is_BA(self):
        assert _index_to_label(52) == "BA"

    def test_negative_raises(self):
        with pytest.raises(ValueError):
            _index_to_label(-1)

    def test_sequential_unique(self):
        labels = [_index_to_label(i) for i in range(30)]
        assert len(set(labels)) == 30


# ---------------------------------------------------------------------------
# parse_ranking_from_text
# ---------------------------------------------------------------------------

class TestParseRankingFromText:
    def test_parses_final_ranking_section(self):
        text = (
            "Response A is best.\n"
            "FINAL RANKING:\n"
            "1. Response A\n"
            "2. Response B\n"
            "3. Response C\n"
        )
        result = parse_ranking_from_text(text)
        assert result == ["Response A", "Response B", "Response C"]

    def test_falls_back_to_regex_without_section(self):
        text = "I think Response B is best, then Response A."
        result = parse_ranking_from_text(text)
        assert "Response B" in result
        assert "Response A" in result

    def test_empty_text_returns_empty_list(self):
        assert parse_ranking_from_text("") == []

    def test_no_rankings_returns_empty_list(self):
        assert parse_ranking_from_text("There are no responses here.") == []

    def test_handles_trailing_content_after_ranking(self):
        text = (
            "FINAL RANKING:\n"
            "1. Response A\n"
            "2. Response B\n"
            "\nSome extra notes."
        )
        result = parse_ranking_from_text(text)
        assert result[:2] == ["Response A", "Response B"]

    def test_two_responses(self):
        text = "FINAL RANKING:\n1. Response A\n2. Response B"
        result = parse_ranking_from_text(text)
        assert result == ["Response A", "Response B"]

    def test_preserves_order(self):
        text = "FINAL RANKING:\n1. Response C\n2. Response A\n3. Response B"
        result = parse_ranking_from_text(text)
        assert result == ["Response C", "Response A", "Response B"]


# ---------------------------------------------------------------------------
# calculate_aggregate_rankings
# ---------------------------------------------------------------------------

class TestCalculateAggregateRankings:
    def _label_map(self):
        return {
            "Response A": "openai/gpt-4o",
            "Response B": "anthropic/claude-3-haiku",
            "Response C": "google/gemini-flash",
        }

    def _make_stage2(self, rankings: list[str]) -> list[dict]:
        """Create stage2 results where each model provided the same ranking text."""
        return [
            {
                "model": f"model-{i}",
                "ranking": "FINAL RANKING:\n" + "\n".join(
                    f"{pos + 1}. {label}" for pos, label in enumerate(rankings)
                ),
                "parsed_ranking": rankings,
            }
            for i in range(len(rankings))
        ]

    def test_unanimous_top_model_ranks_first(self):
        stage2 = self._make_stage2(["Response A", "Response B", "Response C"])
        result = calculate_aggregate_rankings(stage2, self._label_map())
        top = result[0]
        assert top["model"] == "openai/gpt-4o"

    def test_result_sorted_by_average_rank_ascending(self):
        stage2 = self._make_stage2(["Response A", "Response B", "Response C"])
        result = calculate_aggregate_rankings(stage2, self._label_map())
        avg_ranks = [r["average_rank"] for r in result]
        assert avg_ranks == sorted(avg_ranks)

    def test_includes_rankings_count(self):
        stage2 = self._make_stage2(["Response A", "Response B"])
        result = calculate_aggregate_rankings(stage2, {"Response A": "m1", "Response B": "m2"})
        for entry in result:
            assert "rankings_count" in entry
            assert entry["rankings_count"] > 0

    def test_empty_stage2_returns_empty(self):
        result = calculate_aggregate_rankings([], {})
        assert result == []

    def test_unknown_labels_ignored(self):
        stage2 = [
            {
                "model": "m",
                "ranking": "FINAL RANKING:\n1. Response Z",
                "parsed_ranking": ["Response Z"],
            }
        ]
        result = calculate_aggregate_rankings(stage2, {"Response A": "openai/gpt-4o"})
        # Response Z not in label_map, so nothing should be aggregated
        assert result == []

    def test_average_rank_is_rounded(self):
        stage2 = self._make_stage2(["Response A", "Response B", "Response C"])
        result = calculate_aggregate_rankings(stage2, self._label_map())
        for entry in result:
            assert isinstance(entry["average_rank"], float)
            # Should be rounded to 2 decimal places
            assert round(entry["average_rank"], 2) == entry["average_rank"]

    def test_tied_models_both_present(self):
        # Two models both voted Response A #1 and Response B #2
        label_map = {"Response A": "m1", "Response B": "m2"}
        stage2 = [
            {
                "model": "voter1",
                "ranking": "FINAL RANKING:\n1. Response A\n2. Response B",
                "parsed_ranking": ["Response A", "Response B"],
            },
            {
                "model": "voter2",
                "ranking": "FINAL RANKING:\n1. Response A\n2. Response B",
                "parsed_ranking": ["Response A", "Response B"],
            },
        ]
        result = calculate_aggregate_rankings(stage2, label_map)
        models_in_result = [r["model"] for r in result]
        assert "m1" in models_in_result
        assert "m2" in models_in_result
