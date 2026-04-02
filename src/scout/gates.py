"""Hard gates for Scout job scoring.

Eight gates with tri-state verdicts (PASS / FAIL / MAYBE) sourced from
research/synthesis.md section "Scout Scoring Model v2 > Hard Gates".
Every gate runs independently (no short-circuit) so the caller always
sees the full picture.

MAYBE verdicts surface borderline cases for human review rather than
treating a $145 listing identically to an equity scam.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from scout.models import GateResult, GateVerdict

if TYPE_CHECKING:
    from scout.models import ParsedListing

# ---------------------------------------------------------------------------
# Keyword patterns for text-matching gates (synthesis SS2 Tier 3 + SS7)
# ---------------------------------------------------------------------------

_MVP_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\bbuild from scratch\b",
        r"\bbuild my app\b",
        r"\bbuild me a\b",
        r"\bI have an idea\b",
        r"\bbuild (?:a|an|the) (?:full|complete|entire)\b",
        r"\bmvp\b",
        r"\bfrom the ground up\b",
    ]
]

_EQUITY_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\bequity\b",
        r"\brevenue share\b",
        r"\bprofit sharing\b",
        r"\bshare of profits\b",
        r"\bsweat equity\b",
        r"\bco-?founder\b",
    ]
]

_FREE_WORK_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\bfree (?:test|sample|trial)\b",
        r"\btrial task\b",
        r"\btest project\b",
        r"\btest first\b",
        r"\bwork for free\b",
        r"\bunpaid (?:test|trial|task)\b",
    ]
]

# Minimum budget threshold (all 6 sources agree)
BUDGET_FLOOR: float = 150.0

# Budget MAYBE zone: $100-149 is close enough to surface for human review
BUDGET_MAYBE_FLOOR: float = 100.0


def _text_blob(listing: ParsedListing) -> str:
    """Combine title + description for keyword matching."""
    return f"{listing.title} {listing.description}"


def _matches_any(text: str, patterns: list[re.Pattern[str]]) -> bool:
    return any(p.search(text) for p in patterns)


# ---------------------------------------------------------------------------
# Individual gate functions
# ---------------------------------------------------------------------------


def _gate_budget_floor(listing: ParsedListing) -> GateResult:
    if listing.budget is None:
        return GateResult(
            gate="budget_floor",
            verdict=GateVerdict.FAIL,
            reason="No budget listed",
        )
    if listing.budget >= BUDGET_FLOOR:
        return GateResult(
            gate="budget_floor",
            verdict=GateVerdict.PASS,
            reason=f"Budget ${listing.budget:.0f} meets ${BUDGET_FLOOR:.0f} floor",
        )
    if listing.budget >= BUDGET_MAYBE_FLOOR:
        return GateResult(
            gate="budget_floor",
            verdict=GateVerdict.MAYBE,
            reason=(
                f"Budget ${listing.budget:.0f} is close to "
                f"${BUDGET_FLOOR:.0f} floor — borderline"
            ),
        )
    return GateResult(
        gate="budget_floor",
        verdict=GateVerdict.FAIL,
        reason=f"Budget ${listing.budget:.0f} below ${BUDGET_FLOOR:.0f} floor",
    )


def _gate_effort_ceiling(
    pre_scores: dict[str, int] | None,
) -> GateResult:
    if pre_scores is None or "effort" not in pre_scores:
        return GateResult(
            gate="effort_ceiling",
            verdict=GateVerdict.PASS,
            reason="No effort score provided; gate skipped",
        )
    effort = pre_scores["effort"]
    if effort < 3:
        return GateResult(
            gate="effort_ceiling",
            verdict=GateVerdict.PASS,
            reason=f"Effort {effort}/5 within ceiling (<3)",
        )
    if effort == 3:
        return GateResult(
            gate="effort_ceiling",
            verdict=GateVerdict.MAYBE,
            reason=f"Effort {effort}/5 at boundary (3-6 hours) — borderline",
        )
    return GateResult(
        gate="effort_ceiling",
        verdict=GateVerdict.FAIL,
        reason=f"Effort {effort}/5 exceeds ceiling (>3 = >6 hours)",
    )


def _gate_clarity_floor(
    pre_scores: dict[str, int] | None,
) -> GateResult:
    if pre_scores is None or "clarity" not in pre_scores:
        return GateResult(
            gate="clarity_floor",
            verdict=GateVerdict.PASS,
            reason="No clarity score provided; gate skipped",
        )
    clarity = pre_scores["clarity"]
    if clarity >= 3:
        return GateResult(
            gate="clarity_floor",
            verdict=GateVerdict.PASS,
            reason=f"Clarity {clarity}/5 meets floor (>=3)",
        )
    return GateResult(
        gate="clarity_floor",
        verdict=GateVerdict.FAIL,
        reason=f"Clarity {clarity}/5 below floor (>=3 required)",
    )


def _gate_fit_floor(
    pre_scores: dict[str, int] | None,
) -> GateResult:
    if pre_scores is None or "fit" not in pre_scores:
        return GateResult(
            gate="fit_floor",
            verdict=GateVerdict.PASS,
            reason="No fit score provided; gate skipped",
        )
    fit = pre_scores["fit"]
    if fit >= 3:
        return GateResult(
            gate="fit_floor",
            verdict=GateVerdict.PASS,
            reason=f"Fit {fit}/5 meets floor (>=3)",
        )
    return GateResult(
        gate="fit_floor",
        verdict=GateVerdict.FAIL,
        reason=f"Fit {fit}/5 below floor (>=3 required)",
    )


def _gate_payment_verified(listing: ParsedListing) -> GateResult:
    has_spend = listing.client_spend_history is not None
    has_hire = listing.client_hire_rate is not None

    if has_spend and has_hire:
        return GateResult(
            gate="payment_verified",
            verdict=GateVerdict.PASS,
            reason="Client has both spend history and hire rate data",
        )
    if has_spend or has_hire:
        missing = "hire rate" if not has_hire else "spend history"
        return GateResult(
            gate="payment_verified",
            verdict=GateVerdict.MAYBE,
            reason=f"Partial client data — missing {missing} (could be parsing gap)",
        )
    return GateResult(
        gate="payment_verified",
        verdict=GateVerdict.FAIL,
        reason="No client spend history and no hire rate — unverified",
    )


def _gate_mvp_rejection(listing: ParsedListing) -> GateResult:
    blob = _text_blob(listing)
    matched = _matches_any(blob, _MVP_PATTERNS)
    return GateResult(
        gate="mvp_rejection",
        verdict=GateVerdict.FAIL if matched else GateVerdict.PASS,
        reason=(
            "Matches MVP / build-from-scratch pattern (scope creep 5/5)"
            if matched
            else "No MVP / build-from-scratch signals"
        ),
    )


def _gate_equity_rejection(listing: ParsedListing) -> GateResult:
    blob = _text_blob(listing)
    matched = _matches_any(blob, _EQUITY_PATTERNS)
    return GateResult(
        gate="equity_rejection",
        verdict=GateVerdict.FAIL if matched else GateVerdict.PASS,
        reason=(
            "Mentions equity or revenue share — not real money"
            if matched
            else "No equity / revenue share signals"
        ),
    )


def _gate_free_work_rejection(listing: ParsedListing) -> GateResult:
    blob = _text_blob(listing)
    matched = _matches_any(blob, _FREE_WORK_PATTERNS)
    return GateResult(
        gate="free_work_rejection",
        verdict=GateVerdict.FAIL if matched else GateVerdict.PASS,
        reason=(
            "Requests free test / trial work — red flag"
            if matched
            else "No free test work demands"
        ),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def check_gates(
    listing: ParsedListing,
    pre_scores: dict[str, int] | None = None,
) -> list[GateResult]:
    """Run all 8 hard gates against a listing.

    Gates 2-4 (effort, clarity, fit) require pre-scored dimensions.
    If ``pre_scores`` is None or missing the relevant key, those gates
    pass by default (they'll be evaluated later when scores are available).

    All gates run independently — no short-circuit.
    """
    return [
        _gate_budget_floor(listing),
        _gate_effort_ceiling(pre_scores),
        _gate_clarity_floor(pre_scores),
        _gate_fit_floor(pre_scores),
        _gate_payment_verified(listing),
        _gate_mvp_rejection(listing),
        _gate_equity_rejection(listing),
        _gate_free_work_rejection(listing),
    ]
