"""Integration tests for the Wave 2 intake parser.

Covers parse confidence assignment, inferred_fields tracking,
multi-listing batch parsing, and fixture-driven smoke tests.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scout.intake import parse_listings
from scout.models import Category, ParseConfidence, Platform, RawListing

FIXTURES_PATH = Path(__file__).parent / "fixtures" / "sample_listings.json"


def load_fixtures() -> list[dict[str, object]]:
    data: list[dict[str, object]] = json.loads(FIXTURES_PATH.read_text())
    return data


def raw_from_fixture(fx: dict[str, object]) -> RawListing:
    r: dict[str, object] = fx["raw"]  # type: ignore[assignment]
    platform_val = r.get("platform")
    raw_text = str(r["raw_text"])
    source_url_val = r.get("source_url")
    source_url = str(source_url_val) if source_url_val else None
    return RawListing(
        platform=Platform(str(platform_val)) if platform_val else None,
        raw_text=raw_text,
        source_url=source_url,
    )


# ---------------------------------------------------------------------------
# Parse confidence tests
# ---------------------------------------------------------------------------


class TestParseConfidence:
    def test_high_confidence_full_data(self) -> None:
        """Budget + long description + tech keywords = HIGH."""
        raw = RawListing(
            platform=Platform.UPWORK,
            raw_text=(
                "Integrate Stripe webhooks into Next.js app\n"
                "We need to handle payment events from Stripe in our Next.js application. "
                "The webhook endpoint exists but events are not being processed correctly. "
                "API keys and staging environment available.\n\n"
                "Budget: $600\n"
                "Skills: Next.js, Stripe, webhook\n"
                "Client spent $12,000\n"
                "Hire rate: 85%"
            ),
        )
        result = parse_listings([raw])[0]
        assert result.parse_confidence == ParseConfidence.HIGH

    def test_medium_confidence_inferred_budget(self) -> None:
        """Budget range (inferred midpoint) with tech = MEDIUM."""
        raw = RawListing(
            platform=Platform.REDDIT,
            raw_text=(
                "[HIRING] API integration Python developer\n"
                "Need to connect two services via REST API. Budget around $400-500. "
                "Python preferred. DM me."
            ),
        )
        result = parse_listings([raw])[0]
        assert result.parse_confidence == ParseConfidence.MEDIUM

    def test_low_confidence_vague(self) -> None:
        """No budget, short description, no keywords = LOW."""
        raw = RawListing(
            platform=Platform.REDDIT,
            raw_text="[HIRING] need help with website",
        )
        result = parse_listings([raw])[0]
        assert result.parse_confidence == ParseConfidence.LOW


# ---------------------------------------------------------------------------
# inferred_fields tracking
# ---------------------------------------------------------------------------


class TestInferredFields:
    def test_clean_upwork_budget_not_inferred(self) -> None:
        raw = RawListing(
            platform=Platform.UPWORK,
            raw_text="Fix Python bug\nDetails here.\nBudget: $300\nSkills: Python",
        )
        result = parse_listings([raw])[0]
        assert "budget" not in result.inferred_fields

    def test_range_budget_is_inferred(self) -> None:
        raw = RawListing(
            platform=Platform.UPWORK,
            raw_text="Migrate site\nMigrate our WordPress site.\nBudget: $500-1000\nSkills: WordPress, Next.js",
        )
        result = parse_listings([raw])[0]
        assert "budget" in result.inferred_fields

    def test_auto_detected_platform_is_inferred(self) -> None:
        raw = RawListing(
            platform=None,
            raw_text="[HIRING] Python developer needed for short task.",
        )
        result = parse_listings([raw])[0]
        assert "platform" in result.inferred_fields

    def test_explicit_platform_not_inferred(self) -> None:
        raw = RawListing(
            platform=Platform.UPWORK,
            raw_text="Fix bug\nDescription.\nBudget: $200\nSkills: Python",
        )
        result = parse_listings([raw])[0]
        assert "platform" not in result.inferred_fields


# ---------------------------------------------------------------------------
# Multi-listing batch parsing
# ---------------------------------------------------------------------------


class TestBatchParsing:
    def test_five_listings_produce_five_results(self) -> None:
        raws = [
            RawListing(
                platform=Platform.UPWORK,
                raw_text=f"Job {i}\nDesc.\nBudget: $200\nSkills: Python",
            )
            for i in range(5)
        ]
        results = parse_listings(raws)
        assert len(results) == 5

    def test_mixed_platforms_all_parsed(self) -> None:
        raws = [
            RawListing(
                platform=Platform.UPWORK,
                raw_text="Fix bug\nUpwork bug.\nBudget: $300\nSkills: Python",
            ),
            RawListing(
                platform=Platform.REDDIT,
                raw_text="[HIRING] Python task\nNeed Python dev.",
            ),
            RawListing(
                platform=None,
                raw_text="Need help with API integration. Budget is $400.",
            ),
        ]
        results = parse_listings(raws)
        assert len(results) == 3
        assert results[0].platform == Platform.UPWORK
        assert results[1].platform == Platform.REDDIT

    def test_empty_list_returns_empty(self) -> None:
        assert parse_listings([]) == []


# ---------------------------------------------------------------------------
# Fixture-driven integration tests
# ---------------------------------------------------------------------------


class TestFixtures:
    """Smoke tests against all 10 sample fixtures."""

    fixtures = load_fixtures()

    @pytest.mark.parametrize("fx", fixtures, ids=[str(f["id"]) for f in fixtures])
    def test_fixture_parses_without_error(self, fx: dict[str, object]) -> None:
        raw = raw_from_fixture(fx)
        results = parse_listings([raw])
        assert len(results) == 1
        assert isinstance(results[0].parse_confidence, ParseConfidence)

    def test_upwork_bug_fix_high_confidence(self) -> None:
        fx = next(
            f for f in self.fixtures if f["id"] == "upwork_bug_fix_with_error_log"
        )
        result = parse_listings([raw_from_fixture(fx)])[0]
        assert result.parse_confidence == ParseConfidence.HIGH
        assert result.budget == 350.0
        assert result.category == Category.BUG_FIX

    def test_upwork_mvp_flags_red_flag(self) -> None:
        fx = next(f for f in self.fixtures if f["id"] == "upwork_mvp_build_my_app")
        result = parse_listings([raw_from_fixture(fx)])[0]
        assert "mvp/build-from-scratch" in result.red_flags

    def test_reddit_vague_is_low_confidence(self) -> None:
        fx = next(f for f in self.fixtures if f["id"] == "reddit_vague_one_liner")
        result = parse_listings([raw_from_fixture(fx)])[0]
        assert result.parse_confidence == ParseConfidence.LOW

    def test_equity_listing_flags_equity(self) -> None:
        fx = next(f for f in self.fixtures if f["id"] == "upwork_equity_red_flags")
        result = parse_listings([raw_from_fixture(fx)])[0]
        assert "equity/revenue-share" in result.red_flags

    def test_free_test_work_flagged(self) -> None:
        fx = next(f for f in self.fixtures if f["id"] == "upwork_free_test_work")
        result = parse_listings([raw_from_fixture(fx)])[0]
        assert "free-test-work" in result.red_flags

    def test_scraping_is_correct_category(self) -> None:
        fx = next(
            f
            for f in self.fixtures
            if f["id"] == "upwork_web_scraping_clear_deliverables"
        )
        result = parse_listings([raw_from_fixture(fx)])[0]
        assert result.category == Category.WEB_SCRAPING

    def test_budget_range_midpoint(self) -> None:
        fx = next(f for f in self.fixtures if f["id"] == "upwork_budget_range")
        result = parse_listings([raw_from_fixture(fx)])[0]
        assert result.budget == 750.0
        assert "budget" in result.inferred_fields

    def test_urgent_listing_has_urgency_signals(self) -> None:
        fx = next(f for f in self.fixtures if f["id"] == "generic_urgent_listing")
        result = parse_listings([raw_from_fixture(fx)])[0]
        assert len(result.urgency_signals) > 0

    def test_full_upwork_api_integration_high_confidence(self) -> None:
        fx = next(f for f in self.fixtures if f["id"] == "upwork_api_integration_full")
        result = parse_listings([raw_from_fixture(fx)])[0]
        assert result.parse_confidence == ParseConfidence.HIGH
        assert result.client_spend_history == 12000.0
        assert result.client_hire_rate == 85.0
