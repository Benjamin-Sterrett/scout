"""CLI for Scout v1 manual flow.

Entry point: ``python -m scout`` (via __main__.py).

Subcommands:
  score     — parse, gate, score, and rank listings from file or stdin
  normalize — placeholder for Wave 4 ticket normalization
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any

from scout.models import (
    ParseConfidence,
    Platform,
    RawListing,
    ResponseSLA,
    ScoredListing,
)
from scout.pipeline import PipelineResult, run_pipeline


def _split_listings(text: str) -> list[str]:
    """Split text into listing blocks separated by two or more blank lines.

    Single blank lines are preserved within a listing (e.g., between
    title and description).  Listings are separated by double-blank-lines
    or a line containing only ``---``.
    """
    # Normalize: split on 2+ consecutive blank lines OR a --- separator line
    blocks = re.split(r"\n\s*\n\s*\n|\n---\n", text)
    return [b.strip() for b in blocks if b.strip()]


def _read_listings(args: argparse.Namespace) -> list[RawListing]:
    """Build RawListing objects from --file or stdin."""
    if args.file:
        with open(args.file) as f:
            text = f.read()
    else:
        text = sys.stdin.read()

    platform: Platform | None = None
    if args.platform:
        platform = Platform(args.platform)

    listings = _split_listings(text)
    return [RawListing(platform=platform, raw_text=p) for p in listings if p.strip()]


def _sla_label(sla: ResponseSLA) -> str:
    """Short label for SLA tier."""
    mapping: dict[ResponseSLA, str] = {
        ResponseSLA.IMMEDIATE_30MIN: "30min",
        ResponseSLA.PRIORITY_60MIN: "60min",
        ResponseSLA.STANDARD_4HR: "4hr",
        ResponseSLA.BATCH_NEXT_DAY: "next day",
        ResponseSLA.SKIP: "skip",
    }
    return mapping.get(sla, sla.value)


def _sla_action(sla: ResponseSLA) -> str:
    """Action prompt based on SLA tier."""
    if sla == ResponseSLA.IMMEDIATE_30MIN:
        return "-> RESPOND NOW"
    if sla == ResponseSLA.PRIORITY_60MIN:
        return "-> Priority response"
    return ""


def _format_ranked(idx: int, s: ScoredListing, has_pre_scores: bool) -> str:
    """Format a single ranked listing for human-readable output."""
    p = s.parsed_listing
    confidence = p.parse_confidence.value.upper()
    sla = _sla_label(s.response_sla)
    action = _sla_action(s.response_sla)

    lines: list[str] = []
    header = f"#{idx} [SCORE: {s.total_score:.1f}] [SLA: {sla}] [CONFIDENCE: {confidence}] {p.title}"
    lines.append(header)

    # Platform + budget + category
    budget_str = f"${p.budget:.0f}" if p.budget is not None else "N/A"
    category_str = p.category.value.upper() if p.category else "OTHER"
    lines.append(
        f"   Platform: {p.platform.value.title()} | Budget: {budget_str} | Category: {category_str}"
    )

    # Dimension breakdown (only if pre_scores were provided)
    if has_pre_scores and s.dimension_scores:
        dims = " | ".join(
            f"{d.dimension.title()}: {d.score}" for d in s.dimension_scores
        )
        lines.append(f"   {dims}")

    # Bonuses
    if s.bonuses:
        bonus_parts = [f"+{b.points} {b.name.replace('_', ' ')}" for b in s.bonuses]
        lines.append(f"   Bonuses: {', '.join(bonus_parts)}")

    if not has_pre_scores:
        lines.append("   [no LLM scores -- gate filtering only]")

    if action:
        lines.append(f"   {action}")

    return "\n".join(lines)


def _format_rejected(s: ScoredListing) -> str:
    """Format a rejected listing."""
    title = s.parsed_listing.title
    reason = s.rejection_reason or "unknown"
    budget_str = ""
    if s.parsed_listing.budget is not None:
        budget_str = f" (${s.parsed_listing.budget:.0f})"
    return f'"{title}" -> GATE FAIL: {reason}{budget_str}'


def _format_review(s: ScoredListing) -> str:
    """Format a needs-review listing."""
    p = s.parsed_listing
    title = p.title
    if p.parse_confidence == ParseConfidence.LOW:
        return f'"{title}" -> LOW confidence, couldn\'t extract fields'

    # MAYBE gate -- show which gate was borderline
    maybe_gates = [g for g in s.gate_results if g.verdict.value == "maybe"]
    if maybe_gates:
        reasons = ", ".join(f"{g.gate} ({g.reason})" for g in maybe_gates)
        score_str = f" [SCORE: {s.total_score:.1f}]" if s.total_score > 0 else ""
        return f'"{title}"{score_str} -> MAYBE: {reasons}'

    return f'"{title}" -> needs manual review'


def _print_human(result: PipelineResult, *, top_n: int) -> None:
    """Print human-readable output to stdout."""
    stats = result.stats
    print(
        f"\n=== SCOUT RESULTS ({stats.passed_gates} scored, "
        f"{stats.rejected} rejected, {stats.needs_review} need review) ==="
    )

    if not result.ranked and not result.rejected and not result.needs_review:
        print("\nNo listings processed.")
        print()
        return

    # Ranked listings
    if result.ranked:
        print()
    for i, s in enumerate(result.ranked[:top_n], 1):
        print(_format_ranked(i, s, result.has_pre_scores))
        print()

    # Rejected
    if result.rejected:
        print(f"--- REJECTED ({len(result.rejected)}) ---")
        for s in result.rejected:
            print(_format_rejected(s))
        print()

    # Needs review
    if result.needs_review:
        print(f"--- NEEDS REVIEW ({len(result.needs_review)}) ---")
        for s in result.needs_review:
            print(_format_review(s))
        print()

    # Footer
    print(
        f"Pipeline: {stats.total_parsed} listings processed "
        f"in {stats.duration_ms:.0f}ms"
    )
    print()


def _scored_to_dict(s: ScoredListing) -> dict[str, Any]:
    """Convert ScoredListing to JSON-serializable dict."""
    p = s.parsed_listing
    return {
        "title": p.title,
        "platform": p.platform.value,
        "budget": p.budget,
        "category": p.category.value if p.category else None,
        "parse_confidence": p.parse_confidence.value,
        "total_score": s.total_score,
        "response_sla": s.response_sla.value,
        "rejected": s.rejected,
        "rejection_reason": s.rejection_reason,
        "needs_review": s.needs_review,
        "gate_results": [
            {"gate": g.gate, "verdict": g.verdict.value, "reason": g.reason}
            for g in s.gate_results
        ],
        "dimension_scores": [
            {"dimension": d.dimension, "score": d.score, "weight": d.weight}
            for d in s.dimension_scores
        ],
        "bonuses": [
            {"name": b.name, "points": b.points, "reason": b.reason} for b in s.bonuses
        ],
    }


def _print_json(result: PipelineResult) -> None:
    """Print JSON output to stdout."""
    output: dict[str, Any] = {
        "ranked": [_scored_to_dict(s) for s in result.ranked],
        "rejected": [_scored_to_dict(s) for s in result.rejected],
        "needs_review": [_scored_to_dict(s) for s in result.needs_review],
        "has_pre_scores": result.has_pre_scores,
        "stats": {
            "total_parsed": result.stats.total_parsed,
            "passed_gates": result.stats.passed_gates,
            "rejected": result.stats.rejected,
            "needs_review": result.stats.needs_review,
            "avg_score": result.stats.avg_score,
            "duration_ms": result.stats.duration_ms,
            "confidence_distribution": result.stats.confidence_distribution,
        },
    }
    print(json.dumps(output, indent=2))


def _cmd_score(args: argparse.Namespace) -> None:
    """Execute the 'score' subcommand."""
    if args.top < 1:
        print("Error: --top must be a positive integer.", file=sys.stderr)
        sys.exit(1)

    raws = _read_listings(args)
    if not raws:
        print("No listings found in input.", file=sys.stderr)
        sys.exit(1)

    result = run_pipeline(raws, pre_scores_map=None, top_n=args.top)

    if args.json:
        _print_json(result)
    else:
        _print_human(result, top_n=args.top)


def _cmd_normalize(args: argparse.Namespace) -> None:
    """Execute the 'normalize' subcommand (placeholder for Wave 4)."""
    _ = args  # index argument parsed but unused
    print("Normalization requires PRJ-371 (Wave 4). Not yet implemented.")
    sys.exit(0)


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="scout",
        description="Scout — Freelance job arbitrage engine",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # --- score ---
    score_parser = subparsers.add_parser(
        "score",
        help="Parse, gate, score, and rank job listings",
    )
    score_parser.add_argument(
        "--file",
        type=str,
        default=None,
        help="Read listings from file (paragraphs separated by blank lines)",
    )
    score_parser.add_argument(
        "--platform",
        type=str,
        choices=[p.value for p in Platform],
        default=None,
        help="Hint platform for all listings",
    )
    score_parser.add_argument(
        "--top",
        type=int,
        default=5,
        help="Return top N ranked listings (default: 5)",
    )
    score_parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Output results as JSON",
    )
    score_parser.set_defaults(func=_cmd_score)

    # --- normalize ---
    normalize_parser = subparsers.add_parser(
        "normalize",
        help="Convert Nth result from last run to Linear ticket (Wave 4)",
    )
    normalize_parser.add_argument(
        "index",
        type=int,
        help="Index of the result to normalize (1-based)",
    )
    normalize_parser.set_defaults(func=_cmd_normalize)

    return parser


def main(argv: list[str] | None = None) -> None:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)
