"""Pipeline orchestrator for Scout.

Runs the full parse -> gate -> score -> rank flow.  Accepts raw listings,
returns ranked/rejected/needs_review buckets with stats.

Design: score_job() runs on ALL listings (including LOW confidence).
Routing happens AFTER scoring:
  1. rejected=True (any FAIL gate)  -> rejected
  2. parse_confidence=LOW (not rejected) -> needs_review
  3. needs_review=True (MAYBE gates) -> needs_review WITH score
  4. Otherwise -> ranked (sorted by total_score desc, sliced to top_n)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from scout.intake import parse_listings
from scout.models import (
    ParseConfidence,
    ParsedListing,
    RawListing,
    ScoredListing,
)
from scout.scoring import score_job


@dataclass
class PipelineStats:
    """Aggregate stats for a pipeline run."""

    total_parsed: int = 0
    passed_gates: int = 0
    rejected: int = 0
    needs_review: int = 0
    avg_score: float = 0.0
    duration_ms: float = 0.0
    confidence_distribution: dict[str, int] = field(default_factory=dict)


@dataclass
class PipelineResult:
    """Full pipeline output with three buckets + stats."""

    ranked: list[ScoredListing]
    rejected: list[ScoredListing]
    needs_review: list[ScoredListing]
    stats: PipelineStats
    has_pre_scores: bool = False


def _build_confidence_distribution(
    parsed: list[ParsedListing],
) -> dict[str, int]:
    """Count HIGH/MEDIUM/LOW across parsed listings."""
    dist: dict[str, int] = {"high": 0, "medium": 0, "low": 0}
    for p in parsed:
        dist[p.parse_confidence.value] = dist.get(p.parse_confidence.value, 0) + 1
    return dist


def run_pipeline(
    raws: list[RawListing],
    pre_scores_map: dict[int, dict[str, int]] | None = None,
    top_n: int = 5,
) -> PipelineResult:
    """Execute the full pipeline: parse -> gate -> score -> rank.

    Args:
        raws: Raw listings to process.
        pre_scores_map: Optional mapping of listing index -> dimension scores.
            When None or missing an index, gates that need scores pass by
            default and dimension scores are empty.  Bonuses still apply
            (they're derived from listing data, not LLM scores), so
            total_score may be nonzero even without pre_scores.
        top_n: Number of top-ranked listings to return.

    Returns:
        PipelineResult with ranked/rejected/needs_review buckets.
    """
    start = time.monotonic()

    parsed = parse_listings(raws)
    scores_map = pre_scores_map or {}
    has_scores = bool(pre_scores_map)

    ranked_buf: list[ScoredListing] = []
    rejected_buf: list[ScoredListing] = []
    review_buf: list[ScoredListing] = []

    for i, listing in enumerate(parsed):
        pre_scores = scores_map.get(i, {})
        scored = score_job(listing, pre_scores)

        if scored.rejected:
            rejected_buf.append(scored)
        elif listing.parse_confidence == ParseConfidence.LOW:
            # LOW confidence -> needs_review even if gates passed.
            # Override needs_review flag on the scored listing.
            review_buf.append(scored.model_copy(update={"needs_review": True}))
        elif scored.needs_review:
            # MAYBE gates (no FAIL) -> needs_review WITH score.
            review_buf.append(scored)
        else:
            ranked_buf.append(scored)

    # Sort ranked by total_score descending.
    ranked_buf.sort(key=lambda s: s.total_score, reverse=True)

    # Compute stats from the FULL ranked buffer before slicing.
    total_passed = len(ranked_buf)
    avg = 0.0
    if ranked_buf:
        avg = sum(s.total_score for s in ranked_buf) / len(ranked_buf)

    # Slice to top_n for display.
    display_ranked = ranked_buf[:top_n]

    elapsed_ms = (time.monotonic() - start) * 1000

    stats = PipelineStats(
        total_parsed=len(parsed),
        passed_gates=total_passed,
        rejected=len(rejected_buf),
        needs_review=len(review_buf),
        avg_score=round(avg, 1),
        duration_ms=round(elapsed_ms, 1),
        confidence_distribution=_build_confidence_distribution(parsed),
    )

    return PipelineResult(
        ranked=display_ranked,
        rejected=rejected_buf,
        needs_review=review_buf,
        stats=stats,
        has_pre_scores=has_scores,
    )
