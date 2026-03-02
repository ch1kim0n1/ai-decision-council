"""Structured logging and observability utilities for ai-decision-council.

Usage
-----
    from ai_decision_council.observability import get_logger, configure_logging

    configure_logging(level="INFO", json_mode=False)
    logger = get_logger("council")
    logger.info("stage_start", stage="stage1", model_count=5)

Environment variables
---------------------
    LLM_COUNCIL_LOG_LEVEL   — DEBUG / INFO / WARNING / ERROR (default: INFO)
    LLM_COUNCIL_LOG_JSON    — 1 / true to emit newline-delimited JSON logs
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import sys
import time
from typing import Any, Generator


_LOGGER_NAME = "ai_decision_council"
_configured = False


# ---------------------------------------------------------------------------
# JSON log formatter
# ---------------------------------------------------------------------------

class _JsonFormatter(logging.Formatter):
    """Emit each log record as a single JSON line for log-aggregation pipelines."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        # Merge any extra fields attached via `extra=` kwarg
        for key, value in record.__dict__.items():
            if key not in (
                "name", "levelname", "pathname", "filename", "module",
                "funcName", "lineno", "asctime", "created", "thread",
                "threadName", "process", "processName", "relativeCreated",
                "msecs", "levelno", "args", "msg", "exc_info", "exc_text",
                "stack_info", "taskName",
            ):
                payload[key] = value

        return json.dumps(payload, default=str)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def configure_logging(
    level: str | int | None = None,
    json_mode: bool | None = None,
) -> None:
    """Configure the package-level logger.

    Call once at application startup.  Subsequent calls are no-ops unless
    ``force=True`` is passed (private API, for tests).

    Parameters
    ----------
    level:
        Log level string or integer.  Defaults to ``LLM_COUNCIL_LOG_LEVEL``
        env var, falling back to ``INFO``.
    json_mode:
        Emit JSON logs.  Defaults to ``LLM_COUNCIL_LOG_JSON`` env var.
    """
    global _configured
    if _configured:
        return

    _log_level = level or os.getenv("LLM_COUNCIL_LOG_LEVEL", "INFO")
    _json_mode = json_mode
    if _json_mode is None:
        _json_mode = os.getenv("LLM_COUNCIL_LOG_JSON", "0").lower() in ("1", "true", "yes")

    root_logger = logging.getLogger(_LOGGER_NAME)
    root_logger.setLevel(_log_level)

    if not root_logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        if _json_mode:
            handler.setFormatter(_JsonFormatter())
        else:
            handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s [%(levelname)s] %(name)s - %(message)s",
                    datefmt="%Y-%m-%dT%H:%M:%S",
                )
            )
        root_logger.addHandler(handler)

    root_logger.propagate = False
    _configured = True


def _reconfigure_logging(
    level: str | int | None = None,
    json_mode: bool | None = None,
) -> None:
    """Force-reset configuration.  Intended for test isolation only."""
    global _configured
    _configured = False
    pkg_logger = logging.getLogger(_LOGGER_NAME)
    pkg_logger.handlers.clear()
    configure_logging(level=level, json_mode=json_mode)


def get_logger(name: str | None = None) -> "CouncilLogger":
    """Return a ``CouncilLogger`` wrapping the named child logger.

    Parameters
    ----------
    name:
        Sub-logger name, e.g. ``"council"``, ``"providers"``.
        Defaults to the root package logger.
    """
    full_name = f"{_LOGGER_NAME}.{name}" if name else _LOGGER_NAME
    return CouncilLogger(logging.getLogger(full_name))


class CouncilLogger:
    """Thin wrapper that adds structured key-value fields to log records."""

    def __init__(self, inner: logging.Logger) -> None:
        self._inner = inner

    # ------------------------------------------------------------------
    # Convenience level methods
    # ------------------------------------------------------------------

    def debug(self, event: str, **fields: Any) -> None:
        self._emit(logging.DEBUG, event, fields)

    def info(self, event: str, **fields: Any) -> None:
        self._emit(logging.INFO, event, fields)

    def warning(self, event: str, **fields: Any) -> None:
        self._emit(logging.WARNING, event, fields)

    def error(self, event: str, **fields: Any) -> None:
        self._emit(logging.ERROR, event, fields)

    def exception(self, event: str, **fields: Any) -> None:
        self._inner.exception(event, extra=fields)

    # ------------------------------------------------------------------
    # Stage-specific helpers
    # ------------------------------------------------------------------

    def stage_start(self, stage: str, **fields: Any) -> None:
        self.info(f"{stage}_start", stage=stage, **fields)

    def stage_complete(self, stage: str, duration_ms: float, **fields: Any) -> None:
        self.info(f"{stage}_complete", stage=stage, duration_ms=round(duration_ms, 1), **fields)

    def stage_error(self, stage: str, error: str, **fields: Any) -> None:
        self.error(f"{stage}_error", stage=stage, error=error, **fields)

    def model_call_start(self, model: str, stage: str) -> None:
        self.debug("model_call_start", model=model, stage=stage)

    def model_call_complete(self, model: str, stage: str, duration_ms: float) -> None:
        self.debug("model_call_complete", model=model, stage=stage, duration_ms=round(duration_ms, 1))

    def model_call_error(self, model: str, stage: str, error_code: str, message: str) -> None:
        self.warning("model_call_error", model=model, stage=stage, error_code=error_code, error_message=message)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _emit(self, level: int, event: str, fields: dict[str, Any]) -> None:
        if self._inner.isEnabledFor(level):
            self._inner.log(level, event, extra=fields)


# ---------------------------------------------------------------------------
# Timing context manager
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def timed_stage(logger: CouncilLogger, stage: str, **fields: Any) -> Generator[None, None, None]:
    """Context manager that logs stage start + complete with wall-clock duration.

    Example::

        with timed_stage(log, "stage1", model_count=5, query_len=120):
            results = await stage1_collect_responses(...)
    """
    logger.stage_start(stage, **fields)
    t0 = time.perf_counter()
    try:
        yield
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.stage_error(stage, str(exc), duration_ms=round(elapsed_ms, 1), **fields)
        raise
    else:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.stage_complete(stage, elapsed_ms, **fields)
