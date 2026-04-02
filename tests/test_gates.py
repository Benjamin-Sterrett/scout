"""Tests for Scout hard gates (src/scout/gates.py).

Each of the 8 gates is tested individually with PASS/FAIL/MAYBE
verdicts, plus all-pass and multi-failure scenarios.
"""

from __future__ import annotations

import pytest

from scout.gates import check_gates
from scout.models import GateVerdict, ParseConfidence, ParsedListing, Platform


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_listing(**overrides: object) -> ParsedListing:
    """Build a minimal valid ParsedListing, overriding specific fields."""
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


_ALL_PASS_SCORES: dict[str, int] = {
    "clarity": 4,
    "fit": 4,
    "effort": 2,
    "price": 4,
    "urgency": 3,
    "risk": 2,
    "client_risk": 2,
    "technical_risk": 2,
}


def _get_gate(results: list[object], name: str) -> object:
    """Extract a gate result by name."""
    return next(r for r in results if r.gate == name)  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Gate 1: budget_floor
# ---------------------------------------------------------------------------


class TestBudgetFloor:
    def test_above_floor_passes(self) -> None:
        listing = _make_listing(budget=200.0)
        results = check_gates(listing, _ALL_PASS_SCORES)
        gate = _get_gate(results, "budget_floor")
        assert gate.verdict == GateVerdict.PASS  # type: ignore[union-attr]

    def test_at_floor_passes(self) -> None:
        listing = _make_listing(budget=150.0)
        results = check_gates(listing, _ALL_PASS_SCORES)
        gate = _get_gate(results, "budget_floor")
        assert gate.verdict == GateVerdict.PASS  # type: ignore[union-attr]

    def test_below_floor_fails(self) -> None:
        listing = _make_listing(budget=50.0)
        results = check_gates(listing, _ALL_PASS_SCORES)
        gate = _get_gate(results, "budget_floor")
        assert gate.verdict == GateVerdict.FAIL  # type: ignore[union-attr]
        assert "$50" in gate.reason  # type: ignore[union-attr]

    def test_no_budget_fails(self) -> None:
        listing = _make_listing(budget=None)
        results = check_gates(listing, _ALL_PASS_SCORES)
        gate = _get_gate(results, "budget_floor")
        assert gate.verdict == GateVerdict.FAIL  # type: ignore[union-attr]

    def test_borderline_budget_maybe(self) -> None:
        """$100-149 is close to floor -- MAYBE."""
        listing = _make_listing(budget=145.0)
        results = check_gates(listing, _ALL_PASS_SCORES)
        gate = _get_gate(results, "budget_floor")
        assert gate.verdict == GateVerdict.MAYBE  # type: ignore[union-attr]
        assert "borderline" in gate.reason.lower()  # type: ignore[union-attr]

    def test_at_maybe_floor_is_maybe(self) -> None:
        """$100 exactly is still MAYBE (>= BUDGET_MAYBE_FLOOR)."""
        listing = _make_listing(budget=100.0)
        results = check_gates(listing, _ALL_PASS_SCORES)
        gate = _get_gate(results, "budget_floor")
        assert gate.verdict == GateVerdict.MAYBE  # type: ignore[union-attr]

    def test_below_maybe_floor_fails(self) -> None:
        """$99 is below the MAYBE floor -- FAIL."""
        listing = _make_listing(budget=99.0)
        results = check_gates(listing, _ALL_PASS_SCORES)
        gate = _get_gate(results, "budget_floor")
        assert gate.verdict == GateVerdict.FAIL  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Gate 2: effort_ceiling
# ---------------------------------------------------------------------------


class TestEffortCeiling:
    def test_effort_2_passes(self) -> None:
        scores = {**_ALL_PASS_SCORES, "effort": 2}
        results = check_gates(_make_listing(), scores)
        gate = _get_gate(results, "effort_ceiling")
        assert gate.verdict == GateVerdict.PASS  # type: ignore[union-attr]

    def test_effort_1_passes(self) -> None:
        scores = {**_ALL_PASS_SCORES, "effort": 1}
        results = check_gates(_make_listing(), scores)
        gate = _get_gate(results, "effort_ceiling")
        assert gate.verdict == GateVerdict.PASS  # type: ignore[union-attr]

    def test_effort_3_maybe(self) -> None:
        """Effort 3 (3-6 hours) is at the boundary -- MAYBE."""
        scores = {**_ALL_PASS_SCORES, "effort": 3}
        results = check_gates(_make_listing(), scores)
        gate = _get_gate(results, "effort_ceiling")
        assert gate.verdict == GateVerdict.MAYBE  # type: ignore[union-attr]
        assert "borderline" in gate.reason.lower()  # type: ignore[union-attr]

    def test_effort_4_fails(self) -> None:
        scores = {**_ALL_PASS_SCORES, "effort": 4}
        results = check_gates(_make_listing(), scores)
        gate = _get_gate(results, "effort_ceiling")
        assert gate.verdict == GateVerdict.FAIL  # type: ignore[union-attr]

    def test_effort_5_fails(self) -> None:
        scores = {**_ALL_PASS_SCORES, "effort": 5}
        results = check_gates(_make_listing(), scores)
        gate = _get_gate(results, "effort_ceiling")
        assert gate.verdict == GateVerdict.FAIL  # type: ignore[union-attr]

    def test_no_scores_skips(self) -> None:
        results = check_gates(_make_listing(), None)
        gate = _get_gate(results, "effort_ceiling")
        assert gate.verdict == GateVerdict.PASS  # type: ignore[union-attr]
        assert "skipped" in gate.reason.lower()  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Gate 3: clarity_floor
# ---------------------------------------------------------------------------


class TestClarityFloor:
    def test_clarity_3_passes(self) -> None:
        scores = {**_ALL_PASS_SCORES, "clarity": 3}
        results = check_gates(_make_listing(), scores)
        gate = _get_gate(results, "clarity_floor")
        assert gate.verdict == GateVerdict.PASS  # type: ignore[union-attr]

    def test_clarity_2_fails(self) -> None:
        scores = {**_ALL_PASS_SCORES, "clarity": 2}
        results = check_gates(_make_listing(), scores)
        gate = _get_gate(results, "clarity_floor")
        assert gate.verdict == GateVerdict.FAIL  # type: ignore[union-attr]

    def test_clarity_1_fails(self) -> None:
        scores = {**_ALL_PASS_SCORES, "clarity": 1}
        results = check_gates(_make_listing(), scores)
        gate = _get_gate(results, "clarity_floor")
        assert gate.verdict == GateVerdict.FAIL  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Gate 4: fit_floor
# ---------------------------------------------------------------------------


class TestFitFloor:
    def test_fit_3_passes(self) -> None:
        scores = {**_ALL_PASS_SCORES, "fit": 3}
        results = check_gates(_make_listing(), scores)
        gate = _get_gate(results, "fit_floor")
        assert gate.verdict == GateVerdict.PASS  # type: ignore[union-attr]

    def test_fit_2_fails(self) -> None:
        scores = {**_ALL_PASS_SCORES, "fit": 2}
        results = check_gates(_make_listing(), scores)
        gate = _get_gate(results, "fit_floor")
        assert gate.verdict == GateVerdict.FAIL  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Gate 5: payment_verified
# ---------------------------------------------------------------------------


class TestPaymentVerified:
    def test_has_both_passes(self) -> None:
        listing = _make_listing(client_spend_history=1000.0, client_hire_rate=80.0)
        results = check_gates(listing, _ALL_PASS_SCORES)
        gate = _get_gate(results, "payment_verified")
        assert gate.verdict == GateVerdict.PASS  # type: ignore[union-attr]

    def test_has_spend_only_maybe(self) -> None:
        """Only spend history -- partial data, MAYBE."""
        listing = _make_listing(client_spend_history=500.0, client_hire_rate=None)
        results = check_gates(listing, _ALL_PASS_SCORES)
        gate = _get_gate(results, "payment_verified")
        assert gate.verdict == GateVerdict.MAYBE  # type: ignore[union-attr]
        assert "hire rate" in gate.reason.lower()  # type: ignore[union-attr]

    def test_has_hire_rate_only_maybe(self) -> None:
        """Only hire rate -- partial data, MAYBE."""
        listing = _make_listing(client_spend_history=None, client_hire_rate=60.0)
        results = check_gates(listing, _ALL_PASS_SCORES)
        gate = _get_gate(results, "payment_verified")
        assert gate.verdict == GateVerdict.MAYBE  # type: ignore[union-attr]
        assert "spend history" in gate.reason.lower()  # type: ignore[union-attr]

    def test_both_none_fails(self) -> None:
        listing = _make_listing(client_spend_history=None, client_hire_rate=None)
        results = check_gates(listing, _ALL_PASS_SCORES)
        gate = _get_gate(results, "payment_verified")
        assert gate.verdict == GateVerdict.FAIL  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Gate 6: mvp_rejection
# ---------------------------------------------------------------------------


class TestMvpRejection:
    @pytest.mark.parametrize(
        "text",
        [
            "I need someone to build my app",
            "Build from scratch a social media platform",
            "I have an idea for a startup",
            "Build the MVP for my project",
            "Need an app built from the ground up",
        ],
    )
    def test_mvp_keywords_fail(self, text: str) -> None:
        listing = _make_listing(description=text)
        results = check_gates(listing, _ALL_PASS_SCORES)
        gate = _get_gate(results, "mvp_rejection")
        assert gate.verdict == GateVerdict.FAIL  # type: ignore[union-attr]

    def test_clean_description_passes(self) -> None:
        listing = _make_listing(description="Fix a bug in React checkout flow")
        results = check_gates(listing, _ALL_PASS_SCORES)
        gate = _get_gate(results, "mvp_rejection")
        assert gate.verdict == GateVerdict.PASS  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Gate 7: equity_rejection
# ---------------------------------------------------------------------------


class TestEquityRejection:
    @pytest.mark.parametrize(
        "text",
        [
            "Offering equity instead of payment",
            "Revenue share model for co-founders",
            "Profit sharing arrangement",
            "Looking for a cofounder",
        ],
    )
    def test_equity_keywords_fail(self, text: str) -> None:
        listing = _make_listing(description=text)
        results = check_gates(listing, _ALL_PASS_SCORES)
        gate = _get_gate(results, "equity_rejection")
        assert gate.verdict == GateVerdict.FAIL  # type: ignore[union-attr]

    def test_clean_description_passes(self) -> None:
        listing = _make_listing(description="Fixed price $500 for API integration")
        results = check_gates(listing, _ALL_PASS_SCORES)
        gate = _get_gate(results, "equity_rejection")
        assert gate.verdict == GateVerdict.PASS  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Gate 8: free_work_rejection
# ---------------------------------------------------------------------------


class TestFreeWorkRejection:
    @pytest.mark.parametrize(
        "text",
        [
            "Please do a free test before we hire",
            "We require a trial task first",
            "Complete a test project to prove skills",
            "Free sample of your work needed",
            "Work for free initially",
        ],
    )
    def test_free_work_keywords_fail(self, text: str) -> None:
        listing = _make_listing(description=text)
        results = check_gates(listing, _ALL_PASS_SCORES)
        gate = _get_gate(results, "free_work_rejection")
        assert gate.verdict == GateVerdict.FAIL  # type: ignore[union-attr]

    def test_clean_description_passes(self) -> None:
        listing = _make_listing(description="Paid project, escrow funded")
        results = check_gates(listing, _ALL_PASS_SCORES)
        gate = _get_gate(results, "free_work_rejection")
        assert gate.verdict == GateVerdict.PASS  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Composite scenarios
# ---------------------------------------------------------------------------


class TestCompositeGates:
    def test_all_pass(self) -> None:
        listing = _make_listing()
        # Use effort=2 so effort gate is PASS (not MAYBE at 3)
        scores = {**_ALL_PASS_SCORES, "effort": 2}
        results = check_gates(listing, scores)
        assert all(r.verdict == GateVerdict.PASS for r in results)
        assert len(results) == 8

    def test_multiple_failures(self) -> None:
        """Budget below floor + equity + low effort scores."""
        listing = _make_listing(
            budget=50.0,
            description="Offering equity to build my app from scratch",
            client_spend_history=None,
            client_hire_rate=None,
        )
        scores = {**_ALL_PASS_SCORES, "clarity": 1, "effort": 5}
        results = check_gates(listing, scores)
        failed = [r for r in results if r.verdict == GateVerdict.FAIL]
        # Should fail: budget, effort, clarity, payment, mvp, equity
        assert len(failed) >= 5
        failed_names = {r.gate for r in failed}
        assert "budget_floor" in failed_names
        assert "effort_ceiling" in failed_names
        assert "clarity_floor" in failed_names
        assert "payment_verified" in failed_names
        assert "mvp_rejection" in failed_names

    def test_always_returns_8_results(self) -> None:
        """Even with all failures, all 8 gates run."""
        listing = _make_listing(budget=10.0)
        results = check_gates(listing, _ALL_PASS_SCORES)
        assert len(results) == 8

    def test_maybe_with_no_fail(self) -> None:
        """Borderline budget + effort=3 + partial payment -> all MAYBE, no FAIL."""
        listing = _make_listing(
            budget=120.0,
            client_spend_history=2000.0,
            client_hire_rate=None,
        )
        scores = {**_ALL_PASS_SCORES, "effort": 3}
        results = check_gates(listing, scores)
        fails = [r for r in results if r.verdict == GateVerdict.FAIL]
        maybes = [r for r in results if r.verdict == GateVerdict.MAYBE]
        assert len(fails) == 0
        assert len(maybes) == 3  # budget, effort, payment
        maybe_names = {r.gate for r in maybes}
        assert maybe_names == {"budget_floor", "effort_ceiling", "payment_verified"}

    def test_maybe_and_fail_together(self) -> None:
        """MAYBE on budget but FAIL on effort -> FAIL takes precedence in scoring."""
        listing = _make_listing(budget=120.0)
        scores = {**_ALL_PASS_SCORES, "effort": 5}
        results = check_gates(listing, scores)
        budget = _get_gate(results, "budget_floor")
        effort = _get_gate(results, "effort_ceiling")
        assert budget.verdict == GateVerdict.MAYBE  # type: ignore[union-attr]
        assert effort.verdict == GateVerdict.FAIL  # type: ignore[union-attr]
