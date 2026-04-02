"""Data models for the Scout pipeline.

Defines the 5 stage contracts (RawListing -> ParsedListing -> ScoredListing ->
ApprovedListing -> NormalizedTicket) plus scoring types and reference enums.

All dimension anchors and gate thresholds sourced from research/synthesis.md
section "Scout Scoring Model v2".
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ---------------------------------------------------------------------------
# Reference enums
# ---------------------------------------------------------------------------


class Platform(StrEnum):
    """Freelance platforms tracked by Scout (synthesis SS1)."""

    UPWORK = "upwork"
    FIVERR = "fiverr"
    FREELANCER = "freelancer"
    REDDIT = "reddit"
    WWR = "wwr"
    DISCORD = "discord"
    GUN_IO = "gun_io"
    ARC_DEV = "arc_dev"


class Category(StrEnum):
    """Job categories ranked by arbitrage potential (synthesis SS2)."""

    BUG_FIX = "bug_fix"
    WEB_SCRAPING = "web_scraping"
    API_INTEGRATION = "api_integration"
    AUTOMATION_SCRIPT = "automation_script"
    LANDING_PAGE = "landing_page"
    WORDPRESS_SHOPIFY = "wordpress_shopify"
    MIGRATION = "migration"
    OTHER = "other"


class ParseConfidence(StrEnum):
    """Parser extraction confidence level.

    HIGH  - all key fields extracted cleanly.
    MEDIUM - some fields inferred or missing.
    LOW   - minimal extraction; needs manual review.
    """

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ResponseSLA(StrEnum):
    """Score-driven response urgency tiers (synthesis SS"Response SLA")."""

    IMMEDIATE_30MIN = "immediate_30min"
    PRIORITY_60MIN = "priority_60min"
    STANDARD_4HR = "standard_4hr"
    BATCH_NEXT_DAY = "batch_next_day"
    SKIP = "skip"


class GateVerdict(StrEnum):
    """Tri-state gate outcome.

    PASS  - clearly meets threshold.
    FAIL  - clearly below threshold.
    MAYBE - borderline; surface to human review (Wave 3 pipeline behavior:
            any FAIL -> rejected, all PASS -> score normally, any MAYBE
            with no FAIL -> score but flag for manual review).
    """

    PASS = "pass"
    FAIL = "fail"
    MAYBE = "maybe"


# ---------------------------------------------------------------------------
# Strict base (shared by all pipeline models)
# ---------------------------------------------------------------------------


class _StrictModel(BaseModel):
    """Shared base for all Scout pipeline models.

    ``extra="forbid"`` rejects unexpected fields, preventing silent schema
    drift between pipeline stages and within nested scoring types.
    """

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# Scoring types
# ---------------------------------------------------------------------------


class DimensionScore(_StrictModel):
    """A single scored dimension with its anchor and reasoning."""

    dimension: str
    score: int = Field(ge=1, le=5)
    weight: float
    anchor_matched: str
    reasoning: str


class GateResult(_StrictModel):
    """Result of a single hard gate evaluation."""

    gate: str
    verdict: GateVerdict
    reason: str


class Bonus(_StrictModel):
    """An additive bonus applied to the total score."""

    name: str
    points: int
    reason: str


# ---------------------------------------------------------------------------
# Stage contracts (pipeline spine)
# ---------------------------------------------------------------------------


class RawListing(_StrictModel):
    """Stage 1: Unprocessed input from any platform."""

    platform: Platform | None = None
    raw_text: str
    source_url: str | None = None


class ParsedListing(_StrictModel):
    """Stage 2: Structured fields extracted from raw text.

    ``parse_confidence`` indicates extraction quality.
    ``inferred_fields`` lists field names that were guessed rather than
    directly extracted, so the scoring engine can down-weight them.
    """

    title: str
    description: str
    budget: float | None = Field(default=None, ge=0)
    platform: Platform
    url: str | None = None
    client_spend_history: float | None = Field(default=None, ge=0)
    client_hire_rate: float | None = Field(default=None, ge=0, le=100)
    posted_at: datetime | None = None
    tech_keywords: list[str] = Field(default_factory=list)
    urgency_signals: list[str] = Field(default_factory=list)
    red_flags: list[str] = Field(default_factory=list)
    parse_confidence: ParseConfidence
    inferred_fields: list[str] = Field(default_factory=list)
    category: Category | None = None


class ScoredListing(_StrictModel):
    """Stage 3: ParsedListing + scoring results.

    Enforces consistency: if any gate has verdict FAIL, ``rejected`` must
    be True and ``rejection_reason`` must be provided.  ``needs_review``
    is set when any gate returned MAYBE (but none FAIL).
    """

    parsed_listing: ParsedListing
    gate_results: list[GateResult]
    dimension_scores: list[DimensionScore]
    bonuses: list[Bonus]
    total_score: float
    response_sla: ResponseSLA
    rejected: bool = False
    rejection_reason: str | None = None
    needs_review: bool = False

    @model_validator(mode="after")
    def _check_gate_consistency(self) -> ScoredListing:
        has_failed_gate = any(
            gr.verdict == GateVerdict.FAIL for gr in self.gate_results
        )
        if has_failed_gate and not self.rejected:
            failed = [
                gr.gate for gr in self.gate_results if gr.verdict == GateVerdict.FAIL
            ]
            msg = (
                f"Gate(s) {failed} failed but rejected=False. "
                "Set rejected=True with a rejection_reason."
            )
            raise ValueError(msg)
        if self.rejected and not self.rejection_reason:
            msg = "rejected=True requires a non-empty rejection_reason."
            raise ValueError(msg)
        return self


class ApprovedListing(_StrictModel):
    """Stage 4: Human-approved listing (v1 gate).

    Validates that the underlying scored listing was not rejected by hard
    gates. If a human override is needed, set ``override=True`` with a
    reason in ``notes``.
    """

    scored_listing: ScoredListing
    approved_by: str
    approved_at: datetime
    notes: str | None = None
    override: bool = False

    @model_validator(mode="after")
    def _check_not_rejected(self) -> ApprovedListing:
        if self.scored_listing.rejected and not self.override:
            msg = (
                "Cannot approve a rejected listing without override=True. "
                f"Rejection reason: {self.scored_listing.rejection_reason}"
            )
            raise ValueError(msg)
        return self


class NormalizedTicket(_StrictModel):
    """Stage 5: Linear ticket payload ready for creation."""

    title: str
    description: str
    priority: int = Field(ge=1, le=4)
    team_id: str
    labels: list[str] = Field(default_factory=list)
    source_listing: ApprovedListing
