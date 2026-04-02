"""Tests for Scout normalizer (src/scout/normalizer.py).

Tests cover ticket generation from ScoredListing, all 8 required sections,
priority mapping at each threshold, description length gate (>= 300 chars),
SOW clause presence, and revision limit presence.
"""

from __future__ import annotations

import pytest

from scout.models import (
    Bonus,
    Category,
    DimensionScore,
    GateResult,
    GateVerdict,
    NormalizedTicket,
    ParseConfidence,
    ParsedListing,
    Platform,
    ResponseSLA,
    ScoredListing,
)
from scout.normalizer import _map_priority, normalize_to_ticket


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_parsed(**overrides: object) -> ParsedListing:
    defaults: dict[str, object] = {
        "title": "Fix Stripe webhook 500 error",
        "description": (
            "Our Stripe webhook endpoint returns 500 when processing "
            "subscription renewals. Error started after upgrading to "
            "Stripe API v2023-10-16. Logs show a TypeError in the "
            "event handler. Repo access will be provided."
        ),
        "budget": 400.0,
        "platform": Platform.UPWORK,
        "url": "https://www.upwork.com/jobs/123456",
        "client_spend_history": 8000.0,
        "client_hire_rate": 85.0,
        "posted_at": None,
        "tech_keywords": ["python", "fastapi", "stripe"],
        "urgency_signals": ["urgent"],
        "parse_confidence": ParseConfidence.HIGH,
        "category": Category.BUG_FIX,
    }
    defaults.update(overrides)
    return ParsedListing(**defaults)  # type: ignore[arg-type]


def _make_scored(
    total_score: float = 14.0,
    sla: ResponseSLA = ResponseSLA.IMMEDIATE_30MIN,
    **parsed_overrides: object,
) -> ScoredListing:
    """Build a ScoredListing with realistic dimension scores."""
    parsed = _make_parsed(**parsed_overrides)
    dim_scores = [
        DimensionScore(
            dimension="clarity",
            score=4,
            weight=1.5,
            anchor_matched="Clear problem + some context",
            reasoning="clarity scored 4/5",
        ),
        DimensionScore(
            dimension="fit",
            score=5,
            weight=1.5,
            anchor_matched="Bug fix in Python/Node - core stack",
            reasoning="fit scored 5/5",
        ),
        DimensionScore(
            dimension="price",
            score=4,
            weight=1.0,
            anchor_matched="$300-500 fixed, reasonable for scope",
            reasoning="price scored 4/5",
        ),
        DimensionScore(
            dimension="urgency",
            score=4,
            weight=1.0,
            anchor_matched="'This week' + reasonable budget",
            reasoning="urgency scored 4/5",
        ),
        DimensionScore(
            dimension="effort",
            score=2,
            weight=1.0,
            anchor_matched="1-3 hours | Single bug with clear reproduction",
            reasoning="effort scored 2/5",
        ),
        DimensionScore(
            dimension="risk",
            score=2,
            weight=1.0,
            anchor_matched="Funded escrow, new client but verified",
            reasoning="risk scored 2/5",
        ),
        DimensionScore(
            dimension="client_risk",
            score=1,
            weight=1.0,
            anchor_matched="$10K+ spent, 90%+ hire rate",
            reasoning="client_risk scored 1/5",
        ),
        DimensionScore(
            dimension="technical_risk",
            score=3,
            weight=1.0,
            anchor_matched="Touches production but sandboxable",
            reasoning="technical_risk scored 3/5",
        ),
    ]
    gate_results = [
        GateResult(gate="budget_floor", verdict=GateVerdict.PASS, reason="ok"),
        GateResult(gate="effort_ceiling", verdict=GateVerdict.PASS, reason="ok"),
        GateResult(gate="clarity_floor", verdict=GateVerdict.PASS, reason="ok"),
        GateResult(gate="fit_floor", verdict=GateVerdict.PASS, reason="ok"),
        GateResult(gate="payment_verified", verdict=GateVerdict.PASS, reason="ok"),
        GateResult(gate="mvp_rejection", verdict=GateVerdict.PASS, reason="ok"),
        GateResult(gate="equity_rejection", verdict=GateVerdict.PASS, reason="ok"),
        GateResult(gate="free_work_rejection", verdict=GateVerdict.PASS, reason="ok"),
    ]
    bonuses = [
        Bonus(name="urgency_premium", points=2, reason="urgent + budget > $200"),
        Bonus(name="tech_keywords", points=1, reason="python, fastapi"),
    ]
    return ScoredListing(
        parsed_listing=parsed,
        gate_results=gate_results,
        dimension_scores=dim_scores,
        bonuses=bonuses,
        total_score=total_score,
        response_sla=sla,
    )


# ---------------------------------------------------------------------------
# Section presence
# ---------------------------------------------------------------------------


class TestTicketSections:
    """All 8 sections must appear in the generated description."""

    def test_problem_section(self) -> None:
        ticket = normalize_to_ticket(_make_scored())
        assert "## Problem" in ticket.description

    def test_scope_section(self) -> None:
        ticket = normalize_to_ticket(_make_scored())
        assert "## Scope" in ticket.description

    def test_assumptions_section(self) -> None:
        ticket = normalize_to_ticket(_make_scored())
        assert "## Assumptions" in ticket.description

    def test_deliverables_section(self) -> None:
        ticket = normalize_to_ticket(_make_scored())
        assert "## Deliverables" in ticket.description

    def test_acceptance_criteria_section(self) -> None:
        ticket = normalize_to_ticket(_make_scored())
        assert "## Acceptance Criteria" in ticket.description

    def test_constraints_section(self) -> None:
        ticket = normalize_to_ticket(_make_scored())
        assert "## Constraints" in ticket.description

    def test_risks_section(self) -> None:
        ticket = normalize_to_ticket(_make_scored())
        assert "## Risks & Mitigations" in ticket.description

    def test_sow_clause_section(self) -> None:
        ticket = normalize_to_ticket(_make_scored())
        assert "## Client SOW Clause" in ticket.description

    def test_source_section(self) -> None:
        ticket = normalize_to_ticket(_make_scored())
        assert "## Source" in ticket.description

    def test_all_eight_sections_present(self) -> None:
        """Single assertion that all 8 required sections exist."""
        ticket = normalize_to_ticket(_make_scored())
        required = [
            "## Problem",
            "## Scope",
            "## Assumptions",
            "## Deliverables",
            "## Acceptance Criteria",
            "## Constraints",
            "## Risks & Mitigations",
            "## Client SOW Clause",
            "## Source",
        ]
        for section in required:
            assert section in ticket.description, f"Missing section: {section}"


# ---------------------------------------------------------------------------
# Priority mapping
# ---------------------------------------------------------------------------


class TestPriorityMapping:
    def test_urgent_at_12(self) -> None:
        assert _map_priority(12.0) == 1

    def test_urgent_above_12(self) -> None:
        assert _map_priority(18.0) == 1

    def test_high_at_11(self) -> None:
        assert _map_priority(11.0) == 2

    def test_high_at_8(self) -> None:
        assert _map_priority(8.0) == 2

    def test_normal_at_7(self) -> None:
        assert _map_priority(7.0) == 3

    def test_normal_at_5(self) -> None:
        assert _map_priority(5.0) == 3

    def test_low_at_4(self) -> None:
        assert _map_priority(4.0) == 4

    def test_low_at_negative(self) -> None:
        assert _map_priority(-3.0) == 4

    def test_boundary_exactly_12(self) -> None:
        ticket = normalize_to_ticket(_make_scored(total_score=12.0))
        assert ticket.priority == 1

    def test_boundary_exactly_8(self) -> None:
        ticket = normalize_to_ticket(
            _make_scored(total_score=8.0, sla=ResponseSLA.PRIORITY_60MIN)
        )
        assert ticket.priority == 2

    def test_boundary_exactly_5(self) -> None:
        ticket = normalize_to_ticket(
            _make_scored(total_score=5.0, sla=ResponseSLA.STANDARD_4HR)
        )
        assert ticket.priority == 3

    def test_below_5(self) -> None:
        ticket = normalize_to_ticket(
            _make_scored(total_score=3.0, sla=ResponseSLA.BATCH_NEXT_DAY)
        )
        assert ticket.priority == 4


# ---------------------------------------------------------------------------
# Description quality
# ---------------------------------------------------------------------------


class TestDescriptionQuality:
    def test_description_at_least_300_chars(self) -> None:
        """Linear ticket quality gate: >= 300 chars."""
        ticket = normalize_to_ticket(_make_scored())
        assert len(ticket.description) >= 300, (
            f"Description only {len(ticket.description)} chars, need >= 300"
        )

    def test_sow_clause_always_present(self) -> None:
        """SOW clause from synthesis SS7 must always appear."""
        ticket = normalize_to_ticket(_make_scored())
        assert "separate estimate and agreement" in ticket.description

    def test_revision_limit_always_present(self) -> None:
        """2 revision rounds must always be stated (synthesis SS7)."""
        ticket = normalize_to_ticket(_make_scored())
        assert "2 revision rounds included" in ticket.description

    def test_loom_walkthrough_in_deliverables(self) -> None:
        """Loom video required in every delivery (synthesis SS8)."""
        ticket = normalize_to_ticket(_make_scored())
        assert "Loom walkthrough" in ticket.description

    def test_preview_buffer_in_deliverables(self) -> None:
        """DeepSeek preview buffer tactic in every delivery (synthesis SS8)."""
        ticket = normalize_to_ticket(_make_scored())
        assert "preview before final delivery" in ticket.description

    def test_source_contains_platform(self) -> None:
        ticket = normalize_to_ticket(_make_scored())
        assert "Platform: upwork" in ticket.description

    def test_source_contains_url(self) -> None:
        ticket = normalize_to_ticket(_make_scored())
        assert "https://www.upwork.com/jobs/123456" in ticket.description

    def test_source_contains_budget(self) -> None:
        ticket = normalize_to_ticket(_make_scored())
        assert "Budget: $400" in ticket.description

    def test_source_contains_score(self) -> None:
        ticket = normalize_to_ticket(_make_scored(total_score=14.0))
        assert "Scout Score: 14.0" in ticket.description


# ---------------------------------------------------------------------------
# Ticket metadata
# ---------------------------------------------------------------------------


class TestTicketMetadata:
    def test_title_has_scout_prefix(self) -> None:
        ticket = normalize_to_ticket(_make_scored())
        assert ticket.title.startswith("Scout: ")

    def test_team_id_is_prj(self) -> None:
        ticket = normalize_to_ticket(_make_scored())
        assert ticket.team_id == "db03ce09-7800-4b9e-941b-4820d141591d"

    def test_labels_include_scout(self) -> None:
        ticket = normalize_to_ticket(_make_scored())
        assert "scout" in ticket.labels

    def test_labels_include_category(self) -> None:
        ticket = normalize_to_ticket(_make_scored())
        assert "bug_fix" in ticket.labels

    def test_approved_listing_preserved(self) -> None:
        scored = _make_scored()
        ticket = normalize_to_ticket(scored)
        assert ticket.source_listing.scored_listing is scored
        assert ticket.source_listing.approved_by == "benjamin"

    def test_custom_approved_by(self) -> None:
        ticket = normalize_to_ticket(_make_scored(), approved_by="other_user")
        assert ticket.source_listing.approved_by == "other_user"


# ---------------------------------------------------------------------------
# Platform-specific assumptions
# ---------------------------------------------------------------------------


class TestPlatformAssumptions:
    def test_upwork_escrow(self) -> None:
        ticket = normalize_to_ticket(_make_scored(platform=Platform.UPWORK))
        assert "escrow" in ticket.description.lower()

    def test_freelancer_escrow(self) -> None:
        ticket = normalize_to_ticket(_make_scored(platform=Platform.FREELANCER))
        assert "milestone escrow" in ticket.description.lower()

    def test_reddit_no_escrow_warning(self) -> None:
        ticket = normalize_to_ticket(_make_scored(platform=Platform.REDDIT))
        assert "no platform escrow" in ticket.description.lower()


# ---------------------------------------------------------------------------
# Risk section
# ---------------------------------------------------------------------------


class TestRiskSection:
    def test_elevated_risk_shows_mitigation(self) -> None:
        """technical_risk=3 should produce a mitigation line."""
        ticket = normalize_to_ticket(_make_scored())
        assert "Mitigation:" in ticket.description

    def test_low_risk_no_elevated(self) -> None:
        """When all risk dims are low, say no elevated risks."""
        scored = _make_scored()
        # Override dimension scores to all low risk
        low_risk_dims = []
        for ds in scored.dimension_scores:
            if ds.dimension in ("risk", "technical_risk", "effort"):
                low_risk_dims.append(ds.model_copy(update={"score": 1}))
            else:
                low_risk_dims.append(ds)
        scored_low = scored.model_copy(update={"dimension_scores": low_risk_dims})
        ticket = normalize_to_ticket(scored_low)
        assert "No elevated risks" in ticket.description


# ---------------------------------------------------------------------------
# Category-specific acceptance criteria
# ---------------------------------------------------------------------------


class TestCategoryAcceptanceCriteria:
    def test_bug_fix_criteria(self) -> None:
        ticket = normalize_to_ticket(_make_scored(category=Category.BUG_FIX))
        assert "no longer reproducible" in ticket.description.lower()

    def test_web_scraping_criteria(self) -> None:
        ticket = normalize_to_ticket(_make_scored(category=Category.WEB_SCRAPING))
        assert "structured data" in ticket.description.lower()

    def test_api_integration_criteria(self) -> None:
        ticket = normalize_to_ticket(_make_scored(category=Category.API_INTEGRATION))
        assert "error handling" in ticket.description.lower()
