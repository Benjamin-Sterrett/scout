"""Tests for Scout pipeline stage contracts: ScoredListing, ApprovedListing, NormalizedTicket.

Covers: scoring result construction, gate consistency invariants, rejection
blocking, human override, extra='forbid' enforcement, priority constraints,
and full 5-level nested chain JSON round-trip.
"""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from scout.models import (
    ApprovedListing,
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


# ---------------------------------------------------------------------------
# ScoredListing tests
# ---------------------------------------------------------------------------


class TestScoredListing:
    @pytest.fixture()
    def scored(self) -> ScoredListing:
        parsed = ParsedListing(
            title="Fix React bug",
            description="TypeError on checkout",
            budget=400.0,
            platform=Platform.UPWORK,
            client_spend_history=8000.0,
            client_hire_rate=85.0,
            parse_confidence=ParseConfidence.HIGH,
            tech_keywords=["react", "typescript"],
        )
        return ScoredListing(
            parsed_listing=parsed,
            gate_results=[
                GateResult(gate="budget", verdict=GateVerdict.PASS, reason=">= $150"),
                GateResult(gate="effort", verdict=GateVerdict.PASS, reason="<= 3"),
            ],
            dimension_scores=[
                DimensionScore(
                    dimension="clarity",
                    score=4,
                    weight=1.5,
                    anchor_matched="Clear problem + context",
                    reasoning="Has error type and location",
                ),
            ],
            bonuses=[
                Bonus(name="urgency", points=2, reason="ASAP + budget > $200"),
            ],
            total_score=14.5,
            response_sla=ResponseSLA.IMMEDIATE_30MIN,
        )

    def test_instantiation(self, scored: ScoredListing) -> None:
        assert scored.total_score == 14.5
        assert scored.rejected is False
        assert scored.rejection_reason is None

    def test_rejected_listing(self) -> None:
        parsed = ParsedListing(
            title="Build my app",
            description="I have a great idea",
            platform=Platform.UPWORK,
            parse_confidence=ParseConfidence.LOW,
        )
        scored = ScoredListing(
            parsed_listing=parsed,
            gate_results=[
                GateResult(gate="clarity", verdict=GateVerdict.FAIL, reason="< 3"),
            ],
            dimension_scores=[],
            bonuses=[],
            total_score=0.0,
            response_sla=ResponseSLA.SKIP,
            rejected=True,
            rejection_reason="Failed clarity gate",
        )
        assert scored.rejected is True

    def test_json_round_trip(self, scored: ScoredListing) -> None:
        json_str = scored.model_dump_json()
        restored = ScoredListing.model_validate_json(json_str)
        assert restored == scored

    def test_failed_gate_requires_rejected_true(self) -> None:
        """If any gate failed, rejected must be True."""
        parsed = ParsedListing(
            title="t",
            description="d",
            platform=Platform.UPWORK,
            parse_confidence=ParseConfidence.LOW,
        )
        with pytest.raises(ValidationError, match="Gate.*failed but rejected=False"):
            ScoredListing(
                parsed_listing=parsed,
                gate_results=[
                    GateResult(
                        gate="budget", verdict=GateVerdict.FAIL, reason="< $150"
                    ),
                ],
                dimension_scores=[],
                bonuses=[],
                total_score=0.0,
                response_sla=ResponseSLA.SKIP,
                rejected=False,
            )

    def test_rejected_requires_reason(self) -> None:
        """rejected=True requires a non-empty rejection_reason."""
        parsed = ParsedListing(
            title="t",
            description="d",
            platform=Platform.UPWORK,
            parse_confidence=ParseConfidence.LOW,
        )
        with pytest.raises(ValidationError, match="rejection_reason"):
            ScoredListing(
                parsed_listing=parsed,
                gate_results=[],
                dimension_scores=[],
                bonuses=[],
                total_score=0.0,
                response_sla=ResponseSLA.SKIP,
                rejected=True,
                rejection_reason=None,
            )

    def test_scoring_types_reject_extra_fields(self) -> None:
        """DimensionScore, GateResult, Bonus also use extra='forbid'."""
        with pytest.raises(ValidationError):
            DimensionScore(
                dimension="clarity",
                score=3,
                weight=1.5,
                anchor_matched="test",
                reasoning="test",
                extra_field="nope",  # type: ignore[call-arg]
            )
        with pytest.raises(ValidationError):
            GateResult(
                gate="budget", verdict=GateVerdict.PASS, reason="ok", extra="nope"
            )  # type: ignore[call-arg]
        with pytest.raises(ValidationError):
            Bonus(name="urgency", points=2, reason="fast", extra="nope")  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# ApprovedListing tests
# ---------------------------------------------------------------------------


class TestApprovedListing:
    def test_instantiation(self) -> None:
        parsed = ParsedListing(
            title="Scrape product data",
            description="Extract pricing from 3 sites",
            budget=500.0,
            platform=Platform.FREELANCER,
            parse_confidence=ParseConfidence.HIGH,
        )
        scored = ScoredListing(
            parsed_listing=parsed,
            gate_results=[],
            dimension_scores=[],
            bonuses=[],
            total_score=12.0,
            response_sla=ResponseSLA.PRIORITY_60MIN,
        )
        approved = ApprovedListing(
            scored_listing=scored,
            approved_by="benjamin",
            approved_at=datetime(2026, 4, 1, 14, 30, tzinfo=timezone.utc),
            notes="Good fit, similar to last scraping job",
        )
        assert approved.approved_by == "benjamin"
        assert approved.notes is not None

    def test_rejected_listing_cannot_be_approved(self) -> None:
        """Gate failures override score -- rejected listings can't be approved."""
        parsed = ParsedListing(
            title="Build my app",
            description="I have a great idea",
            platform=Platform.UPWORK,
            parse_confidence=ParseConfidence.LOW,
        )
        scored = ScoredListing(
            parsed_listing=parsed,
            gate_results=[
                GateResult(gate="clarity", verdict=GateVerdict.FAIL, reason="< 3"),
            ],
            dimension_scores=[],
            bonuses=[],
            total_score=0.0,
            response_sla=ResponseSLA.SKIP,
            rejected=True,
            rejection_reason="Failed clarity gate",
        )
        with pytest.raises(ValidationError, match="Cannot approve a rejected listing"):
            ApprovedListing(
                scored_listing=scored,
                approved_by="benjamin",
                approved_at=datetime(2026, 4, 1, 14, 0, tzinfo=timezone.utc),
            )

    def test_rejected_listing_approved_with_override(self) -> None:
        """Human override allows approving a rejected listing."""
        parsed = ParsedListing(
            title="Edge case job",
            description="Rejected by gate but human wants it",
            platform=Platform.UPWORK,
            parse_confidence=ParseConfidence.MEDIUM,
        )
        scored = ScoredListing(
            parsed_listing=parsed,
            gate_results=[
                GateResult(gate="effort", verdict=GateVerdict.FAIL, reason="> 3"),
            ],
            dimension_scores=[],
            bonuses=[],
            total_score=0.0,
            response_sla=ResponseSLA.SKIP,
            rejected=True,
            rejection_reason="Failed effort gate",
        )
        approved = ApprovedListing(
            scored_listing=scored,
            approved_by="benjamin",
            approved_at=datetime(2026, 4, 1, 14, 0, tzinfo=timezone.utc),
            override=True,
            notes="Taking this one despite gate failure -- repeat client",
        )
        assert approved.override is True

    def test_extra_fields_rejected(self) -> None:
        """Pipeline contracts use extra='forbid'."""
        parsed = ParsedListing(
            title="t",
            description="d",
            platform=Platform.UPWORK,
            parse_confidence=ParseConfidence.HIGH,
        )
        scored = ScoredListing(
            parsed_listing=parsed,
            gate_results=[],
            dimension_scores=[],
            bonuses=[],
            total_score=5.0,
            response_sla=ResponseSLA.STANDARD_4HR,
        )
        with pytest.raises(ValidationError):
            ApprovedListing(
                scored_listing=scored,
                approved_by="test",
                approved_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                unknown_field="nope",  # type: ignore[call-arg]
            )


# ---------------------------------------------------------------------------
# NormalizedTicket tests
# ---------------------------------------------------------------------------


class TestNormalizedTicket:
    def test_instantiation(self) -> None:
        parsed = ParsedListing(
            title="Fix webhook",
            description="Stripe webhook broken",
            platform=Platform.UPWORK,
            parse_confidence=ParseConfidence.HIGH,
        )
        scored = ScoredListing(
            parsed_listing=parsed,
            gate_results=[],
            dimension_scores=[],
            bonuses=[],
            total_score=11.0,
            response_sla=ResponseSLA.PRIORITY_60MIN,
        )
        approved = ApprovedListing(
            scored_listing=scored,
            approved_by="benjamin",
            approved_at=datetime(2026, 4, 1, 15, 0, tzinfo=timezone.utc),
        )
        ticket = NormalizedTicket(
            title="Fix Stripe webhook after v3 upgrade",
            description="## Problem\nWebhook stopped...",
            priority=2,
            team_id="db03ce09-7800-4b9e-941b-4820d141591d",
            labels=["bug_fix", "stripe"],
            source_listing=approved,
        )
        assert ticket.priority == 2
        assert len(ticket.labels) == 2

    def test_priority_constraints(self) -> None:
        """Priority must be 1-4 (Linear priority range)."""
        parsed = ParsedListing(
            title="t",
            description="d",
            platform=Platform.REDDIT,
            parse_confidence=ParseConfidence.LOW,
        )
        scored = ScoredListing(
            parsed_listing=parsed,
            gate_results=[],
            dimension_scores=[],
            bonuses=[],
            total_score=0.0,
            response_sla=ResponseSLA.SKIP,
        )
        approved = ApprovedListing(
            scored_listing=scored,
            approved_by="test",
            approved_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        with pytest.raises(ValidationError):
            NormalizedTicket(
                title="t",
                description="d",
                priority=0,
                team_id="x",
                source_listing=approved,
            )
        with pytest.raises(ValidationError):
            NormalizedTicket(
                title="t",
                description="d",
                priority=5,
                team_id="x",
                source_listing=approved,
            )

    def test_full_chain_json_round_trip(self) -> None:
        """The entire 5-level nested chain survives JSON serialization."""
        parsed = ParsedListing(
            title="Fix React bug",
            description="TypeError in checkout",
            budget=400.0,
            platform=Platform.UPWORK,
            client_spend_history=3000.0,
            client_hire_rate=72.5,
            parse_confidence=ParseConfidence.HIGH,
            tech_keywords=["react"],
            urgency_signals=["ASAP"],
            category=Category.BUG_FIX,
        )
        scored = ScoredListing(
            parsed_listing=parsed,
            gate_results=[
                GateResult(gate="budget", verdict=GateVerdict.PASS, reason=">= $150"),
            ],
            dimension_scores=[
                DimensionScore(
                    dimension="clarity",
                    score=4,
                    weight=1.5,
                    anchor_matched="Clear problem",
                    reasoning="Has error type",
                ),
            ],
            bonuses=[
                Bonus(name="urgency", points=2, reason="ASAP signal"),
            ],
            total_score=14.0,
            response_sla=ResponseSLA.IMMEDIATE_30MIN,
        )
        approved = ApprovedListing(
            scored_listing=scored,
            approved_by="benjamin",
            approved_at=datetime(2026, 4, 1, 16, 0, tzinfo=timezone.utc),
        )
        ticket = NormalizedTicket(
            title="Fix React TypeError in checkout",
            description="## Problem\nTypeError when cart > 10 items",
            priority=1,
            team_id="db03ce09-7800-4b9e-941b-4820d141591d",
            labels=["bug_fix", "react", "urgent"],
            source_listing=approved,
        )

        json_str = ticket.model_dump_json()
        restored = NormalizedTicket.model_validate_json(json_str)
        assert restored == ticket
        assert restored.source_listing.scored_listing.parsed_listing.budget == 400.0
        assert (
            restored.source_listing.scored_listing.parsed_listing.client_hire_rate
            == 72.5
        )
