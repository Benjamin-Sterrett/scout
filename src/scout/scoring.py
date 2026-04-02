"""Scoring engine for Scout job evaluation.

Implements the 8-dimension scoring model with anchored definitions,
6 additive bonuses, and score-driven Response SLA tiers.  All anchors
and weights sourced verbatim from research/synthesis.md section
"Scout Scoring Model v2".

Design note (v1): Actual dimension scoring (deciding "is this Clarity 3
or 4?") is done by an LLM given the listing text + SCORING_PROMPT_TEMPLATE.
The ``score_dimensions`` function accepts pre-scored values and applies
weights / anchors.  It does NOT do NLP classification.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from scout.gates import check_gates
from scout.models import (
    Bonus,
    DimensionScore,
    GateResult,
    GateVerdict,
    ResponseSLA,
    ScoredListing,
)

if TYPE_CHECKING:
    from scout.models import ParsedListing

# ---------------------------------------------------------------------------
# Dimension anchors — VERBATIM from synthesis SS"Dimension Anchors"
# ---------------------------------------------------------------------------

DIMENSION_ANCHORS: dict[str, dict[str, object]] = {
    "clarity": {
        "weight": 1.5,
        "inverted": False,
        "anchors": {
            1: "No specifics, subjective, or contradictory | 'Make it better' / 'Fix everything' / 'It just doesn't feel right'",
            2: "Vague problem with some technical keywords | 'Something is wrong with our API, it's slow sometimes'",
            3: "Clear problem but missing reproduction steps or environment details | 'Our contact form isn't sending emails. Built with Next.js.'",
            4: "Clear problem + some context but missing reproduction steps | 'Stripe webhook stopped working after we updated to v3. Here's our endpoint code.'",
            5: "Error log + reproduction steps + repo access + expected behavior stated | 'TypeError on line 42 of checkout.js when cart has >10 items. Repo: github.com/...'",
        },
    },
    "fit": {
        "weight": 1.5,
        "inverted": False,
        "anchors": {
            1: "Completely outside lane (design, iOS native, blockchain, game dev)",
            2: "Partially outside stack (e.g., mobile, DevOps, ML pipeline)",
            3: "Known framework but unfamiliar specific library or service",
            4: "API integration, web scraping, or landing page in familiar tech",
            5: "Bug fix or automation in React/Next.js/Python/Node — your core stack",
        },
    },
    "price": {
        "weight": 1.0,
        "inverted": False,
        "anchors": {
            1: "< $75 or 'make me an offer' with no budget signal",
            2: "$75-150, only worth it for < 1 hour / portfolio building",
            3: "$150-300, tight but acceptable if effort is low",
            4: "$300-500 fixed, reasonable for scope",
            5: "> $500 fixed + speed premium signal ('urgent', 'today')",
        },
    },
    "urgency": {
        "weight": 1.0,
        "inverted": False,
        "anchors": {
            1: "No urgency + low budget (signals tire-kicker)",
            2: "'No rush' / 'when you can'",
            3: "'Soon' / no timeline stated but active posting",
            4: "'This week' + reasonable budget",
            5: "'Today' / 'ASAP' + funded budget + clear deliverable",
        },
    },
    "effort": {
        "weight": 1.0,
        "inverted": False,
        "anchors": {
            1: "< 1 hour | CSS fix, typo, config change, known error pattern",
            2: "1-3 hours | Single bug with clear reproduction, simple API integration",
            3: "3-6 hours | Multi-file bug, API integration with auth, basic scraper",
            4: "1-2 days | Complex integration, migration with testing, multi-page site (GATE: >6 hours = reject)",
            5: "Multi-day / unknown | Full feature build, unclear scope, 'build my app' (GATE: >6 hours = reject)",
        },
    },
    "risk": {
        "weight": 1.0,
        "inverted": True,
        "anchors": {
            1: "Funded escrow, clear SOW, repeat client, bounded scope",
            2: "Funded escrow, new client but verified, clear deliverable",
            3: "Verified client, first interaction, some scope ambiguity",
            4: "Unverified or new client, vague success criteria, no milestone structure",
            5: "No escrow, off-platform payment, 'we'll figure out scope as we go'",
        },
    },
    "client_risk": {
        "weight": 1.0,
        "inverted": True,
        "anchors": {
            1: "$10K+ spent, 90%+ hire rate, 4.8+ rating, repeat poster",
            2: "$1K-10K spent, 70%+ hire rate, verified payment",
            3: "$500-1K spent, 50-70% hire rate, some history",
            4: "< $500 spent, < 50% hire rate, first-time client",
            5: "No history, no verified payment, dispute history visible",
        },
    },
    "technical_risk": {
        "weight": 1.0,
        "inverted": True,
        "anchors": {
            1: "Isolated, no production access needed, easily reversible | Fix CSS, update copy, static site change",
            2: "Limited blast radius, staging available, testable | API endpoint fix with test suite, scraper on public data",
            3: "Touches production but sandboxable, moderate blast radius | Webhook fix, form handler, payment flow change",
            4: "Production database access, no staging, hard to reverse | DB migration, data cleanup on live system",
            5: "Admin access to critical systems, destructive potential | Production DB writes, auth system changes, infra modifications",
        },
    },
}

# Dimensions that are SUBTRACTED in the scoring formula.
# Per synthesis formula: Score = (Clarity*1.5 + Fit*1.5 + Price + Urgency)
#                              - (Effort + Risk + Client_Risk + Technical_Risk)
# Note: Effort is subtracted even though its anchor scale runs low-to-high
# (1=<1hr is best for us). The "inverted" flag on Risk/Client_Risk/Technical_Risk
# describes the anchor semantics (1=safest), not the formula position.
_SUBTRACTED_DIMENSIONS: frozenset[str] = frozenset(
    ["effort", "risk", "client_risk", "technical_risk"]
)

# ---------------------------------------------------------------------------
# Response SLA thresholds (synthesis SS"Response SLA")
# ---------------------------------------------------------------------------

RESPONSE_SLA_THRESHOLDS: list[tuple[float, ResponseSLA]] = [
    (12.0, ResponseSLA.IMMEDIATE_30MIN),
    (8.0, ResponseSLA.PRIORITY_60MIN),
    (5.0, ResponseSLA.STANDARD_4HR),
    (3.0, ResponseSLA.BATCH_NEXT_DAY),
]
# Anything below 3.0 maps to SKIP (handled as the fallback).

# ---------------------------------------------------------------------------
# Bonus definitions (synthesis SS"Bonuses")
# ---------------------------------------------------------------------------

# Urgency keywords that trigger the speed premium bonus.
_URGENCY_KEYWORDS: frozenset[str] = frozenset(
    ["urgent", "asap", "today", "immediately", "right now", "emergency"]
)

# Technical keywords that signal scoping confidence.
_TECH_KEYWORDS: frozenset[str] = frozenset(
    [
        "react",
        "next.js",
        "nextjs",
        "python",
        "node",
        "nodejs",
        "typescript",
        "javascript",
        "tailwind",
        "api",
        "webhook",
        "scraping",
        "automation",
        "django",
        "flask",
        "fastapi",
        "express",
        "postgresql",
        "mongodb",
    ]
)


def _has_urgency_premium(listing: ParsedListing) -> bool:
    """'Urgent'/'ASAP'/'today' + budget > $200 → +2."""
    if listing.budget is None or listing.budget <= 200:
        return False
    signals = {s.lower() for s in listing.urgency_signals}
    text_lower = f"{listing.title} {listing.description}".lower()
    return bool(
        signals & _URGENCY_KEYWORDS or any(kw in text_lower for kw in _URGENCY_KEYWORDS)
    )


def _has_tech_keywords(listing: ParsedListing) -> bool:
    """Technical keywords + clear deliverable → +1."""
    kw_lower = {k.lower() for k in listing.tech_keywords}
    text_lower = f"{listing.title} {listing.description}".lower()
    return bool(
        kw_lower & _TECH_KEYWORDS or any(kw in text_lower for kw in _TECH_KEYWORDS)
    )


def _is_repeat_poster(listing: ParsedListing) -> bool:
    """Repeat job poster → +1.

    Uses client_spend_history as a proxy: clients who have spent $1K+
    are repeat posters on the platform.
    """
    return (
        listing.client_spend_history is not None
        and listing.client_spend_history >= 1000
    )


def _low_competition(listing: ParsedListing) -> bool:
    """< 10 existing proposals → +1.

    Detectable via platform-specific signals.  In v1, check for
    'low competition' or similar signals in urgency_signals.
    """
    signals_lower = {s.lower() for s in listing.urgency_signals}
    return "low competition" in signals_lower or "few proposals" in signals_lower


def _reusable_asset(listing: ParsedListing) -> bool:
    """Script/template/workflow reusable across future jobs → +2.

    Detected by category (scraping, automation) or keywords.
    """
    reusable_categories = {"web_scraping", "automation_script"}
    if listing.category and listing.category.value in reusable_categories:
        return True
    text_lower = f"{listing.title} {listing.description}".lower()
    reuse_signals = ["template", "reusable", "boilerplate", "script"]
    return any(sig in text_lower for sig in reuse_signals)


def _proof_proximity(listing: ParsedListing) -> bool:
    """Near-identical past project → +2.

    In v1, detected via 'proof proximity' or 'done before' signals.
    Future versions will match against a project history database.
    """
    signals_lower = {s.lower() for s in listing.urgency_signals}
    return "proof proximity" in signals_lower or "done before" in signals_lower


# Ordered list of (name, points, detector) for bonus evaluation.
BONUS_DEFINITIONS: list[tuple[str, int, str]] = [
    ("urgency_premium", 2, "'Urgent'/'ASAP'/'today' + budget > $200"),
    ("tech_keywords", 1, "Technical keywords + clear deliverable"),
    ("repeat_poster", 1, "Repeat job poster ($1K+ spent)"),
    ("low_competition", 1, "< 10 existing proposals"),
    ("reusable_asset", 2, "Script/template/workflow reusable across future jobs"),
    (
        "proof_proximity",
        2,
        "Near-identical past project — fastest execution, lowest risk",
    ),
]


def calculate_bonuses(
    listing: ParsedListing,
    scores: list[DimensionScore],  # noqa: ARG001 — reserved for future use
) -> list[Bonus]:
    """Evaluate all 6 bonus rules against a listing.

    Returns only bonuses that matched.
    """
    detectors: list[tuple[str, int, str, object]] = [
        (
            "urgency_premium",
            2,
            "'Urgent'/'ASAP'/'today' + budget > $200",
            _has_urgency_premium,
        ),
        (
            "tech_keywords",
            1,
            "Technical keywords + clear deliverable",
            _has_tech_keywords,
        ),
        ("repeat_poster", 1, "Repeat job poster ($1K+ spent)", _is_repeat_poster),
        ("low_competition", 1, "< 10 existing proposals", _low_competition),
        (
            "reusable_asset",
            2,
            "Script/template/workflow reusable across future jobs",
            _reusable_asset,
        ),
        ("proof_proximity", 2, "Near-identical past project", _proof_proximity),
    ]
    matched: list[Bonus] = []
    for name, points, reason, detect_fn in detectors:
        if detect_fn(listing):  # type: ignore[operator]
            matched.append(Bonus(name=name, points=points, reason=reason))
    return matched


# ---------------------------------------------------------------------------
# Scoring functions
# ---------------------------------------------------------------------------


def score_dimensions(
    listing: ParsedListing,  # noqa: ARG001 — reserved for LLM context in v2
    pre_scores: dict[str, int],
) -> list[DimensionScore]:
    """Apply weights and record anchors for pre-scored dimensions.

    ``pre_scores`` maps dimension name -> integer score (1-5).
    Weights and anchor text come from ``DIMENSION_ANCHORS``.
    """
    results: list[DimensionScore] = []
    for dim_name, cfg in DIMENSION_ANCHORS.items():
        raw = pre_scores.get(dim_name)
        if raw is None:
            continue
        raw = max(1, min(5, raw))  # clamp
        weight = float(cfg["weight"])  # type: ignore[arg-type]
        anchors: dict[int, str] = cfg["anchors"]  # type: ignore[assignment]
        results.append(
            DimensionScore(
                dimension=dim_name,
                score=raw,
                weight=weight,
                anchor_matched=anchors.get(raw, ""),
                reasoning=f"{dim_name} scored {raw}/5",
            )
        )
    return results


def _compute_total(
    dim_scores: list[DimensionScore],
    bonuses: list[Bonus],
) -> float:
    """Apply the synthesis formula.

    Score = (Clarity*1.5 + Fit*1.5 + Price + Urgency)
          - (Effort + Risk + Client_Risk + Technical_Risk)
          + Bonuses
    """
    positive = 0.0
    negative = 0.0
    for ds in dim_scores:
        weighted = ds.score * ds.weight
        if ds.dimension in _SUBTRACTED_DIMENSIONS:
            negative += weighted
        else:
            positive += weighted
    bonus_total = sum(b.points for b in bonuses)
    return positive - negative + bonus_total


def determine_sla(total_score: float) -> ResponseSLA:
    """Map a total score to a Response SLA tier."""
    for threshold, sla in RESPONSE_SLA_THRESHOLDS:
        if total_score >= threshold:
            return sla
    return ResponseSLA.SKIP


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def score_job(
    listing: ParsedListing,
    pre_scores: dict[str, int],
) -> ScoredListing:
    """Full scoring pipeline: gates -> dimensions -> bonuses -> SLA.

    Gate verdict logic:
    - Any FAIL  -> rejected (total_score=0, SLA=SKIP, empty scores/bonuses)
    - Any MAYBE (no FAIL) -> score normally but set needs_review=True
    - All PASS  -> score normally

    Gate failures override score -- a job scoring 15 but with a gate
    failure still gets rejected (synthesis: "Gate failures override score").
    """
    gate_results: list[GateResult] = check_gates(listing, pre_scores)
    failed_gates = [g for g in gate_results if g.verdict == GateVerdict.FAIL]
    maybe_gates = [g for g in gate_results if g.verdict == GateVerdict.MAYBE]

    if failed_gates:
        return ScoredListing(
            parsed_listing=listing,
            gate_results=gate_results,
            dimension_scores=[],
            bonuses=[],
            total_score=0.0,
            response_sla=ResponseSLA.SKIP,
            rejected=True,
            rejection_reason=(
                "Failed gate(s): "
                + ", ".join(f"{g.gate} ({g.reason})" for g in failed_gates)
            ),
        )

    dim_scores = score_dimensions(listing, pre_scores)
    bonuses = calculate_bonuses(listing, dim_scores)
    total = _compute_total(dim_scores, bonuses)
    sla = determine_sla(total)

    return ScoredListing(
        parsed_listing=listing,
        gate_results=gate_results,
        dimension_scores=dim_scores,
        bonuses=bonuses,
        total_score=total,
        response_sla=sla,
        needs_review=bool(maybe_gates),
    )


# ---------------------------------------------------------------------------
# LLM Scoring Prompt Template (v1 manual flow)
# ---------------------------------------------------------------------------

SCORING_PROMPT_TEMPLATE: str = """You are scoring a freelance job listing for Scout, a job arbitrage engine.

Score each dimension 1-5 using ONLY these anchored definitions. Return JSON.

## Listing
Title: {title}
Description: {description}
Budget: {budget}
Platform: {platform}
Client spend history: {client_spend_history}
Client hire rate: {client_hire_rate}
Tech keywords: {tech_keywords}

## Dimensions (score each 1-5)

### Clarity (weight 1.5x)
1: No specifics, subjective, or contradictory | "Make it better" / "Fix everything"
2: Vague problem with some technical keywords | "Something is wrong with our API, it's slow sometimes"
3: Clear problem but missing reproduction steps or environment details
4: Clear problem + some context but missing reproduction steps
5: Error log + reproduction steps + repo access + expected behavior stated

### Fit (weight 1.5x)
1: Completely outside lane (design, iOS native, blockchain, game dev)
2: Partially outside stack (e.g., mobile, DevOps, ML pipeline)
3: Known framework but unfamiliar specific library or service
4: API integration, web scraping, or landing page in familiar tech
5: Bug fix or automation in React/Next.js/Python/Node — core stack

### Price (weight 1.0x)
1: < $75 or "make me an offer" with no budget signal
2: $75-150, only worth it for < 1 hour / portfolio building
3: $150-300, tight but acceptable if effort is low
4: $300-500 fixed, reasonable for scope
5: > $500 fixed + speed premium signal ("urgent", "today")

### Urgency (weight 1.0x)
1: No urgency + low budget (signals tire-kicker)
2: "No rush" / "when you can"
3: "Soon" / no timeline stated but active posting
4: "This week" + reasonable budget
5: "Today" / "ASAP" + funded budget + clear deliverable

### Effort (weight 1.0x)
1: < 1 hour | CSS fix, typo, config change, known error pattern
2: 1-3 hours | Single bug with clear reproduction, simple API integration
3: 3-6 hours | Multi-file bug, API integration with auth, basic scraper
4: 1-2 days | Complex integration, migration with testing (GATE: >6hr = reject)
5: Multi-day / unknown | Full feature build, unclear scope (GATE: >6hr = reject)

### Risk (weight 1.0x, inverted — 1 is safest, subtracted from score)
1: Funded escrow, clear SOW, repeat client, bounded scope
2: Funded escrow, new client but verified, clear deliverable
3: Verified client, first interaction, some scope ambiguity
4: Unverified or new client, vague success criteria, no milestone structure
5: No escrow, off-platform payment, "we'll figure out scope as we go"

### Client Risk (weight 1.0x, inverted — 1 is safest, subtracted from score)
1: $10K+ spent, 90%+ hire rate, 4.8+ rating, repeat poster
2: $1K-10K spent, 70%+ hire rate, verified payment
3: $500-1K spent, 50-70% hire rate, some history
4: < $500 spent, < 50% hire rate, first-time client
5: No history, no verified payment, dispute history visible

### Technical Risk (weight 1.0x, inverted — 1 is safest, subtracted from score)
1: Isolated, no production access needed, easily reversible
2: Limited blast radius, staging available, testable
3: Touches production but sandboxable, moderate blast radius
4: Production database access, no staging, hard to reverse
5: Admin access to critical systems, destructive potential

## Response format
Return ONLY valid JSON:
{{
  "clarity": <int 1-5>,
  "fit": <int 1-5>,
  "price": <int 1-5>,
  "urgency": <int 1-5>,
  "effort": <int 1-5>,
  "risk": <int 1-5>,
  "client_risk": <int 1-5>,
  "technical_risk": <int 1-5>
}}
"""
