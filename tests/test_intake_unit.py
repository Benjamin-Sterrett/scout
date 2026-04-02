"""Unit tests for the Wave 2 multi-format intake parser.

Covers extractors (budget, urgency, tech keywords, red flags, category),
platform auto-detection, and platform-specific parsers (Upwork, Reddit, generic).
"""

from __future__ import annotations

from scout.intake import (
    _detect_platform,
    _extract_budget,
    _extract_category,
    _extract_red_flags,
    _extract_tech_keywords,
    _extract_urgency_signals,
    parse_listings,
)
from scout.models import Category, Platform, RawListing


# ---------------------------------------------------------------------------
# Platform auto-detection
# ---------------------------------------------------------------------------


class TestDetectPlatform:
    def test_detects_upwork_from_budget_and_skills_labels(self) -> None:
        text = "Fix my bug\nBudget: $300\nSkills: Python"
        assert _detect_platform(text) == Platform.UPWORK

    def test_detects_upwork_from_client_and_hire_rate(self) -> None:
        text = "Some job\nClient spent $1,000\nHire rate: 75%\nBudget: $200"
        assert _detect_platform(text) == Platform.UPWORK

    def test_detects_reddit_from_hiring_tag(self) -> None:
        text = "[HIRING] Need a Python developer for scraping project"
        assert _detect_platform(text) == Platform.REDDIT

    def test_detects_reddit_from_dm_me(self) -> None:
        text = "Looking for a developer. DM me."
        assert _detect_platform(text) == Platform.REDDIT

    def test_falls_back_to_freelancer_for_generic_text(self) -> None:
        text = "I need someone to help with my website."
        assert _detect_platform(text) == Platform.FREELANCER

    def test_upwork_single_budget_label_is_upwork(self) -> None:
        text = "Build a landing page\nBudget: $500"
        assert _detect_platform(text) == Platform.UPWORK


# ---------------------------------------------------------------------------
# Budget parsing
# ---------------------------------------------------------------------------


class TestExtractBudget:
    def test_single_labeled_budget(self) -> None:
        amount, inferred = _extract_budget("Budget: $500")
        assert amount == 500.0
        assert inferred is False

    def test_labeled_budget_with_comma(self) -> None:
        amount, inferred = _extract_budget("Budget: $1,200")
        assert amount == 1200.0
        assert inferred is False

    def test_labeled_budget_range_takes_midpoint(self) -> None:
        amount, inferred = _extract_budget("Budget: $500-1000")
        assert amount == 750.0
        assert inferred is True

    def test_labeled_budget_range_with_dollar_signs(self) -> None:
        amount, inferred = _extract_budget("Budget: $1,000-2,000")
        assert amount == 1500.0
        assert inferred is True

    def test_hourly_range_is_inferred(self) -> None:
        amount, inferred = _extract_budget("Rate: $50-100/hr for the project")
        assert amount == 75.0
        assert inferred is True

    def test_bare_dollar_amount(self) -> None:
        amount, inferred = _extract_budget("The budget is $400 for this task.")
        assert amount == 400.0
        assert inferred is True  # not labeled

    def test_no_budget_make_offer(self) -> None:
        amount, inferred = _extract_budget("Make me an offer, budget is flexible.")
        assert amount is None
        assert inferred is False

    def test_no_budget_empty_text(self) -> None:
        amount, inferred = _extract_budget("Just a short task, no budget mentioned.")
        assert amount is None

    def test_k_suffix_budget(self) -> None:
        amount, inferred = _extract_budget("Budget: $2k")
        assert amount == 2000.0
        assert inferred is False

    def test_labeled_budget_with_negotiable(self) -> None:
        """Codex finding #3: 'Budget: $500 negotiable' should return 500."""
        amount, inferred = _extract_budget("Budget: $500 negotiable")
        assert amount == 500.0
        assert inferred is False

    def test_client_metadata_not_treated_as_budget(self) -> None:
        """Codex finding #4: 'Client spent $5,000' must not be job budget."""
        amount, inferred = _extract_budget(
            "Fix bug\nClient spent $5,000\nHire rate: 70%"
        )
        assert amount is None


# ---------------------------------------------------------------------------
# Urgency signal extraction
# ---------------------------------------------------------------------------


class TestExtractUrgencySignals:
    def test_detects_asap(self) -> None:
        signals = _extract_urgency_signals(
            "We need this done ASAP, it's blocking production."
        )
        assert "asap" in signals

    def test_detects_today(self) -> None:
        signals = _extract_urgency_signals("Must be completed today or tomorrow.")
        assert "today" in signals

    def test_detects_urgent(self) -> None:
        signals = _extract_urgency_signals("URGENT: Fix the checkout flow immediately.")
        assert "urgent" in signals
        assert "immediately" in signals

    def test_detects_deadline_date(self) -> None:
        signals = _extract_urgency_signals("Project must be completed by Friday.")
        assert any("friday" in s.lower() for s in signals)

    def test_detects_emergency(self) -> None:
        signals = _extract_urgency_signals("This is an emergency fix needed.")
        assert "emergency" in signals

    def test_no_urgency_signals(self) -> None:
        signals = _extract_urgency_signals("Looking for a developer. No rush.")
        assert not any(s in signals for s in ["asap", "today", "urgent"])

    def test_deduplication(self) -> None:
        signals = _extract_urgency_signals("urgent URGENT urgent")
        assert signals.count("urgent") == 1


# ---------------------------------------------------------------------------
# Tech keyword extraction
# ---------------------------------------------------------------------------


class TestExtractTechKeywords:
    def test_detects_react(self) -> None:
        kws = _extract_tech_keywords("Built with React and Stripe.")
        assert "react" in kws
        assert "stripe" in kws

    def test_detects_nextjs(self) -> None:
        kws = _extract_tech_keywords("Our Next.js app needs a fix.")
        assert "next.js" in kws

    def test_detects_python(self) -> None:
        kws = _extract_tech_keywords("Need a Python script to automate this.")
        assert "python" in kws
        assert "automate" in kws

    def test_detects_wordpress_and_shopify(self) -> None:
        kws = _extract_tech_keywords("WordPress and Shopify integration.")
        assert "wordpress" in kws
        assert "shopify" in kws

    def test_detects_stripe(self) -> None:
        kws = _extract_tech_keywords("Add Stripe payment processing.")
        assert "stripe" in kws

    def test_case_insensitive(self) -> None:
        kws = _extract_tech_keywords("REACT and NODE.JS application.")
        assert "react" in kws
        assert "node.js" in kws

    def test_no_tech_keywords(self) -> None:
        kws = _extract_tech_keywords("Help me with my website please.")
        assert len(kws) == 0

    def test_deduplication(self) -> None:
        kws = _extract_tech_keywords("Python script in Python using Python.")
        assert kws.count("python") == 1


# ---------------------------------------------------------------------------
# Red flag extraction
# ---------------------------------------------------------------------------


class TestExtractRedFlags:
    def test_detects_equity(self) -> None:
        flags = _extract_red_flags("We offer equity compensation for this role.")
        assert "equity/revenue-share" in flags

    def test_detects_revenue_share(self) -> None:
        flags = _extract_red_flags("Compensation is revenue share once we launch.")
        assert "equity/revenue-share" in flags

    def test_detects_free_test_work(self) -> None:
        flags = _extract_red_flags("Please complete a test project before we hire.")
        assert "free-test-work" in flags

    def test_detects_trial_task(self) -> None:
        flags = _extract_red_flags("We require a trial task to evaluate candidates.")
        assert "free-test-work" in flags

    def test_detects_mvp_pattern(self) -> None:
        flags = _extract_red_flags("I want you to build my app from scratch.")
        assert "mvp/build-from-scratch" in flags

    def test_detects_quick_and_easy(self) -> None:
        flags = _extract_red_flags("This should be quick and easy for an expert.")
        assert "quick-and-easy" in flags

    def test_no_red_flags(self) -> None:
        flags = _extract_red_flags("Fix a bug in our checkout flow. Budget: $300.")
        assert len(flags) == 0

    def test_multiple_flags_one_per_group(self) -> None:
        flags = _extract_red_flags("Equity deal. Test project required. Build my app.")
        assert flags.count("equity/revenue-share") <= 1
        assert flags.count("free-test-work") <= 1
        assert flags.count("mvp/build-from-scratch") <= 1


# ---------------------------------------------------------------------------
# Category detection
# ---------------------------------------------------------------------------


class TestExtractCategory:
    def test_bug_fix_from_fix_keyword(self) -> None:
        cat = _extract_category("Please fix the broken login flow.", [])
        assert cat == Category.BUG_FIX

    def test_bug_fix_from_error_keyword(self) -> None:
        cat = _extract_category("Getting a TypeError on checkout.", [])
        assert cat == Category.BUG_FIX

    def test_web_scraping(self) -> None:
        cat = _extract_category("Need to scrape product data from 10 sites.", [])
        assert cat == Category.WEB_SCRAPING

    def test_api_integration(self) -> None:
        cat = _extract_category(
            "Integrate Stripe webhook into our app.", ["stripe", "webhook"]
        )
        assert cat == Category.API_INTEGRATION

    def test_automation_script(self) -> None:
        cat = _extract_category("Automate our daily report generation.", ["python"])
        assert cat == Category.AUTOMATION_SCRIPT

    def test_wordpress_shopify(self) -> None:
        cat = _extract_category("WordPress plugin needs configuration.", ["wordpress"])
        assert cat == Category.WORDPRESS_SHOPIFY

    def test_migration(self) -> None:
        cat = _extract_category("Migrate our site from WordPress to Next.js.", [])
        assert cat == Category.MIGRATION

    def test_unknown_returns_none(self) -> None:
        cat = _extract_category("I need a logo designed.", [])
        assert cat is None


# ---------------------------------------------------------------------------
# Platform-specific parser tests
# ---------------------------------------------------------------------------


class TestParseUpwork:
    def test_upwork_extracts_budget(self) -> None:
        raw = RawListing(
            platform=Platform.UPWORK,
            raw_text="Fix React bug\nWe need a React fix.\n\nBudget: $250\nSkills: React, JavaScript\nClient spent $1,500\nHire rate: 70%",
        )
        result = parse_listings([raw])[0]
        assert result.budget == 250.0
        assert "budget" not in result.inferred_fields

    def test_upwork_extracts_client_history(self) -> None:
        raw = RawListing(
            platform=Platform.UPWORK,
            raw_text="Python task\nShort Python task.\n\nBudget: $200\nSkills: Python\nClient spent $5,000\nHire rate: 82%",
        )
        result = parse_listings([raw])[0]
        assert result.client_spend_history == 5000.0
        assert result.client_hire_rate == 82.0

    def test_upwork_high_confidence_full_listing(self) -> None:
        raw = RawListing(
            platform=Platform.UPWORK,
            raw_text=(
                "Fix Stripe checkout TypeError\n"
                "Our checkout.js throws a TypeError when the cart has more than 10 items. "
                "Error: Cannot read property 'price' of undefined. Line 42. "
                "Repo access provided. Need fix with tests.\n\n"
                "Budget: $350\n"
                "Skills: JavaScript, React, Stripe\n"
                "Client spent $4,500\n"
                "Hire rate: 78%"
            ),
        )
        from scout.models import ParseConfidence

        result = parse_listings([raw])[0]
        assert result.parse_confidence == ParseConfidence.HIGH
        assert result.budget == 350.0

    def test_upwork_url_preserved(self) -> None:
        raw = RawListing(
            platform=Platform.UPWORK,
            raw_text="Fix bug\nDetails.\nBudget: $200\nSkills: Python",
            source_url="https://www.upwork.com/jobs/~test123",
        )
        result = parse_listings([raw])[0]
        assert result.url == "https://www.upwork.com/jobs/~test123"


class TestParseReddit:
    def test_reddit_strips_hiring_prefix(self) -> None:
        raw = RawListing(
            platform=Platform.REDDIT,
            raw_text="[HIRING] Python developer for API project\n\nLooking for someone to build an API integration.",
        )
        result = parse_listings([raw])[0]
        assert "[HIRING]" not in result.title
        assert "Python developer" in result.title

    def test_reddit_medium_confidence_structured(self) -> None:
        raw = RawListing(
            platform=Platform.REDDIT,
            raw_text=(
                "[HIRING] Python developer for Airtable/Slack API integration\n\n"
                "Looking for someone to connect Airtable to Slack using their APIs. "
                "When a row status changes, post to #team-updates. Budget around $400-500. "
                "DM me with examples."
            ),
        )
        from scout.models import ParseConfidence

        result = parse_listings([raw])[0]
        assert result.parse_confidence == ParseConfidence.MEDIUM
        assert result.platform == Platform.REDDIT

    def test_reddit_low_confidence_vague(self) -> None:
        raw = RawListing(
            platform=Platform.REDDIT,
            raw_text="[HIRING] need help with website",
        )
        from scout.models import ParseConfidence

        result = parse_listings([raw])[0]
        assert result.parse_confidence == ParseConfidence.LOW
        assert result.budget is None


class TestParseGeneric:
    def test_generic_first_line_is_title(self) -> None:
        raw = RawListing(
            platform=None,
            raw_text="URGENT: Fix WordPress contact form\nOur form stopped working. Budget is $200.",
        )
        result = parse_listings([raw])[0]
        assert "WordPress" in result.title or "URGENT" in result.title

    def test_generic_urgency_signals_extracted(self) -> None:
        raw = RawListing(
            platform=None,
            raw_text=(
                "URGENT: Fix broken contact form\n"
                "Our form stopped sending emails. We need this ASAP. "
                "WordPress site with Contact Form 7. Budget is $200."
            ),
        )
        result = parse_listings([raw])[0]
        assert "asap" in result.urgency_signals or "urgent" in result.urgency_signals
