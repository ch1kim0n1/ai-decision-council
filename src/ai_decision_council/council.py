"""3-stage council orchestration with provider abstraction and partial-failure handling."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Tuple

from .config import CouncilConfig
from .observability import get_logger
from .providers.base import ProviderAdapter, ProviderError
from .providers.openrouter import OpenRouterAdapter
from .schemas import ModelRunError

_log = get_logger("council")


def _index_to_label(index: int) -> str:
    """
    Convert a zero-based index to alphabetical label sequence.

    Examples:
        0 -> A
        25 -> Z
        26 -> AA
        27 -> AB
    """
    if index < 0:
        raise ValueError("index must be non-negative")

    label = []
    n = index
    while True:
        n, remainder = divmod(n, 26)
        label.append(chr(65 + remainder))
        if n == 0:
            break
        n -= 1
    return "".join(reversed(label))


def _default_adapter(config: CouncilConfig) -> ProviderAdapter:
    return OpenRouterAdapter(
        api_key=config.api_key,
        api_url=config.api_url,
        max_retries=config.max_retries,
        retry_backoff_seconds=config.retry_backoff_seconds,
    )


async def _chat_single_model(
    adapter: ProviderAdapter,
    model: str,
    messages: List[Dict[str, str]],
    timeout: float,
    stage: str,
) -> Tuple[str, Dict[str, Any] | None, ModelRunError | None]:
    _log.model_call_start(model=model, stage=stage)
    t0 = time.perf_counter()
    try:
        response = await adapter.chat(model=model, messages=messages, timeout=timeout)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        _log.model_call_complete(model=model, stage=stage, duration_ms=elapsed_ms)
        return (
            model,
            {
                "content": response.content,
                "reasoning_details": response.reasoning_details,
            },
            None,
        )
    except ProviderError as exc:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        _log.model_call_error(model=model, stage=stage, error_code=exc.code, message=str(exc))
        return (
            model,
            None,
            ModelRunError(
                model=model,
                stage=stage,
                error_code=exc.code,
                message=str(exc),
            ),
        )
    except Exception as exc:  # pragma: no cover - defensive guard
        elapsed_ms = (time.perf_counter() - t0) * 1000
        _log.model_call_error(model=model, stage=stage, error_code="unexpected_error", message=str(exc))
        return (
            model,
            None,
            ModelRunError(
                model=model,
                stage=stage,
                error_code="unexpected_error",
                message=str(exc),
            ),
        )


async def _chat_models_parallel(
    adapter: ProviderAdapter,
    models: List[str],
    messages: List[Dict[str, str]],
    timeout: float,
    stage: str,
) -> Tuple[Dict[str, Dict[str, Any]], List[ModelRunError]]:
    import asyncio

    tasks = [
        _chat_single_model(
            adapter=adapter,
            model=model,
            messages=messages,
            timeout=timeout,
            stage=stage,
        )
        for model in models
    ]
    results = await asyncio.gather(*tasks)

    responses: Dict[str, Dict[str, Any]] = {}
    errors: List[ModelRunError] = []
    for model, response, error in results:
        if response is not None:
            responses[model] = response
        if error is not None:
            errors.append(error)
    return responses, errors


async def _stage1_collect_responses_internal(
    user_query: str,
    models: List[str],
    adapter: ProviderAdapter,
    timeout: float,
) -> Tuple[List[Dict[str, Any]], List[ModelRunError]]:
    messages = [{"role": "user", "content": user_query}]
    responses, errors = await _chat_models_parallel(
        adapter=adapter,
        models=models,
        messages=messages,
        timeout=timeout,
        stage="stage1",
    )

    stage1_results = [
        {"model": model, "response": response.get("content", "")}
        for model, response in responses.items()
    ]
    return stage1_results, errors


async def _stage2_collect_rankings_internal(
    user_query: str,
    stage1_results: List[Dict[str, Any]],
    models: List[str],
    adapter: ProviderAdapter,
    timeout: float,
) -> Tuple[List[Dict[str, Any]], Dict[str, str], List[ModelRunError]]:
    labels = [_index_to_label(i) for i in range(len(stage1_results))]
    label_to_model = {
        f"Response {label}": result["model"]
        for label, result in zip(labels, stage1_results)
    }

    responses_text = "\n\n".join(
        [
            f"Response {label}:\n{result['response']}"
            for label, result in zip(labels, stage1_results)
        ]
    )

    ranking_prompt = f"""You are evaluating different responses to the following question:

Question: {user_query}

Here are the responses from different models (anonymized):

{responses_text}

Your task:
1. First, evaluate each response individually. For each response, explain what it does well and what it does poorly.
2. Then, at the very end of your response, provide a final ranking.

IMPORTANT: Your final ranking MUST be formatted EXACTLY as follows:
- Start with the line "FINAL RANKING:" (all caps, with colon)
- Then list the responses from best to worst as a numbered list
- Each line should be: number, period, space, then ONLY the response label (e.g., "1. Response A")
- Do not add any other text or explanations in the ranking section

Example of the correct format for your ENTIRE response:

Response A provides good detail on X but misses Y...
Response B is accurate but lacks depth on Z...
Response C offers the most comprehensive answer...

FINAL RANKING:
1. Response C
2. Response A
3. Response B

Now provide your evaluation and ranking:"""

    messages = [{"role": "user", "content": ranking_prompt}]
    responses, errors = await _chat_models_parallel(
        adapter=adapter,
        models=models,
        messages=messages,
        timeout=timeout,
        stage="stage2",
    )

    stage2_results = []
    for model, response in responses.items():
        full_text = response.get("content", "")
        parsed = parse_ranking_from_text(full_text)
        stage2_results.append(
            {
                "model": model,
                "ranking": full_text,
                "parsed_ranking": parsed,
            }
        )

    return stage2_results, label_to_model, errors


async def _stage3_synthesize_final_internal(
    user_query: str,
    stage1_results: List[Dict[str, Any]],
    stage2_results: List[Dict[str, Any]],
    chairman_model: str,
    adapter: ProviderAdapter,
    timeout: float,
) -> Tuple[Dict[str, Any], List[ModelRunError]]:
    stage1_text = "\n\n".join(
        [
            f"Model: {result['model']}\nResponse: {result['response']}"
            for result in stage1_results
        ]
    )
    stage2_text = "\n\n".join(
        [f"Model: {result['model']}\nRanking: {result['ranking']}" for result in stage2_results]
    )

    chairman_prompt = f"""You are the Chairman of an LLM Council. Multiple AI models have provided responses to a user's question, and then ranked each other's responses.

Original Question: {user_query}

STAGE 1 - Individual Responses:
{stage1_text}

STAGE 2 - Peer Rankings:
{stage2_text}

Your task as Chairman is to synthesize all of this information into a single, comprehensive, accurate answer to the user's original question. Consider:
- The individual responses and their insights
- The peer rankings and what they reveal about response quality
- Any patterns of agreement or disagreement

Provide a clear, well-reasoned final answer that represents the council's collective wisdom:"""

    model, response, error = await _chat_single_model(
        adapter=adapter,
        model=chairman_model,
        messages=[{"role": "user", "content": chairman_prompt}],
        timeout=timeout,
        stage="stage3",
    )

    if response is None:
        fallback = {
            "model": chairman_model,
            "response": "Error: Unable to generate final synthesis.",
        }
        return fallback, [error] if error else []

    return {
        "model": model,
        "response": response.get("content", ""),
    }, []


async def _generate_conversation_title_internal(
    user_query: str,
    title_model: str,
    adapter: ProviderAdapter,
    timeout: float,
) -> Tuple[str, List[ModelRunError]]:
    title_prompt = f"""Generate a very short title (3-5 words maximum) that summarizes the following question.
The title should be concise and descriptive. Do not use quotes or punctuation in the title.

Question: {user_query}

Title:"""

    _, response, error = await _chat_single_model(
        adapter=adapter,
        model=title_model,
        messages=[{"role": "user", "content": title_prompt}],
        timeout=timeout,
        stage="title",
    )

    if response is None:
        return "New Conversation", [error] if error else []

    title = response.get("content", "New Conversation").strip().strip('"\'')
    if len(title) > 50:
        title = title[:47] + "..."
    return title or "New Conversation", []


async def stage1_collect_responses(
    user_query: str,
    config: CouncilConfig | None = None,
    adapter: ProviderAdapter | None = None,
) -> List[Dict[str, Any]]:
    """Stage 1 public API (backward-compatible return shape)."""
    config = (config or CouncilConfig.from_env()).with_resolved_defaults()
    adapter = adapter or _default_adapter(config)
    stage1_results, _ = await _stage1_collect_responses_internal(
        user_query=user_query,
        models=list(config.models or []),
        adapter=adapter,
        timeout=config.stage_timeout_seconds,
    )
    return stage1_results


async def stage2_collect_rankings(
    user_query: str,
    stage1_results: List[Dict[str, Any]],
    config: CouncilConfig | None = None,
    adapter: ProviderAdapter | None = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    """Stage 2 public API (backward-compatible return shape)."""
    config = (config or CouncilConfig.from_env()).with_resolved_defaults()
    adapter = adapter or _default_adapter(config)
    stage2_results, label_to_model, _ = await _stage2_collect_rankings_internal(
        user_query=user_query,
        stage1_results=stage1_results,
        models=list(config.models or []),
        adapter=adapter,
        timeout=config.stage_timeout_seconds,
    )
    return stage2_results, label_to_model


async def stage3_synthesize_final(
    user_query: str,
    stage1_results: List[Dict[str, Any]],
    stage2_results: List[Dict[str, Any]],
    config: CouncilConfig | None = None,
    adapter: ProviderAdapter | None = None,
) -> Dict[str, Any]:
    """Stage 3 public API (backward-compatible return shape)."""
    config = (config or CouncilConfig.from_env()).with_resolved_defaults()
    adapter = adapter or _default_adapter(config)
    stage3_result, _ = await _stage3_synthesize_final_internal(
        user_query=user_query,
        stage1_results=stage1_results,
        stage2_results=stage2_results,
        chairman_model=config.chairman_model,
        adapter=adapter,
        timeout=config.stage_timeout_seconds,
    )
    return stage3_result


def parse_ranking_from_text(ranking_text: str) -> List[str]:
    """Parse the FINAL RANKING section from model output."""
    import re

    if "FINAL RANKING:" in ranking_text:
        parts = ranking_text.split("FINAL RANKING:")
        if len(parts) >= 2:
            ranking_section = parts[1]
            numbered_matches = re.findall(r"\d+\.\s*Response [A-Z]+", ranking_section)
            if numbered_matches:
                return [
                    re.search(r"Response [A-Z]+", match).group()  # type: ignore[union-attr]
                    for match in numbered_matches
                ]
            return re.findall(r"Response [A-Z]+", ranking_section)

    return re.findall(r"Response [A-Z]+", ranking_text)


def calculate_aggregate_rankings(
    stage2_results: List[Dict[str, Any]],
    label_to_model: Dict[str, str],
) -> List[Dict[str, Any]]:
    """Calculate aggregate rankings across all model rankings."""
    from collections import defaultdict

    model_positions = defaultdict(list)

    for ranking in stage2_results:
        ranking_text = ranking["ranking"]
        parsed_ranking = parse_ranking_from_text(ranking_text)

        for position, label in enumerate(parsed_ranking, start=1):
            if label in label_to_model:
                model_name = label_to_model[label]
                model_positions[model_name].append(position)

    aggregate = []
    for model, positions in model_positions.items():
        if positions:
            avg_rank = sum(positions) / len(positions)
            aggregate.append(
                {
                    "model": model,
                    "average_rank": round(avg_rank, 2),
                    "rankings_count": len(positions),
                }
            )

    aggregate.sort(key=lambda x: x["average_rank"])
    return aggregate


async def generate_conversation_title(
    user_query: str,
    config: CouncilConfig | None = None,
    adapter: ProviderAdapter | None = None,
) -> str:
    """Generate a short conversation title."""
    config = (config or CouncilConfig.from_env()).with_resolved_defaults()
    adapter = adapter or _default_adapter(config)
    title, _ = await _generate_conversation_title_internal(
        user_query=user_query,
        title_model=config.title_model,
        adapter=adapter,
        timeout=config.title_timeout_seconds,
    )
    return title


async def run_full_council_with_runtime(
    user_query: str,
    config: CouncilConfig,
    adapter: ProviderAdapter,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any], Dict[str, Any]]:
    """Run the full pipeline using explicit runtime configuration and adapter."""
    errors: List[ModelRunError] = []

    _log.stage_start("stage1", model_count=len(list(config.models or [])), query_len=len(user_query))
    t_stage1 = time.perf_counter()
    stage1_results, stage1_errors = await _stage1_collect_responses_internal(
        user_query=user_query,
        models=list(config.models or []),
        adapter=adapter,
        timeout=config.stage_timeout_seconds,
    )
    _log.stage_complete("stage1", (time.perf_counter() - t_stage1) * 1000,
                        results=len(stage1_results), errors=len(stage1_errors))
    errors.extend(stage1_errors)

    if not stage1_results:
        metadata = {
            "label_to_model": {},
            "aggregate_rankings": [],
            "errors": [error.to_dict() for error in errors],
        }
        return (
            [],
            [],
            {
                "model": "error",
                "response": "All models failed to respond. Please try again.",
            },
            metadata,
        )

    _log.stage_start("stage2", ranked_responses=len(stage1_results))
    t_stage2 = time.perf_counter()
    stage2_results, label_to_model, stage2_errors = await _stage2_collect_rankings_internal(
        user_query=user_query,
        stage1_results=stage1_results,
        models=list(config.models or []),
        adapter=adapter,
        timeout=config.stage_timeout_seconds,
    )
    _log.stage_complete("stage2", (time.perf_counter() - t_stage2) * 1000,
                        rankings=len(stage2_results), errors=len(stage2_errors))
    errors.extend(stage2_errors)

    aggregate_rankings = calculate_aggregate_rankings(stage2_results, label_to_model)

    _log.stage_start("stage3", chairman=config.chairman_model)
    t_stage3 = time.perf_counter()
    stage3_result, stage3_errors = await _stage3_synthesize_final_internal(
        user_query=user_query,
        stage1_results=stage1_results,
        stage2_results=stage2_results,
        chairman_model=config.chairman_model or CHAIRMAN_MODEL,
        adapter=adapter,
        timeout=config.stage_timeout_seconds,
    )
    _log.stage_complete("stage3", (time.perf_counter() - t_stage3) * 1000,
                        errors=len(stage3_errors))
    errors.extend(stage3_errors)

    metadata = {
        "label_to_model": label_to_model,
        "aggregate_rankings": aggregate_rankings,
        "errors": [error.to_dict() for error in errors],
    }

    return stage1_results, stage2_results, stage3_result, metadata


async def run_full_council(
    user_query: str,
    config: CouncilConfig | None = None,
    adapter: ProviderAdapter | None = None,
) -> Tuple[List, List, Dict, Dict]:
    """
    Run the complete 3-stage council process.

    Returns:
        Tuple of (stage1_results, stage2_results, stage3_result, metadata)
    """
    config = (config or CouncilConfig.from_env()).with_resolved_defaults()
    adapter = adapter or _default_adapter(config)
    return await run_full_council_with_runtime(
        user_query=user_query,
        config=config,
        adapter=adapter,
    )
