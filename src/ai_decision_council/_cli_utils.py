"""Shared utility helpers for CLI modules."""

from __future__ import annotations

import sys
from pathlib import Path


def _write_file(path: Path, content: str, force: bool) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not force:
        print(f"File exists, use --force to overwrite: {path}", file=sys.stderr)
        return False
    path.write_text(content, encoding="utf-8")
    print(f"Created: {path}")
    return True


def _format_model_list(models: list[str]) -> str:
    return "\n".join([f"- {model}" for model in models])
