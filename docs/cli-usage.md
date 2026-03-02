# CLI Usage

## Validate configuration

```bash
ai-decision-council doctor
```

## Show models

```bash
ai-decision-council models --defaults
ai-decision-council models --defaults --count 7
ai-decision-council models
```

## Scaffold integration files

```bash
ai-decision-council init
ai-decision-council init --api fastapi
ai-decision-council bridge --output ./my_bridge.py
```

## Run council

```bash
ai-decision-council run --prompt "Your prompt"
ai-decision-council run --prompt "Your prompt" --json
```

## API utilities

```bash
ai-decision-council api bootstrap --path .
ai-decision-council api serve --host 0.0.0.0 --port 8001
ai-decision-council api openapi --output ./openapi.json
ai-decision-council api sdk --output-dir ./sdk
```

`api bootstrap` scaffolds integration files, writes `.env`, exports OpenAPI, and generates typed Python/TypeScript SDK files in one command.

## Legacy alias

The `llm-council` command is still supported as a compatibility alias.
