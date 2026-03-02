"""Tests for the structured logging / observability module."""

from __future__ import annotations

import json
import logging
import os
import time
from io import StringIO
from unittest.mock import patch

import pytest

from ai_decision_council.observability import (
    CouncilLogger,
    _JsonFormatter,
    _LOGGER_NAME,
    configure_logging,
    get_logger,
    timed_stage,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reset_configured():
    """Reset the module-level _configured flag between tests."""
    import ai_decision_council.observability as obs
    obs._configured = False
    # Remove all handlers from the root logger so tests are isolated
    root = logging.getLogger(_LOGGER_NAME)
    root.handlers.clear()
    root.propagate = False


# ---------------------------------------------------------------------------
# configure_logging
# ---------------------------------------------------------------------------

class TestConfigureLogging:
    def setup_method(self):
        _reset_configured()

    def test_configure_sets_level_info_by_default(self):
        with patch.dict(os.environ, {"LLM_COUNCIL_LOG_LEVEL": "INFO"}, clear=False):
            configure_logging()
        logger = logging.getLogger(_LOGGER_NAME)
        assert logger.level == logging.INFO

    def test_configure_sets_level_debug(self):
        configure_logging(level="DEBUG")
        logger = logging.getLogger(_LOGGER_NAME)
        assert logger.level == logging.DEBUG

    def test_configure_is_idempotent(self):
        configure_logging(level="DEBUG")
        configure_logging(level="ERROR")  # second call should be a no-op
        logger = logging.getLogger(_LOGGER_NAME)
        assert logger.level == logging.DEBUG  # still DEBUG from first call

    def test_configure_json_mode_via_env(self):
        _reset_configured()
        with patch.dict(os.environ, {"LLM_COUNCIL_LOG_JSON": "1"}, clear=False):
            configure_logging()
        root = logging.getLogger(_LOGGER_NAME)
        handlers_with_json = [
            h for h in root.handlers if isinstance(h.formatter, _JsonFormatter)
        ]
        assert len(handlers_with_json) == 1

    def test_configure_plain_mode_by_default(self):
        with patch.dict(os.environ, {"LLM_COUNCIL_LOG_JSON": "0"}, clear=False):
            configure_logging()
        root = logging.getLogger(_LOGGER_NAME)
        json_handlers = [
            h for h in root.handlers if isinstance(h.formatter, _JsonFormatter)
        ]
        assert len(json_handlers) == 0


# ---------------------------------------------------------------------------
# get_logger / CouncilLogger
# ---------------------------------------------------------------------------

class TestGetLogger:
    def test_returns_council_logger(self):
        log = get_logger("test")
        assert isinstance(log, CouncilLogger)

    def test_logger_name_is_namespaced(self):
        log = get_logger("council")
        assert log._inner.name == f"{_LOGGER_NAME}.council"

    def test_same_name_returns_same_logger(self):
        a = get_logger("duplicate")
        b = get_logger("duplicate")
        assert a._inner is b._inner


# ---------------------------------------------------------------------------
# CouncilLogger methods
# ---------------------------------------------------------------------------

class TestCouncilLoggerMethods:
    """Verify each log-level method emits the right level and merges fields."""

    def setup_method(self):
        _reset_configured()
        self.stream = StringIO()
        configure_logging(level="DEBUG", json_mode=True)
        # Redirect the handler stream to our StringIO
        root = logging.getLogger(_LOGGER_NAME)
        for h in root.handlers:
            h.stream = self.stream

    def _get_records(self) -> list[dict]:
        lines = [l.strip() for l in self.stream.getvalue().splitlines() if l.strip()]
        return [json.loads(l) for l in lines]

    def test_info_emits_record(self):
        log = get_logger("test.info")
        log.info("some_event", foo="bar")
        records = self._get_records()
        assert len(records) == 1
        assert records[0]["message"] == "some_event"
        assert records[0]["foo"] == "bar"

    def test_debug_emits_record(self):
        log = get_logger("test.debug")
        log.debug("dbg_event", x=1)
        records = self._get_records()
        assert any(r["message"] == "dbg_event" for r in records)

    def test_warning_emits_record(self):
        log = get_logger("test.warning")
        log.warning("warn_event")
        records = self._get_records()
        assert any(r["level"] == "WARNING" for r in records)

    def test_error_emits_record(self):
        log = get_logger("test.error")
        log.error("err_event", code="E001")
        records = self._get_records()
        assert any(r["message"] == "err_event" for r in records)

    def test_stage_start(self):
        log = get_logger("test.stage_start")
        log.stage_start("stage1", model_count=5)
        records = self._get_records()
        assert any(r.get("stage") == "stage1" for r in records)

    def test_stage_complete(self):
        log = get_logger("test.stage_complete")
        log.stage_complete("stage2", duration_ms=150.3, results=4)
        records = self._get_records()
        assert any(r.get("stage") == "stage2" and r.get("results") == 4 for r in records)

    def test_model_call_start(self):
        log = get_logger("test.model_start")
        log.model_call_start(model="gpt-4o", stage="stage1")
        records = self._get_records()
        assert any(r.get("model") == "gpt-4o" for r in records)

    def test_model_call_complete(self):
        log = get_logger("test.model_complete")
        log.model_call_complete(model="claude-3", stage="stage1", duration_ms=200.0)
        records = self._get_records()
        assert any(r.get("model") == "claude-3" for r in records)

    def test_model_call_error(self):
        log = get_logger("test.model_error")
        log.model_call_error(model="bad-model", stage="stage2", error_code="auth_error", message="msg")
        records = self._get_records()
        assert any(r.get("error_code") == "auth_error" for r in records)


# ---------------------------------------------------------------------------
# timed_stage context manager
# ---------------------------------------------------------------------------

class TestTimedStage:
    def setup_method(self):
        _reset_configured()

    def test_timed_stage_logs_start_and_complete(self):
        stream = StringIO()
        configure_logging(level="DEBUG", json_mode=True)
        root = logging.getLogger(_LOGGER_NAME)
        for h in root.handlers:
            h.stream = stream

        log = get_logger("timed")
        with timed_stage(log, "stage1", foo="bar"):
            pass

        lines = [l for l in stream.getvalue().splitlines() if l.strip()]
        records = [json.loads(l) for l in lines]
        stages = [r.get("stage") for r in records]
        assert "stage1" in stages

    def test_timed_stage_logs_error_on_exception(self):
        stream = StringIO()
        _reset_configured()
        configure_logging(level="DEBUG", json_mode=True)
        root = logging.getLogger(_LOGGER_NAME)
        for h in root.handlers:
            h.stream = stream

        log = get_logger("timed_error")
        with pytest.raises(ValueError):
            with timed_stage(log, "stage3"):
                raise ValueError("boom")

        lines = [l for l in stream.getvalue().splitlines() if l.strip()]
        records = [json.loads(l) for l in lines]
        levels = [r.get("level") for r in records]
        assert "ERROR" in levels

    def test_timed_stage_elapsed_positive(self):
        stream = StringIO()
        _reset_configured()
        configure_logging(level="DEBUG", json_mode=True)
        root = logging.getLogger(_LOGGER_NAME)
        for h in root.handlers:
            h.stream = stream

        log = get_logger("timed_elapsed")
        with timed_stage(log, "stage2"):
            time.sleep(0.01)

        lines = [l for l in stream.getvalue().splitlines() if l.strip()]
        records = [json.loads(l) for l in lines]
        # The complete record should have duration_ms
        complete_recs = [r for r in records if "duration_ms" in r]
        assert complete_recs, "Expected a record with duration_ms"
        assert complete_recs[0]["duration_ms"] > 0


# ---------------------------------------------------------------------------
# _JsonFormatter
# ---------------------------------------------------------------------------

class TestJsonFormatter:
    def test_format_returns_valid_json(self):
        formatter = _JsonFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO,
            pathname="", lineno=0, msg="hello", args=(), exc_info=None
        )
        result = formatter.format(record)
        parsed = json.loads(result)
        assert parsed["message"] == "hello"
        assert parsed["level"] == "INFO"

    def test_format_includes_extra_fields(self):
        formatter = _JsonFormatter()
        record = logging.LogRecord(
            name="test", level=logging.DEBUG,
            pathname="", lineno=0, msg="ev", args=(), exc_info=None
        )
        record.custom_key = "custom_val"
        result = formatter.format(record)
        parsed = json.loads(result)
        assert parsed.get("custom_key") == "custom_val"
