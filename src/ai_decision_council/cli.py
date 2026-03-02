"""CLI entrypoints for ai-decision-council package."""

from __future__ import annotations

import argparse
from typing import Sequence, cast

from ._cli_commands import (
    cmd_api_bootstrap,
    cmd_api_openapi,
    cmd_api_sdk,
    cmd_api_serve,
    cmd_bridge,
    cmd_doctor,
    cmd_init,
    cmd_models,
    cmd_run,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ai-decision-council",
        description="CLI for integrating and running the ai-decision-council package.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser(
        "init",
        help="Create integration starter files in your project.",
    )
    init_parser.add_argument(
        "--path",
        default=".",
        help="Target directory for generated files.",
    )
    init_parser.add_argument(
        "--api",
        choices=["bridge", "fastapi", "all"],
        default="bridge",
        help="Scaffold target. `fastapi` creates API module templates.",
    )
    init_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing files.",
    )
    init_parser.set_defaults(func=cmd_init)

    bridge_parser = subparsers.add_parser(
        "bridge",
        help="Generate a project-local bridge module.",
    )
    bridge_parser.add_argument(
        "--output",
        default="ai_decision_council_bridge.py",
        help="Path to generated bridge file.",
    )
    bridge_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing file.",
    )
    bridge_parser.set_defaults(func=cmd_bridge)

    doctor_parser = subparsers.add_parser(
        "doctor",
        help="Validate required runtime configuration.",
    )
    doctor_parser.set_defaults(func=cmd_doctor)

    models_parser = subparsers.add_parser(
        "models",
        help="Print default or currently selected model set.",
    )
    models_parser.add_argument(
        "--defaults",
        action="store_true",
        help="Show curated default model catalog.",
    )
    models_parser.add_argument(
        "--count",
        type=int,
        help="When used with --defaults, show only first N default models.",
    )
    models_parser.set_defaults(func=cmd_models)

    run_parser = subparsers.add_parser(
        "run",
        help="Run the council pipeline for a single prompt.",
    )
    run_parser.add_argument(
        "--prompt",
        "-p",
        required=True,
        help="Prompt to send through the council.",
    )
    run_parser.add_argument(
        "--config",
        "-c",
        help="Path to configuration file (TOML or YAML format).",
    )
    run_parser.add_argument(
        "--json",
        action="store_true",
        help="Print full structured output as JSON.",
    )
    run_parser.set_defaults(func=cmd_run)

    api_parser = subparsers.add_parser(
        "api",
        help="FastAPI integration utilities (bootstrap, serve, schema, SDK).",
    )
    api_subparsers = api_parser.add_subparsers(dest="api_command", required=True)

    bootstrap_parser = api_subparsers.add_parser(
        "bootstrap",
        help="One-command setup: scaffold files, write .env, generate OpenAPI and typed SDK.",
    )
    bootstrap_parser.add_argument(
        "--path",
        default=".",
        help="Target directory for generated files and artifacts.",
    )
    bootstrap_parser.add_argument(
        "--api-scaffold",
        choices=["bridge", "fastapi", "all"],
        default="all",
        help="Which integration files to scaffold before generating artifacts.",
    )
    bootstrap_parser.add_argument(
        "--openapi-output",
        default="openapi.json",
        help="OpenAPI output path relative to --path.",
    )
    bootstrap_parser.add_argument(
        "--sdk-dir",
        default="sdk",
        help="SDK output directory relative to --path.",
    )
    bootstrap_parser.add_argument(
        "--skip-openapi",
        action="store_true",
        help="Skip OpenAPI schema generation.",
    )
    bootstrap_parser.add_argument(
        "--skip-sdk",
        action="store_true",
        help="Skip SDK generation.",
    )
    bootstrap_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing files.",
    )
    bootstrap_parser.set_defaults(func=cmd_api_bootstrap)

    serve_parser = api_subparsers.add_parser("serve", help="Run the packaged FastAPI app.")
    serve_parser.add_argument("--host", default="0.0.0.0")
    serve_parser.add_argument("--port", type=int, default=8001)
    serve_parser.add_argument("--reload", action="store_true")
    serve_parser.add_argument(
        "--config",
        "-c",
        help="Path to configuration file (TOML or YAML format).",
    )
    serve_parser.set_defaults(func=cmd_api_serve)

    openapi_parser = api_subparsers.add_parser(
        "openapi",
        help="Write OpenAPI schema from packaged FastAPI app.",
    )
    openapi_parser.add_argument(
        "--output",
        default="ai_decision_council_openapi.json",
        help="Path to generated OpenAPI JSON file.",
    )
    openapi_parser.add_argument("--force", action="store_true")
    openapi_parser.set_defaults(func=cmd_api_openapi)

    sdk_parser = api_subparsers.add_parser(
        "sdk",
        help="Generate typed Python + TypeScript SDK clients from OpenAPI contract.",
    )
    sdk_parser.add_argument(
        "--output-dir",
        default="./sdk",
        help="Directory where SDK files will be created.",
    )
    sdk_parser.add_argument("--force", action="store_true")
    sdk_parser.set_defaults(func=cmd_api_sdk)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    result = args.func(args)
    return cast(int, result)
