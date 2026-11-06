"""What the admin analytics page shows about the assistant: intents, languages, latency,
which tier answered, and guardrail activity.

Read from `TurnAnalytics`, which holds timings and labels only.
"""

import math
from collections import Counter
from datetime import datetime, timedelta
from typing import Any

from models.turn_analytics import TurnAnalytics
from time_utils import now_utc

MAX_TURNS = 5000  # the latest turns in the window; plenty for a POC
# The first-choice answers. Anything else answering means a fallback tier was needed.
PRIMARY_TIERS = frozenset({"gemini"})
FALLBACK_TIERS = frozenset({"ollama", "rules"})


def percentile(values: list[float], percent: float) -> float:
    """Nearest-rank percentile: always one of the measured values."""
    if not values:
        raise ValueError("no values")
    ordered = sorted(values)
    return ordered[max(1, math.ceil(percent / 100 * len(ordered))) - 1]


async def record_turn(
    *,
    pipeline: str,
    result: Any,
    stages: dict[str, float],
    stt_provider: str = "",
    tts_provider: str = "",
    spoken: bool = False,
    barged_in: bool = False,
) -> None:
    """One row per assistant turn, whichever way it arrived. No words, no user."""
    await TurnAnalytics(
        pipeline=pipeline,
        intent=result.intent.value,
        language=result.language,
        routed_by=result.routed_by,
        used_llm=result.used_llm,
        cache_hit=result.cached,
        answered_by=result.answered_by,
        llm_errors=result.llm_errors,
        blocked=result.blocked,
        guardrail=result.guardrail or "",
        tools_called=result.tools_called,
        stt_provider=stt_provider,
        tts_provider=tts_provider,
        spoken=spoken,
        barged_in=barged_in,
        stages=stages,
    ).insert()


def _latency(turns: list[TurnAnalytics]) -> dict[str, dict[str, Any]]:
    by_pipeline: dict[str, dict[str, Any]] = {}
    for pipeline in sorted({t.pipeline for t in turns}):
        mine = [t for t in turns if t.pipeline == pipeline]
        stages: dict[str, dict[str, float]] = {}
        for stage in sorted({stage for t in mine for stage in t.stages}):
            values = [t.stages[stage] for t in mine if stage in t.stages]
            stages[stage] = {
                "n": len(values),
                "p50": percentile(values, 50),
                "p95": percentile(values, 95),
            }
        by_pipeline[pipeline] = {"turns": len(mine), "stages": stages}
    return by_pipeline


async def turn_summary(days: int) -> dict[str, Any]:
    since: datetime = now_utc() - timedelta(days=days)
    turns = (
        await TurnAnalytics.find(TurnAnalytics.created_at >= since)
        .sort("-created_at")
        .limit(MAX_TURNS)
        .to_list()
    )
    total = len(turns)
    tiers = Counter(t.answered_by or "unknown" for t in turns)
    # Rates are over the turns that say who answered: rows from before that was recorded
    # would otherwise count as neither a first-choice answer nor a fallback
    known = total - tiers["unknown"]
    errors = Counter(error for t in turns for error in t.llm_errors)

    def share(count: int) -> float:
        return count / known if known else 0.0

    return {
        "since": since.isoformat(),
        "days": days,
        "turns": total,
        "pipelines": _latency(turns),
        "intents": dict(Counter(t.intent for t in turns).most_common()),
        "languages": dict(Counter(t.language for t in turns).most_common()),
        "answered_by": dict(tiers.most_common()),
        "turns_without_tier": tiers["unknown"],
        "fallback_rate": share(sum(tiers[tier] for tier in FALLBACK_TIERS)),
        "cache_rate": share(tiers["cache"]),
        "primary_rate": share(sum(tiers[tier] for tier in PRIMARY_TIERS)),
        "llm_errors": dict(errors.most_common()),
        "turns_with_llm_errors": sum(1 for t in turns if t.llm_errors),
        "blocked": sum(1 for t in turns if t.blocked),
        "guardrails": dict(Counter(t.guardrail for t in turns if t.guardrail).most_common()),
        "barged_in": sum(1 for t in turns if t.barged_in),
        "unspoken": sum(1 for t in turns if t.pipeline != "text" and not t.spoken),
    }
