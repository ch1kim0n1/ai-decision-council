# Troubleshooting

## `doctor` says API key missing

Set one of:

- `LLM_COUNCIL_API_KEY` (preferred; OpenRouter API key)
- `OPENROUTER_API_KEY` (legacy fallback; same OpenRouter key)

## Model count validation errors

- `LLM_COUNCIL_MODEL_COUNT` must be between `2` and `20`.
- If `LLM_COUNCIL_MODELS` is set, it must include at least 2 models.

## Chairman model errors

`LLM_COUNCIL_CHAIRMAN_MODEL` must be part of selected model list.

## Sync method fails in async runtime

Use async methods (`await council.run(...)`) instead of `run_sync` in environments with active event loops.

## Partial failures in results

Inspect:

- `result.errors`
- `result.metadata["errors"]`

Runs continue when some models fail; they fail only if all stage-1 models fail.

## API returns unauthorized

Set:

- `LLM_COUNCIL_REFERENCE_API_TOKEN` (or `LLM_COUNCIL_REFERENCE_API_KEYS`)

And pass it as `Authorization: Bearer <token>` in API requests.
