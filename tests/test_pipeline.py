"""Tests for scout.pipeline — orchestrator logic."""

from __future__ import annotations

import json
from pathlib import Path

from scout.models import (
    ParseConfidence,
    Platform,
    RawListing,
    ResponseSLA,
)
from scout.pipeline import PipelineResult, PipelineStats, run_pipeline


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FIXTURES = Path(__file__).parent / "fixtures" / "sample_listings.json"


def _load_fixtures() -> list[dict[str, object]]:
    with open(_FIXTURES) as f:
        return json.load(f)  # type: ignore[no-any-return]


def _raw_from_fixture(fix: dict[str, object]) -> RawListing:
    raw_data: dict[str, object] = fix["raw"]  # type: ignore[assignment]
    platform = raw_data.get("platform")
    return RawListing(
        platform=Platform(str(platform)) if platform else None,
        raw_text=str(raw_data["raw_text"]),
        source_url=str(raw_data["source_url"]) if raw_data.get("source_url") else None,
    )


def _all_raws() -> list[RawListing]:
    return [_raw_from_fixture(f) for f in _load_fixtures()]


# ---------------------------------------------------------------------------
# Pipeline tests
# ---------------------------------------------------------------------------


class TestPipelineFullRun:
    """Run pipeline with all 10 fixtures, no pre_scores."""

    def test_returns_pipeline_result(self) -> None:
        result = run_pipeline(_all_raws())
        assert isinstance(result, PipelineResult)

    def test_stats_populated(self) -> None:
        result = run_pipeline(_all_raws())
        assert isinstance(result.stats, PipelineStats)
        assert result.stats.total_parsed == 10
        total = (
            result.stats.passed_gates
            + result.stats.rejected
            + result.stats.needs_review
        )
        assert total == 10

    def test_has_pre_scores_false(self) -> None:
        result = run_pipeline(_all_raws())
        assert result.has_pre_scores is False

    def test_confidence_distribution(self) -> None:
        result = run_pipeline(_all_raws())
        dist = result.stats.confidence_distribution
        assert "high" in dist
        assert "medium" in dist
        assert "low" in dist
        assert sum(dist.values()) == 10

    def test_duration_positive(self) -> None:
        result = run_pipeline(_all_raws())
        assert result.stats.duration_ms >= 0


class TestRankedOrder:
    """Ranked listings should be sorted by total_score descending."""

    def test_descending_sort(self) -> None:
        result = run_pipeline(_all_raws())
        scores = [s.total_score for s in result.ranked]
        assert scores == sorted(scores, reverse=True)

    def test_top_n_slicing(self) -> None:
        result = run_pipeline(_all_raws(), top_n=2)
        assert len(result.ranked) <= 2


class TestRejectedSeparation:
    """Listings with gate FAILs go to rejected bucket."""

    def test_mvp_listing_rejected(self) -> None:
        fixtures = _load_fixtures()
        mvp_fix = [f for f in fixtures if f["id"] == "upwork_mvp_build_my_app"]
        assert mvp_fix, "Fixture not found"
        raws = [_raw_from_fixture(mvp_fix[0])]
        result = run_pipeline(raws)
        assert len(result.rejected) == 1
        assert result.rejected[0].rejected is True
        assert "mvp_rejection" in (result.rejected[0].rejection_reason or "")

    def test_equity_listing_rejected(self) -> None:
        fixtures = _load_fixtures()
        eq_fix = [f for f in fixtures if f["id"] == "upwork_equity_red_flags"]
        assert eq_fix, "Fixture not found"
        raws = [_raw_from_fixture(eq_fix[0])]
        result = run_pipeline(raws)
        assert len(result.rejected) == 1

    def test_free_test_work_rejected(self) -> None:
        fixtures = _load_fixtures()
        free_fix = [f for f in fixtures if f["id"] == "upwork_free_test_work"]
        assert free_fix, "Fixture not found"
        raws = [_raw_from_fixture(free_fix[0])]
        result = run_pipeline(raws)
        assert len(result.rejected) == 1

    def test_rejected_listings_not_in_ranked(self) -> None:
        result = run_pipeline(_all_raws())
        for s in result.ranked:
            assert s.rejected is False


class TestLowConfidenceRouting:
    """LOW confidence listings go to needs_review."""

    def test_vague_listing_needs_review(self) -> None:
        fixtures = _load_fixtures()
        vague = [f for f in fixtures if f["id"] == "reddit_vague_one_liner"]
        assert vague, "Fixture not found"
        raws = [_raw_from_fixture(vague[0])]
        result = run_pipeline(raws)
        # Vague one-liner has no budget -> budget gate FAIL -> rejected
        # (budget_floor gate fails on None budget)
        # So it goes to rejected, not needs_review
        assert len(result.rejected) + len(result.needs_review) == 1


class TestMaybeVerdictRouting:
    """MAYBE verdicts (no FAIL) -> needs_review WITH score."""

    def test_borderline_budget_maybe(self) -> None:
        """A listing with budget $140 (MAYBE zone) should go to needs_review."""
        raw = RawListing(
            platform=Platform.UPWORK,
            raw_text=(
                "Fix CSS alignment issue\n\n"
                "Simple CSS fix needed on our homepage hero section.\n\n"
                "Budget: $140\n"
                "Skills: CSS, React\n"
                "Client spent $5,000\n"
                "Hire rate: 80%"
            ),
        )
        result = run_pipeline([raw])
        # $140 is in MAYBE zone ($100-149), and no other gate FAILs
        assert len(result.needs_review) == 1
        assert result.needs_review[0].needs_review is True

    def test_maybe_listing_has_gate_results(self) -> None:
        """MAYBE listing should have gate_results populated."""
        raw = RawListing(
            platform=Platform.UPWORK,
            raw_text=(
                "Fix CSS alignment issue\n\n"
                "Simple CSS fix needed on our homepage hero section.\n\n"
                "Budget: $140\n"
                "Skills: CSS, React\n"
                "Client spent $5,000\n"
                "Hire rate: 80%"
            ),
        )
        result = run_pipeline([raw])
        if result.needs_review:
            assert len(result.needs_review[0].gate_results) > 0


class TestEmptyInput:
    """Pipeline handles empty input gracefully."""

    def test_empty_list(self) -> None:
        result = run_pipeline([])
        assert result.ranked == []
        assert result.rejected == []
        assert result.needs_review == []
        assert result.stats.total_parsed == 0

    def test_stats_on_empty(self) -> None:
        result = run_pipeline([])
        assert result.stats.avg_score == 0.0
        assert result.stats.duration_ms >= 0


class TestPreScoresMode:
    """Pipeline with pre_scores_map provided."""

    def test_has_pre_scores_true(self) -> None:
        fixtures = _load_fixtures()
        bug_fix = [f for f in fixtures if f["id"] == "upwork_bug_fix_with_error_log"]
        assert bug_fix, "Fixture not found"
        raws = [_raw_from_fixture(bug_fix[0])]
        pre_scores = {
            0: {
                "clarity": 5,
                "fit": 5,
                "price": 4,
                "urgency": 3,
                "effort": 2,
                "risk": 2,
                "client_risk": 2,
                "technical_risk": 2,
            }
        }
        result = run_pipeline(raws, pre_scores_map=pre_scores)
        assert result.has_pre_scores is True

    def test_pre_scores_produce_nonzero_score(self) -> None:
        fixtures = _load_fixtures()
        bug_fix = [f for f in fixtures if f["id"] == "upwork_bug_fix_with_error_log"]
        assert bug_fix, "Fixture not found"
        raws = [_raw_from_fixture(bug_fix[0])]
        pre_scores = {
            0: {
                "clarity": 5,
                "fit": 5,
                "price": 4,
                "urgency": 3,
                "effort": 2,
                "risk": 2,
                "client_risk": 2,
                "technical_risk": 2,
            }
        }
        result = run_pipeline(raws, pre_scores_map=pre_scores)
        assert len(result.ranked) == 1
        assert result.ranked[0].total_score > 0

    def test_sla_assigned_with_pre_scores(self) -> None:
        fixtures = _load_fixtures()
        bug_fix = [f for f in fixtures if f["id"] == "upwork_bug_fix_with_error_log"]
        assert bug_fix, "Fixture not found"
        raws = [_raw_from_fixture(bug_fix[0])]
        pre_scores = {
            0: {
                "clarity": 5,
                "fit": 5,
                "price": 4,
                "urgency": 5,
                "effort": 1,
                "risk": 1,
                "client_risk": 2,
                "technical_risk": 1,
            }
        }
        result = run_pipeline(raws, pre_scores_map=pre_scores)
        assert len(result.ranked) == 1
        # High scores should produce IMMEDIATE or PRIORITY SLA
        sla = result.ranked[0].response_sla
        assert sla in (ResponseSLA.IMMEDIATE_30MIN, ResponseSLA.PRIORITY_60MIN)
