"""Tests for Scout core data models: enums, scoring types, RawListing, ParsedListing.

Covers: enum values/counts, JSON serialization, Field constraint validation,
extra='forbid' enforcement, and numeric bounds on financial fields.
"""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from scout.models import (
    Bonus,
    Category,
    DimensionScore,
    GateResult,
    GateVerdict,
    ParseConfidence,
    ParsedListing,
    Platform,
    RawListing,
    ResponseSLA,
)


# ---------------------------------------------------------------------------
# Enum tests
# ---------------------------------------------------------------------------


class TestEnums:
    def test_platform_values(self) -> None:
        assert Platform.UPWORK.value == "upwork"
        assert Platform.GUN_IO.value == "gun_io"
        assert len(Platform) == 8

    def test_category_values(self) -> None:
        assert Category.BUG_FIX.value == "bug_fix"
        assert Category.OTHER.value == "other"
        assert len(Category) == 8

    def test_parse_confidence_values(self) -> None:
        assert ParseConfidence.HIGH.value == "high"
        assert ParseConfidence.LOW.value == "low"
        assert len(ParseConfidence) == 3

    def test_response_sla_values(self) -> None:
        assert ResponseSLA.IMMEDIATE_30MIN.value == "immediate_30min"
        assert ResponseSLA.SKIP.value == "skip"
        assert len(ResponseSLA) == 5

    def test_enum_json_serialization(self) -> None:
        raw = RawListing(platform=Platform.UPWORK, raw_text="test")
        data = raw.model_dump(mode="json")
        assert data["platform"] == "upwork"


# ---------------------------------------------------------------------------
# Scoring type tests
# ---------------------------------------------------------------------------


class TestScoringTypes:
    def test_dimension_score_valid(self) -> None:
        ds = DimensionScore(
            dimension="clarity",
            score=4,
            weight=1.5,
            anchor_matched="Clear problem + some context",
            reasoning="Has description and tech stack",
        )
        assert ds.score == 4
        assert ds.weight == 1.5

    def test_dimension_score_min_max(self) -> None:
        DimensionScore(
            dimension="fit",
            score=1,
            weight=1.0,
            anchor_matched="min",
            reasoning="min",
        )
        DimensionScore(
            dimension="fit",
            score=5,
            weight=1.0,
            anchor_matched="max",
            reasoning="max",
        )

    def test_dimension_score_below_min(self) -> None:
        with pytest.raises(ValidationError):
            DimensionScore(
                dimension="fit",
                score=0,
                weight=1.0,
                anchor_matched="bad",
                reasoning="bad",
            )

    def test_dimension_score_above_max(self) -> None:
        with pytest.raises(ValidationError):
            DimensionScore(
                dimension="fit",
                score=6,
                weight=1.0,
                anchor_matched="bad",
                reasoning="bad",
            )

    def test_gate_result(self) -> None:
        gr = GateResult(gate="budget", verdict=GateVerdict.FAIL, reason="Below $150")
        assert gr.verdict == GateVerdict.FAIL

    def test_bonus(self) -> None:
        b = Bonus(name="urgency", points=2, reason="ASAP + budget > $200")
        assert b.points == 2


# ---------------------------------------------------------------------------
# RawListing tests
# ---------------------------------------------------------------------------


class TestRawListing:
    def test_minimal(self) -> None:
        raw = RawListing(raw_text="Fix my React bug ASAP")
        assert raw.platform is None
        assert raw.source_url is None

    def test_full(self) -> None:
        raw = RawListing(
            platform=Platform.UPWORK,
            raw_text="Fix my React bug",
            source_url="https://upwork.com/jobs/123",
        )
        assert raw.platform == Platform.UPWORK

    def test_json_round_trip(self) -> None:
        raw = RawListing(
            platform=Platform.FIVERR,
            raw_text="scrape data",
            source_url="https://fiverr.com/gig/1",
        )
        json_str = raw.model_dump_json()
        restored = RawListing.model_validate_json(json_str)
        assert restored == raw


# ---------------------------------------------------------------------------
# ParsedListing tests
# ---------------------------------------------------------------------------


class TestParsedListing:
    @pytest.fixture()
    def parsed(self) -> ParsedListing:
        return ParsedListing(
            title="Fix Stripe webhook",
            description="Webhook stopped after upgrade to v3",
            budget=350.0,
            platform=Platform.UPWORK,
            url="https://upwork.com/jobs/456",
            client_spend_history=5200.0,
            client_hire_rate=78.0,
            posted_at=datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc),
            tech_keywords=["stripe", "node.js", "webhook"],
            urgency_signals=["ASAP"],
            red_flags=[],
            parse_confidence=ParseConfidence.HIGH,
            inferred_fields=[],
            category=Category.API_INTEGRATION,
        )

    def test_instantiation(self, parsed: ParsedListing) -> None:
        assert parsed.budget == 350.0
        assert parsed.parse_confidence == ParseConfidence.HIGH
        assert parsed.client_spend_history == 5200.0
        assert parsed.client_hire_rate == 78.0

    def test_optional_fields_default_none(self) -> None:
        p = ParsedListing(
            title="test",
            description="test desc",
            platform=Platform.REDDIT,
            parse_confidence=ParseConfidence.LOW,
        )
        assert p.budget is None
        assert p.client_spend_history is None
        assert p.client_hire_rate is None
        assert p.posted_at is None
        assert p.url is None
        assert p.category is None
        assert p.tech_keywords == []
        assert p.inferred_fields == []

    def test_json_round_trip(self, parsed: ParsedListing) -> None:
        json_str = parsed.model_dump_json()
        restored = ParsedListing.model_validate_json(json_str)
        assert restored == parsed

    def test_inferred_fields_tracked(self) -> None:
        p = ParsedListing(
            title="Vague job",
            description="fix something",
            platform=Platform.FREELANCER,
            parse_confidence=ParseConfidence.MEDIUM,
            inferred_fields=["budget", "tech_keywords"],
        )
        assert "budget" in p.inferred_fields

    def test_negative_budget_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ParsedListing(
                title="t",
                description="d",
                budget=-50.0,
                platform=Platform.UPWORK,
                parse_confidence=ParseConfidence.HIGH,
            )

    def test_negative_client_spend_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ParsedListing(
                title="t",
                description="d",
                client_spend_history=-1.0,
                platform=Platform.UPWORK,
                parse_confidence=ParseConfidence.HIGH,
            )

    def test_hire_rate_over_100_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ParsedListing(
                title="t",
                description="d",
                client_hire_rate=150.0,
                platform=Platform.UPWORK,
                parse_confidence=ParseConfidence.HIGH,
            )

    def test_hire_rate_negative_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ParsedListing(
                title="t",
                description="d",
                client_hire_rate=-5.0,
                platform=Platform.UPWORK,
                parse_confidence=ParseConfidence.HIGH,
            )

    def test_extra_fields_rejected(self) -> None:
        """Pipeline contracts use extra='forbid' to catch schema drift."""
        with pytest.raises(ValidationError):
            ParsedListing(
                title="t",
                description="d",
                platform=Platform.UPWORK,
                parse_confidence=ParseConfidence.HIGH,
                bogus_field="should fail",  # type: ignore[call-arg]
            )
