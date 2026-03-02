"""CLI command handler functions."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import secrets
import sys
from pathlib import Path
from typing import Any, Callable, cast

from dotenv import load_dotenv

from ._cli_sdk import _write_sdk_files
from ._cli_templates import (
    BRIDGE_TEMPLATE,
    ENV_TEMPLATE,
    FASTAPI_EMBED_TEMPLATE,
    FASTAPI_STANDALONE_TEMPLATE,
)
from ._cli_utils import _format_model_list, _write_file
from .client import Council
from .config import CouncilConfig
from .models import DEFAULT_MODEL_CATALOG, MAX_MODELS, MIN_MODELS


def cmd_init(args: argparse.Namespace) -> int:
    target_dir = Path(args.path).resolve()
    env_path = target_dir / ".env.ai-decision-council.example"
    wrote: list[bool] = [_write_file(env_path, ENV_TEMPLATE, force=args.force)]

    if args.api in {"bridge", "all"}:
        bridge_path = target_dir / "ai_decision_council_bridge.py"
        wrote.append(_write_file(bridge_path, BRIDGE_TEMPLATE, force=args.force))

    if args.api in {"fastapi", "all"}:
        wrote.extend(
            [
                _write_file(
                    target_dir / "ai_decision_council_fastapi_app.py",
                    FASTAPI_STANDALONE_TEMPLATE,
                    force=args.force,
                ),
                _write_file(
                    target_dir / "ai_decision_council_fastapi_embedded.py",
                    FASTAPI_EMBED_TEMPLATE,
                    force=args.force,
                ),
            ]
        )

    return 0 if all(wrote) else 1


def cmd_bridge(args: argparse.Namespace) -> int:
    output_path = Path(args.output).resolve()
    success = _write_file(output_path, BRIDGE_TEMPLATE, force=args.force)
    return 0 if success else 1


def cmd_doctor(_args: argparse.Namespace) -> int:
    load_dotenv()

    try:
        config = CouncilConfig.from_env()
    except ValueError as exc:
        print(f"Configuration invalid: {exc}", file=sys.stderr)
        return 1

    print("AI Decision Council doctor report")
    print(f"- API key configured: {'yes' if bool(config.api_key) else 'no'}")
    print(f"- Provider: {config.provider}")
    print(f"- Models configured: {len(config.models or [])}")
    print(f"- Chairman model: {config.chairman_model or 'unset'}")
    print(f"- Title model: {config.title_model or 'unset'}")
    print(f"- API URL: {config.api_url}")
    print(f"- Retries: {config.max_retries}")

    if not config.api_key:
        print(
            "Missing LLM_COUNCIL_API_KEY (or OPENROUTER_API_KEY fallback).",
            file=sys.stderr,
        )
        return 1

    models = config.models or []
    if len(models) < MIN_MODELS or len(models) > MAX_MODELS:
        print(
            f"Model count must be between {MIN_MODELS} and {MAX_MODELS}.",
            file=sys.stderr,
        )
        return 1

    chairman = config.chairman_model or ""
    if chairman not in models:
        print(
            "chairman_model must be present in selected model list.",
            file=sys.stderr,
        )
        return 1

    return 0


def cmd_models(args: argparse.Namespace) -> int:
    if args.defaults:
        if args.count is not None:
            if args.count < MIN_MODELS or args.count > MAX_MODELS:
                print(
                    f"count must be between {MIN_MODELS} and {MAX_MODELS}",
                    file=sys.stderr,
                )
                return 1
            selected = DEFAULT_MODEL_CATALOG[: args.count]
            print(_format_model_list(selected))
            return 0

        print(_format_model_list(DEFAULT_MODEL_CATALOG))
        return 0

    try:
        config = CouncilConfig.from_env()
    except ValueError as exc:
        print(f"Configuration invalid: {exc}", file=sys.stderr)
        return 1

    print(_format_model_list(list(config.models or [])))
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    load_dotenv()

    try:
        if hasattr(args, 'config') and args.config:
            # Load config from file, with environment variable precedence
            from .config import CouncilConfig
            config = CouncilConfig.from_file_and_env(args.config)
            council = Council(config=config)
        else:
            council = Council.from_env()
    except ValueError as exc:
        print(f"Configuration invalid: {exc}", file=sys.stderr)
        return 1

    if not council.config.api_key:
        print(
            "Missing LLM_COUNCIL_API_KEY. Run `ai-decision-council doctor` for setup help.",
            file=sys.stderr,
        )
        return 1

    try:
        result = asyncio.run(council.run(args.prompt))
    except Exception as exc:  # pragma: no cover - runtime safety
        print(f"Council run failed: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(result.final_response)
    return 0


def _import_fastapi_integration():
    try:
        from .api.fastapi import APISettings, create_app
    except Exception as exc:  # pragma: no cover - import guard
        print(
            "FastAPI integration unavailable. Install with `pip install ai-decision-council[api]`.",
            file=sys.stderr,
        )
        print(f"Import error: {exc}", file=sys.stderr)
        return None, None
    return APISettings, create_app


def cmd_api_serve(args: argparse.Namespace) -> int:
    load_dotenv()
    _settings_cls, create_app = _import_fastapi_integration()
    if create_app is None:
        return 1

    try:
        import uvicorn
    except Exception as exc:  # pragma: no cover - import guard
        print(f"Unable to import uvicorn: {exc}", file=sys.stderr)
        return 1

    # Create a council factory that respects config file if provided
    council_factory: Callable[[], Council] | None
    if hasattr(args, 'config') and args.config:
        from .config import CouncilConfig
        def council_factory_impl() -> Council:
            config = CouncilConfig.from_file_and_env(args.config)
            return Council(config=config)
        council_factory = council_factory_impl
    else:
        council_factory = None  # Use default

    app = create_app(council_factory=council_factory)
    uvicorn.run(app, host=args.host, port=args.port, reload=args.reload)
    return 0


def cmd_api_openapi(args: argparse.Namespace) -> int:
    load_dotenv()
    schema = _resolve_openapi_schema()
    if schema is None:
        return 1

    output_path = Path(args.output).resolve()
    success = _write_file(
        output_path,
        json.dumps(schema, indent=2) + "\n",
        force=args.force,
    )
    return 0 if success else 1


def _detect_api_prefix(schema: dict[str, Any]) -> str:
    for path in schema.get("paths", {}):
        if path.endswith("/conversations"):
            return cast(str, path[: -len("/conversations")])
    return "/v1"


def _resolve_openapi_schema() -> dict[str, Any] | None:
    _settings_cls, create_app = _import_fastapi_integration()
    if create_app is None:
        return None
    app = create_app()
    schema = app.openapi()
    return cast(dict[str, Any] | None, schema)

def cmd_api_sdk(args: argparse.Namespace) -> int:
    load_dotenv()
    schema = _resolve_openapi_schema()
    if schema is None:
        return 1

    prefix = _detect_api_prefix(schema)
    output_dir = Path(args.output_dir).resolve()
    success = _write_sdk_files(output_dir, prefix=prefix, force=args.force)
    return 0 if success else 1


def _render_bootstrap_env(*, api_key: str, api_token: str) -> str:
    resolved_key = api_key.strip() if api_key.strip() else "replace-me"
    return f"""# Generated by `ai-decision-council api bootstrap`
# Replace API key if this file contains `replace-me`.
LLM_COUNCIL_API_KEY={resolved_key}
LLM_COUNCIL_REFERENCE_API_TOKEN={api_token}
VITE_REFERENCE_API_TOKEN={api_token}
LLM_COUNCIL_MODEL_COUNT=5
LLM_COUNCIL_API_PREFIX=/v1
"""


def cmd_api_bootstrap(args: argparse.Namespace) -> int:
    load_dotenv()
    target_dir = Path(args.path).resolve()

    init_args = argparse.Namespace(path=str(target_dir), api=args.api_scaffold, force=args.force)
    if cmd_init(init_args) != 0:
        return 1

    api_key = os.getenv("LLM_COUNCIL_API_KEY") or os.getenv("OPENROUTER_API_KEY") or ""
    api_token = os.getenv("LLM_COUNCIL_REFERENCE_API_TOKEN") or secrets.token_urlsafe(24)
    wrote_env = _write_file(
        target_dir / ".env",
        _render_bootstrap_env(api_key=api_key, api_token=api_token),
        force=args.force,
    )
    if not wrote_env:
        return 1

    if args.skip_openapi and args.skip_sdk:
        return 0

    schema = _resolve_openapi_schema()
    if schema is None:
        return 1

    if not args.skip_openapi:
        wrote_openapi = _write_file(
            target_dir / args.openapi_output,
            json.dumps(schema, indent=2) + "\n",
            force=args.force,
        )
        if not wrote_openapi:
            return 1

    if not args.skip_sdk:
        prefix = _detect_api_prefix(schema)
        wrote_sdk = _write_sdk_files(
            (target_dir / args.sdk_dir).resolve(),
            prefix=prefix,
            force=args.force,
        )
        if not wrote_sdk:
            return 1

    return 0

