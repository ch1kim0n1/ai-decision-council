"""Tests for CouncilResult and ModelRunError schema objects."""

from __future__ import annotations

from ai_decision_council.schemas import CouncilResult, ModelRunError


# ---------------------------------------------------------------------------
# ModelRunError
# ---------------------------------------------------------------------------

class TestModelRunError:
    def _make(self, **kwargs) -> ModelRunError:
        defaults = {
            "model": "openai/gpt-4o",
            "stage": "stage1",
            "error_code": "provider_timeout_error",
            "message": "Timed out after 120s",
        }
        defaults.update(kwargs)
        return ModelRunError(**defaults)

    def test_to_dict_all_fields(self):
        err = self._make()
        d = err.to_dict()
        assert d["model"] == "openai/gpt-4o"
        assert d["stage"] == "stage1"
        assert d["error_code"] == "provider_timeout_error"
        assert d["message"] == "Timed out after 120s"

    def test_to_dict_keys(self):
        err = self._make()
        assert set(err.to_dict().keys()) == {"model", "stage", "error_code", "message"}

    def test_different_stages(self):
        for stage in ("stage1", "stage2", "stage3", "title"):
            err = self._make(stage=stage)
            assert err.to_dict()["stage"] == stage


# ---------------------------------------------------------------------------
# CouncilResult
# ---------------------------------------------------------------------------

STAGE1_SAMPLE = [{"model": "openai/gpt-4o", "response": "Answer A"}]
STAGE2_SAMPLE = [{"model": "openai/gpt-4o", "ranking": "FINAL RANKING:\n1. Response A"}]
STAGE3_SAMPLE = {"model": "openai/gpt-4o", "response": "Synthesized answer"}
META_SAMPLE = {"label_to_model": {"Response A": "openai/gpt-4o"}, "aggregate_rankings": []}


def _make_result(**kwargs) -> CouncilResult:
    defaults = {
        "stage1": STAGE1_SAMPLE,
        "stage2": STAGE2_SAMPLE,
        "stage3": STAGE3_SAMPLE,
        "metadata": META_SAMPLE,
        "errors": [],
    }
    defaults.update(kwargs)
    return CouncilResult(**defaults)


class TestCouncilResultProperties:
    def test_final_response_returns_stage3_response(self):
        r = _make_result()
        assert r.final_response == "Synthesized answer"

    def test_final_response_empty_when_missing(self):
        r = _make_result(stage3={})
        assert r.final_response == ""

    def test_final_model_returns_stage3_model(self):
        r = _make_result()
        assert r.final_model == "openai/gpt-4o"

    def test_final_model_empty_when_missing(self):
        r = _make_result(stage3={"response": "x"})
        assert r.final_model == ""

    def test_default_errors_is_empty_list(self):
        r = CouncilResult(
            stage1=STAGE1_SAMPLE,
            stage2=STAGE2_SAMPLE,
            stage3=STAGE3_SAMPLE,
            metadata=META_SAMPLE,
        )
        assert r.errors == []


class TestCouncilResultToDict:
    def test_roundtrip_keys(self):
        r = _make_result()
        d = r.to_dict()
        assert set(d.keys()) == {"stage1", "stage2", "stage3", "metadata", "errors"}

    def test_errors_serialized(self):
        err = ModelRunError(
            model="m", stage="stage1", error_code="e", message="msg"
        )
        r = _make_result(errors=[err])
        d = r.to_dict()
        assert len(d["errors"]) == 1
        assert d["errors"][0]["model"] == "m"

    def test_empty_errors_serialized_as_list(self):
        r = _make_result()
        d = r.to_dict()
        assert d["errors"] == []

    def test_stage1_preserved(self):
        r = _make_result()
        assert r.to_dict()["stage1"] == STAGE1_SAMPLE

    def test_metadata_preserved(self):
        r = _make_result()
        assert r.to_dict()["metadata"] == META_SAMPLE
