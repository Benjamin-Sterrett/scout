"""Tests for Scout scoring engine (src/scout/scoring.py).

Tests cover dimension scoring, bonuses, SLA thresholds, gate-failure
rejection, and the full score_job orchestration flow.
"""

from __future__ import annotations

from scout.models import (
    GateVerdict,
    ParseConfidence,
    ParsedListing,
    Platform,
    ResponseSLA,
)
from scout.scoring import (
    DIMENSION_ANCHORS,
    RESPONSE_SLA_THRESHOLDS,
    _compute_total,
    calculate_bonuses,
    determine_sla,
    score_dimensions,
    score_job,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_listing(**overrides: object) -> ParsedListing:
    defaults: dict[str, object] = {
        "title": "Fix React bug",
        "description": "Button click handler throws TypeError in checkout flow.",
        "budget": 300.0,
        "platform": Platform.UPWORK,
        "client_spend_history": 5000.0,
        "client_hire_rate": 80.0,
        "parse_confidence": ParseConfidence.HIGH,
    }
    defaults.update(overrides)
    return ParsedListing(**defaults)  # type: ignore[arg-type]


_ALL_MID_SCORES: dict[str, int] = {
    "clarity": 3,
    "fit": 3,
    "price": 3,
    "urgency": 3,
    "effort": 3,
    "risk": 3,
    "client_risk": 3,
    "technical_risk": 3,
}


# ---------------------------------------------------------------------------
# Dimension scoring
# ---------------------------------------------------------------------------


class TestScoreDimensions:
    def test_returns_all_8_dimensions(self) -> None:
        listing = _make_listing()
        results = score_dimensions(listing, _ALL_MID_SCORES)
        assert len(results) == 8
        dim_names = {r.dimension for r in results}
        assert dim_names == set(DIMENSION_ANCHORS.keys())

    def test_weights_applied(self) -> None:
        listing = _make_listing()
        results = score_dimensions(listing, _ALL_MID_SCORES)
        clarity = next(r for r in results if r.dimension == "clarity")
        assert clarity.weight == 1.5
        price = next(r for r in results if r.dimension == "price")
        assert price.weight == 1.0

    def test_anchor_text_populated(self) -> None:
        listing = _make_listing()
        scores = {**_ALL_MID_SCORES, "clarity": 5}
        results = score_dimensions(listing, scores)
        clarity = next(r for r in results if r.dimension == "clarity")
        assert "Error log" in clarity.anchor_matched

    def test_scores_clamped_to_range(self) -> None:
        listing = _make_listing()
        scores = {**_ALL_MID_SCORES, "clarity": 10, "fit": -1}
        results = score_dimensions(listing, scores)
        clarity = next(r for r in results if r.dimension == "clarity")
        assert clarity.score == 5
        fit = next(r for r in results if r.dimension == "fit")
        assert fit.score == 1

    def test_missing_dimension_skipped(self) -> None:
        listing = _make_listing()
        partial = {"clarity": 4, "fit": 4}
        results = score_dimensions(listing, partial)
        assert len(results) == 2


# ---------------------------------------------------------------------------
# Total score computation
# ---------------------------------------------------------------------------


class TestComputeTotal:
    def test_formula_all_threes(self) -> None:
        """All 3s: (3*1.5 + 3*1.5 + 3 + 3) - (3 + 3 + 3 + 3) = 15 - 12 = 3."""
        listing = _make_listing()
        dim_scores = score_dimensions(listing, _ALL_MID_SCORES)
        total = _compute_total(dim_scores, [])
        assert total == 3.0

    def test_formula_best_case(self) -> None:
        """Best: (5*1.5 + 5*1.5 + 5 + 5) - (1 + 1 + 1 + 1) = 25 - 4 = 21."""
        listing = _make_listing()
        best = {
            "clarity": 5,
            "fit": 5,
            "price": 5,
            "urgency": 5,
            "effort": 1,
            "risk": 1,
            "client_risk": 1,
            "technical_risk": 1,
        }
        dim_scores = score_dimensions(listing, best)
        total = _compute_total(dim_scores, [])
        assert total == 21.0

    def test_formula_worst_case(self) -> None:
        """Worst: (1*1.5 + 1*1.5 + 1 + 1) - (5 + 5 + 5 + 5) = 5 - 20 = -15."""
        listing = _make_listing()
        worst = {
            "clarity": 1,
            "fit": 1,
            "price": 1,
            "urgency": 1,
            "effort": 5,
            "risk": 5,
            "client_risk": 5,
            "technical_risk": 5,
        }
        dim_scores = score_dimensions(listing, worst)
        total = _compute_total(dim_scores, [])
        assert total == -15.0

    def test_bonuses_added(self) -> None:
        from scout.models import Bonus

        listing = _make_listing()
        dim_scores = score_dimensions(listing, _ALL_MID_SCORES)
        bonuses = [Bonus(name="test", points=3, reason="test")]
        total = _compute_total(dim_scores, bonuses)
        assert total == 6.0  # 3.0 base + 3 bonus


# ---------------------------------------------------------------------------
# SLA determination
# ---------------------------------------------------------------------------


class TestDetermineSLA:
    def test_immediate_at_12(self) -> None:
        assert determine_sla(12.0) == ResponseSLA.IMMEDIATE_30MIN

    def test_immediate_above_12(self) -> None:
        assert determine_sla(18.0) == ResponseSLA.IMMEDIATE_30MIN

    def test_priority_at_11(self) -> None:
        assert determine_sla(11.0) == ResponseSLA.PRIORITY_60MIN

    def test_priority_at_8(self) -> None:
        assert determine_sla(8.0) == ResponseSLA.PRIORITY_60MIN

    def test_standard_at_7(self) -> None:
        assert determine_sla(7.0) == ResponseSLA.STANDARD_4HR

    def test_standard_at_5(self) -> None:
        assert determine_sla(5.0) == ResponseSLA.STANDARD_4HR

    def test_batch_at_4(self) -> None:
        assert determine_sla(4.0) == ResponseSLA.BATCH_NEXT_DAY

    def test_batch_at_3(self) -> None:
        assert determine_sla(3.0) == ResponseSLA.BATCH_NEXT_DAY

    def test_skip_at_2(self) -> None:
        assert determine_sla(2.0) == ResponseSLA.SKIP

    def test_skip_negative(self) -> None:
        assert determine_sla(-5.0) == ResponseSLA.SKIP


# ---------------------------------------------------------------------------
# Bonus detection
# ---------------------------------------------------------------------------


class TestBonuses:
    def test_urgency_premium_triggered(self) -> None:
        listing = _make_listing(
            budget=300.0,
            urgency_signals=["urgent", "ASAP"],
        )
        dim_scores = score_dimensions(listing, _ALL_MID_SCORES)
        bonuses = calculate_bonuses(listing, dim_scores)
        names = {b.name for b in bonuses}
        assert "urgency_premium" in names

    def test_urgency_premium_not_triggered_low_budget(self) -> None:
        listing = _make_listing(
            budget=100.0,
            urgency_signals=["urgent"],
        )
        dim_scores = score_dimensions(listing, _ALL_MID_SCORES)
        bonuses = calculate_bonuses(listing, dim_scores)
        names = {b.name for b in bonuses}
        assert "urgency_premium" not in names

    def test_tech_keywords_from_field(self) -> None:
        listing = _make_listing(tech_keywords=["react", "typescript"])
        dim_scores = score_dimensions(listing, _ALL_MID_SCORES)
        bonuses = calculate_bonuses(listing, dim_scores)
        names = {b.name for b in bonuses}
        assert "tech_keywords" in names

    def test_tech_keywords_from_description(self) -> None:
        listing = _make_listing(
            description="Fix a Python FastAPI endpoint that returns 500",
            tech_keywords=[],
        )
        dim_scores = score_dimensions(listing, _ALL_MID_SCORES)
        bonuses = calculate_bonuses(listing, dim_scores)
        names = {b.name for b in bonuses}
        assert "tech_keywords" in names

    def test_repeat_poster(self) -> None:
        listing = _make_listing(client_spend_history=5000.0)
        dim_scores = score_dimensions(listing, _ALL_MID_SCORES)
        bonuses = calculate_bonuses(listing, dim_scores)
        names = {b.name for b in bonuses}
        assert "repeat_poster" in names

    def test_repeat_poster_low_spend(self) -> None:
        listing = _make_listing(client_spend_history=500.0)
        dim_scores = score_dimensions(listing, _ALL_MID_SCORES)
        bonuses = calculate_bonuses(listing, dim_scores)
        names = {b.name for b in bonuses}
        assert "repeat_poster" not in names

    def test_reusable_asset_by_category(self) -> None:
        from scout.models import Category

        listing = _make_listing(category=Category.WEB_SCRAPING)
        dim_scores = score_dimensions(listing, _ALL_MID_SCORES)
        bonuses = calculate_bonuses(listing, dim_scores)
        names = {b.name for b in bonuses}
        assert "reusable_asset" in names

    def test_reusable_asset_by_keyword(self) -> None:
        listing = _make_listing(
            description="Create a reusable template for scraping",
        )
        dim_scores = score_dimensions(listing, _ALL_MID_SCORES)
        bonuses = calculate_bonuses(listing, dim_scores)
        names = {b.name for b in bonuses}
        assert "reusable_asset" in names


# ---------------------------------------------------------------------------
# Gate failure → rejected ScoredListing
# ---------------------------------------------------------------------------


class TestGateFailureRejection:
    def test_gate_failure_produces_rejected(self) -> None:
        listing = _make_listing(budget=50.0)
        result = score_job(listing, _ALL_MID_SCORES)
        assert result.rejected is True
        assert result.total_score == 0.0
        assert result.response_sla == ResponseSLA.SKIP
        assert result.dimension_scores == []
        assert result.bonuses == []
        assert "budget_floor" in (result.rejection_reason or "")

    def test_high_scores_still_rejected_on_gate(self) -> None:
        """Synthesis: 'Gate failures override score'."""
        high = {
            "clarity": 5,
            "fit": 5,
            "price": 5,
            "urgency": 5,
            "effort": 5,  # this triggers effort_ceiling gate
            "risk": 1,
            "client_risk": 1,
            "technical_risk": 1,
        }
        listing = _make_listing()
        result = score_job(listing, high)
        assert result.rejected is True
        assert "effort_ceiling" in (result.rejection_reason or "")

    def test_maybe_gates_set_needs_review(self) -> None:
        """MAYBE gates (no FAIL) -> scored normally with needs_review=True."""
        listing = _make_listing(budget=130.0)  # MAYBE budget
        scores = {**_ALL_MID_SCORES, "effort": 2}  # avoid effort MAYBE
        result = score_job(listing, scores)
        assert result.rejected is False
        assert result.needs_review is True
        assert result.total_score > 0
        assert len(result.dimension_scores) == 8

    def test_maybe_and_fail_still_rejected(self) -> None:
        """MAYBE + FAIL -> rejected (FAIL takes precedence)."""
        listing = _make_listing(budget=130.0)  # MAYBE budget
        scores = {**_ALL_MID_SCORES, "effort": 5}  # FAIL effort
        result = score_job(listing, scores)
        assert result.rejected is True
        assert "effort_ceiling" in (result.rejection_reason or "")

    def test_no_maybe_no_review_flag(self) -> None:
        """All PASS -> needs_review stays False."""
        listing = _make_listing()
        scores = {**_ALL_MID_SCORES, "effort": 2}
        result = score_job(listing, scores)
        assert result.rejected is False
        assert result.needs_review is False


# ---------------------------------------------------------------------------
# Full score_job flow
# ---------------------------------------------------------------------------


class TestScoreJobFlow:
    def test_passing_job_scored(self) -> None:
        listing = _make_listing()
        good_scores = {
            "clarity": 4,
            "fit": 5,
            "price": 4,
            "urgency": 4,
            "effort": 2,
            "risk": 2,
            "client_risk": 1,
            "technical_risk": 1,
        }
        result = score_job(listing, good_scores)
        assert result.rejected is False
        assert result.total_score > 0
        assert len(result.dimension_scores) == 8
        assert len(result.gate_results) == 8
        assert all(g.verdict == GateVerdict.PASS for g in result.gate_results)
        assert result.needs_review is False

    def test_score_formula_correct(self) -> None:
        """Verify formula: (4*1.5 + 5*1.5 + 4 + 4) - (2 + 2 + 1 + 1) = 21.5 - 6 = 15.5 + bonuses."""
        listing = _make_listing()
        scores = {
            "clarity": 4,
            "fit": 5,
            "price": 4,
            "urgency": 4,
            "effort": 2,
            "risk": 2,
            "client_risk": 1,
            "technical_risk": 1,
        }
        result = score_job(listing, scores)
        base = (4 * 1.5 + 5 * 1.5 + 4 + 4) - (2 + 2 + 1 + 1)
        assert base == 15.5
        bonus_total = sum(b.points for b in result.bonuses)
        assert result.total_score == base + bonus_total

    def test_sla_assigned(self) -> None:
        listing = _make_listing()
        good_scores = {
            "clarity": 5,
            "fit": 5,
            "price": 5,
            "urgency": 5,
            "effort": 1,
            "risk": 1,
            "client_risk": 1,
            "technical_risk": 1,
        }
        result = score_job(listing, good_scores)
        # Score = 21.0 + bonuses >= 12
        assert result.response_sla == ResponseSLA.IMMEDIATE_30MIN

    def test_dimension_anchors_complete(self) -> None:
        """Every dimension in DIMENSION_ANCHORS has 5 anchor levels."""
        for name, cfg in DIMENSION_ANCHORS.items():
            anchors = cfg["anchors"]
            assert isinstance(anchors, dict), f"{name} anchors not a dict"
            assert set(anchors.keys()) == {1, 2, 3, 4, 5}, (  # type: ignore[union-attr]
                f"{name} missing anchor levels"
            )

    def test_sla_thresholds_ordered(self) -> None:
        """Thresholds must be in descending order for first-match to work."""
        thresholds = [t[0] for t in RESPONSE_SLA_THRESHOLDS]
        assert thresholds == sorted(thresholds, reverse=True)
