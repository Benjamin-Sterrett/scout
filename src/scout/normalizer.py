"""Linear ticket normalizer for Scout.

Converts a scored+approved listing into a Linear ticket with structured
sections covering problem, scope, assumptions, deliverables, acceptance
criteria, constraints, risks, and SOW clause.

All template sections sourced from:
- research/synthesis.md SS7 (scope creep prevention, 28% more with contracts)
- research/synthesis.md SS8 (delivery package: Loom + preview buffer)
- .implementation-plan.md Wave 4 citations
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from scout.models import (
    ApprovedListing,
    NormalizedTicket,
    ResponseSLA,
    ScoredListing,
)

if TYPE_CHECKING:
    from scout.models import DimensionScore, ParsedListing

# Linear team ID for PRJ (Projects)
_PRJ_TEAM_ID: str = "db03ce09-7800-4b9e-941b-4820d141591d"

# Priority mapping: score -> Linear priority (1=Urgent, 4=Low)
_PRIORITY_THRESHOLDS: list[tuple[float, int]] = [
    (12.0, 1),  # Urgent
    (8.0, 2),  # High
    (5.0, 3),  # Normal
]
# Below 5.0 -> priority 4 (Low)


def _map_priority(total_score: float) -> int:
    """Map a Scout total score to Linear priority (1-4)."""
    for threshold, priority in _PRIORITY_THRESHOLDS:
        if total_score >= threshold:
            return priority
    return 4


def _sla_label(sla: ResponseSLA) -> str:
    """Human-readable SLA label."""
    labels: dict[ResponseSLA, str] = {
        ResponseSLA.IMMEDIATE_30MIN: "30 min (drop everything)",
        ResponseSLA.PRIORITY_60MIN: "60 min (prioritize)",
        ResponseSLA.STANDARD_4HR: "4 hr (batch with daily review)",
        ResponseSLA.BATCH_NEXT_DAY: "Next day",
        ResponseSLA.SKIP: "Skip",
    }
    return labels.get(sla, sla.value)


def _get_dimension(scores: list[DimensionScore], name: str) -> DimensionScore | None:
    """Find a dimension score by name."""
    for ds in scores:
        if ds.dimension == name:
            return ds
    return None


def _infer_scope(listing: ParsedListing) -> str:
    """Infer scope description from tech keywords and category."""
    parts: list[str] = []
    if listing.tech_keywords:
        parts.append(", ".join(listing.tech_keywords[:5]))
    if listing.category:
        cat_labels: dict[str, str] = {
            "bug_fix": "bug fix",
            "web_scraping": "web scraping / data extraction",
            "api_integration": "API integration",
            "automation_script": "automation script",
            "landing_page": "landing page build",
            "wordpress_shopify": "WordPress/Shopify work",
            "migration": "migration / upgrade",
            "other": "general development",
        }
        label = cat_labels.get(listing.category.value, listing.category.value)
        parts.append(label)
    if not parts:
        return "Scope to be determined after repo access."
    return f"Likely involves: {'; '.join(parts)}."


def _platform_assumptions(listing: ParsedListing) -> list[str]:
    """Platform-specific assumptions."""
    assumptions: list[str] = []
    plat = listing.platform.value
    if plat == "upwork":
        assumptions.append("Upwork escrow funded before work begins")
    elif plat == "freelancer":
        assumptions.append("Freelancer.com milestone escrow funded before work begins")
    elif plat == "fiverr":
        assumptions.append("Fiverr order placed and active")
    elif plat in ("reddit", "discord"):
        assumptions.append(
            "Payment terms agreed in writing before work begins (no platform escrow)"
        )
    return assumptions


def _build_risks(scores: list[DimensionScore]) -> list[str]:
    """Build risk/mitigation lines from scored dimensions."""
    risk_dims = ["risk", "technical_risk", "effort"]
    lines: list[str] = []
    for name in risk_dims:
        ds = _get_dimension(scores, name)
        if ds is None:
            continue
        if ds.score >= 3:
            mitigation = _risk_mitigation(name, ds.score)
            lines.append(
                f"{name.replace('_', ' ').title()} ({ds.score}/5): "
                f"{ds.anchor_matched}. Mitigation: {mitigation}"
            )
    if not lines:
        lines.append("No elevated risks identified.")
    return lines


def _risk_mitigation(dimension: str, score: int) -> str:
    """Suggest a mitigation based on dimension and severity."""
    mitigations: dict[str, dict[int, str]] = {
        "risk": {
            3: "Request clear SOW before starting",
            4: "Require milestone escrow + written acceptance criteria",
            5: "Decline or require full prepayment",
        },
        "technical_risk": {
            3: "Work in staging/sandbox environment only",
            4: "Require staging environment; no direct production access",
            5: "Decline unless isolated sandbox provided",
        },
        "effort": {
            3: "Break into 2+ milestones to contain scope",
            4: "Consider declining; above 6hr threshold",
            5: "Decline; multi-day scope unsuitable for arbitrage",
        },
    }
    dim_map = mitigations.get(dimension, {})
    return dim_map.get(score, "Monitor closely")


def _build_acceptance_criteria(listing: ParsedListing) -> list[str]:
    """Derive acceptance criteria from listing data."""
    criteria: list[str] = []
    cat = listing.category.value if listing.category else "other"

    category_criteria: dict[str, list[str]] = {
        "bug_fix": [
            "Bug no longer reproducible under stated conditions",
            "No regressions introduced",
        ],
        "web_scraping": [
            "Scraper returns structured data matching spec",
            "Handles pagination and rate limiting",
        ],
        "api_integration": [
            "API endpoints respond with correct data",
            "Error handling covers common failure modes",
        ],
        "automation_script": [
            "Script runs end-to-end without manual intervention",
            "Output matches expected format",
        ],
        "landing_page": [
            "Page matches provided design/wireframe",
            "Responsive on mobile and desktop",
        ],
        "wordpress_shopify": [
            "Changes render correctly on the live theme",
            "No conflicts with existing plugins/apps",
        ],
        "migration": [
            "All data migrated with zero loss",
            "New system passes smoke tests",
        ],
    }
    criteria.extend(
        category_criteria.get(cat, ["Deliverable matches stated requirements"])
    )
    criteria.append("All tests pass")
    criteria.append("Client confirms fix resolves the stated issue")
    return criteria


def _format_date(dt: datetime | None) -> str:
    """Format a datetime for display, or 'Unknown'."""
    if dt is None:
        return "Unknown"
    return dt.strftime("%Y-%m-%d")


def _build_description(approved: ApprovedListing) -> str:
    """Build the full Markdown ticket description."""
    scored = approved.scored_listing
    listing = scored.parsed_listing

    budget_str = f"${listing.budget:.0f}" if listing.budget is not None else "N/A"
    effort_ds = _get_dimension(scored.dimension_scores, "effort")
    effort_str = f"{effort_ds.anchor_matched}" if effort_ds else "Not scored"

    sections: list[str] = []

    # Problem
    sections.append("## Problem")
    sections.append(listing.description)

    # Scope
    sections.append("\n## Scope")
    sections.append(_infer_scope(listing))

    # Assumptions
    sections.append("\n## Assumptions")
    assumptions = [
        "Client will provide repo access",
        f"Budget is fixed-price at {budget_str}",
    ]
    assumptions.extend(_platform_assumptions(listing))
    for a in assumptions:
        sections.append(f"- {a}")

    # Deliverables (synthesis SS8 — Loom + preview buffer)
    sections.append("\n## Deliverables")
    deliverables = [
        "Working fix/feature with tests",
        "PR with clear description",
        "Loom walkthrough (2-5 min)",
        "Screenshot/preview before final delivery (preview buffer tactic)",
    ]
    for d in deliverables:
        sections.append(f"- {d}")

    # Acceptance Criteria
    sections.append("\n## Acceptance Criteria")
    for ac in _build_acceptance_criteria(listing):
        sections.append(f"- {ac}")

    # Constraints
    sections.append("\n## Constraints")
    constraints = [
        f"Time: {effort_str}",
        "Max 500 LOC per PR",
        "2 revision rounds included",
        "Additional work requires separate estimate",
    ]
    for c in constraints:
        sections.append(f"- {c}")

    # Risks & Mitigations
    sections.append("\n## Risks & Mitigations")
    for r in _build_risks(scored.dimension_scores):
        sections.append(f"- {r}")

    # Client SOW Clause (synthesis SS7 — 28% more with contracts)
    sections.append("\n## Client SOW Clause")
    sections.append(
        '"Additional work outside the scope defined above '
        'requires a separate estimate and agreement."'
    )

    # Source
    sections.append("\n## Source")
    sections.append(f"- Platform: {listing.platform.value}")
    sections.append(f"- URL: {listing.url or 'N/A'}")
    sections.append(f"- Budget: {budget_str}")
    sections.append(f"- Posted: {_format_date(listing.posted_at)}")
    sections.append(
        f"- Scout Score: {scored.total_score:.1f} / "
        f"SLA: {_sla_label(scored.response_sla)}"
    )

    return "\n".join(sections)


def normalize_to_ticket(
    scored: ScoredListing,
    approved_by: str = "benjamin",
) -> NormalizedTicket:
    """Convert a ScoredListing into a NormalizedTicket ready for Linear.

    Wraps the scored listing in an ApprovedListing, builds the Markdown
    description with all 8 required sections, and maps priority from score.
    """
    approved = ApprovedListing(
        scored_listing=scored,
        approved_by=approved_by,
        approved_at=datetime.now(tz=timezone.utc),
    )

    title_prefix = (
        "Scout: " if not scored.parsed_listing.title.startswith("Scout:") else ""
    )
    title = f"{title_prefix}{scored.parsed_listing.title}"

    labels: list[str] = ["scout"]
    if scored.parsed_listing.category:
        labels.append(scored.parsed_listing.category.value)

    return NormalizedTicket(
        title=title,
        description=_build_description(approved),
        priority=_map_priority(scored.total_score),
        team_id=_PRJ_TEAM_ID,
        labels=labels,
        source_listing=approved,
    )


def create_ticket_cli(ticket: NormalizedTicket) -> str:
    """Create a Linear issue via the ``linear`` CLI and return the issue URL.

    Shells out to ``linear issue create`` with the ticket's title,
    description, team, and priority.  Returns the URL from CLI output.

    Raises:
        RuntimeError: If the CLI command fails or returns no URL.
    """
    cmd = [
        "linear",
        "issue",
        "create",
        "--title",
        ticket.title,
        "--description",
        ticket.description,
        "--team",
        "PRJ",
        "--priority",
        str(ticket.priority),
    ]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        msg = f"linear issue create failed: {result.stderr.strip()}"
        raise RuntimeError(msg)

    # Extract URL from output (Linear CLI prints the issue URL)
    output = result.stdout.strip()
    for line in output.splitlines():
        stripped = line.strip()
        if "linear.app" in stripped or stripped.startswith("http"):
            return stripped
    # If no URL found, return the full output as fallback
    if output:
        return output
    msg = "linear issue create produced no output"
    raise RuntimeError(msg)
