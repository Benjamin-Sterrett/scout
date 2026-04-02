"""Multi-format intake parser for Scout.

Takes list[RawListing], returns list[ParsedListing] with parse_confidence.
Keyword patterns from gates.py are imported directly -- not duplicated.
Does NOT score or gate. Citations: synthesis.md §1, §2, §7.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from scout.gates import _EQUITY_PATTERNS, _FREE_WORK_PATTERNS, _MVP_PATTERNS
from scout.models import Category, ParseConfidence, ParsedListing, Platform

if TYPE_CHECKING:
    from scout.models import RawListing

# Top 18 tech keywords. scoring.py covers the broader set; intake only needs
# enough for category detection and confidence assignment.
_TECH_KEYWORDS: list[str] = [
    "react",
    "next.js",
    "nextjs",
    "python",
    "node",
    "node.js",
    "typescript",
    "javascript",
    "api",
    "webhook",
    "scraping",
    "automation",
    "automate",
    "wordpress",
    "shopify",
    "stripe",
    "django",
    "airtable",
]

# Strongest urgency signals only (synthesis §2 Tier 1).
_URGENCY_EXACT: list[str] = [
    "today",
    "asap",
    "urgent",
    "immediately",
    "right now",
    "emergency",
]

_DEADLINE_PATTERN: re.Pattern[str] = re.compile(
    r"\b(?:by|due|before|deadline)\s+"
    r"(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|"
    r"july?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?|"
    r"\d{1,2}[\/\-]\d{1,2}(?:[\/\-]\d{2,4})?)",
    re.IGNORECASE,
)

_QUICK_EASY_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\bquick and easy\b",
        r"\bshould be (?:simple|easy|quick|straightforward)\b",
        r"\bsimple (?:task|job|project)\b",
        r"\beasy (?:task|job|project|money)\b",
    ]
]

_RED_FLAG_LABELS: list[tuple[list[re.Pattern[str]], str]] = [
    (_MVP_PATTERNS, "mvp/build-from-scratch"),
    (_EQUITY_PATTERNS, "equity/revenue-share"),
    (_FREE_WORK_PATTERNS, "free-test-work"),
    (_QUICK_EASY_PATTERNS, "quick-and-easy"),
]

# Ordered by specificity: more-specific categories first, BUG_FIX last (broadest).
_CATEGORY_PATTERNS: list[tuple[Category, list[str]]] = [
    (
        Category.WEB_SCRAPING,
        ["scrape", "scraping", "data extraction", "crawl", "collect data"],
    ),
    (
        Category.MIGRATION,
        ["migrate", "migration", "convert from", "port to", "rewrite"],
    ),
    (
        Category.WORDPRESS_SHOPIFY,
        ["wordpress", "shopify", "woocommerce", "wp-", "wp plugin"],
    ),
    (
        Category.API_INTEGRATION,
        ["api integration", "webhook", "endpoint", "integrate", "rest api"],
    ),
    (
        Category.AUTOMATION_SCRIPT,
        ["automate", "automation", "script", "cron", "scheduled"],
    ),
    (Category.LANDING_PAGE, ["landing page", "one page", "sales page"]),
    (
        Category.BUG_FIX,
        ["fix", "bug", "error", "broken", "not working", "issue", "crash", "exception"],
    ),
]

# Budget regex patterns
_BUDGET_LABELED: re.Pattern[str] = re.compile(
    r"[Bb]udget\s*:?\s*\$?([\d,]+(?:\.\d+)?(?:k)?)"
    r"(?:\s*[-–]\s*\$?([\d,]+(?:\.\d+)?(?:k)?))?",
    re.IGNORECASE,
)
_HOURLY_RANGE: re.Pattern[str] = re.compile(
    r"\$\s*([\d,]+(?:\.\d+)?)\s*[-–]\s*\$?\s*([\d,]+(?:\.\d+)?)\s*/\s*hr",
    re.IGNORECASE,
)
_DOLLAR_AMOUNT: re.Pattern[str] = re.compile(
    r"\$\s*([\d,]+(?:\.\d+)?(?:k)?)\b",
    re.IGNORECASE,
)
_NO_BUDGET_SIGNALS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\bmake me an offer\b",
        r"\bopen to offers\b",
        r"\bno budget\b",
        r"\bnegotiable\b",
        r"\bto be discussed\b",
    ]
]

# Platform auto-detection signal lists
_UPWORK_SIGNALS: list[str] = [
    "budget:",
    "client:",
    "skills:",
    "hourly range:",
    "fixed price",
    "client spent",
    "hire rate:",
    "payment verified",
]
_REDDIT_SIGNALS: list[str] = [
    "[hiring]",
    "[for hire]",
    "r/forhire",
    "r/freelance",
    "dm me",
    "send me a message",
]


def _parse_dollar_str(s: str) -> float:
    """Convert '$1,000' or '1.5k' to float."""
    s = s.replace(",", "").strip()
    if s.lower().endswith("k"):
        return float(s[:-1]) * 1000
    return float(s)


_METADATA_LINE: re.Pattern[str] = re.compile(
    r"^(?:client\s+spent\s*:?\s*\$|hire\s+rate|skills|payment\s+verified|posted|proposals?)\s*:?",
    re.IGNORECASE,
)


def _extract_budget(text: str) -> tuple[float | None, bool]:
    """Return (amount, was_inferred). None when no budget found."""
    # Labeled budget first — "Budget: $500 negotiable" is still $500.
    m = _BUDGET_LABELED.search(text)
    if m:
        lo = _parse_dollar_str(m.group(1))
        if m.group(2):
            return (lo + _parse_dollar_str(m.group(2))) / 2, True
        return lo, False

    # No-budget signals only matter when no explicit labeled budget found.
    for pat in _NO_BUDGET_SIGNALS:
        if pat.search(text):
            return None, False

    m_hr = _HOURLY_RANGE.search(text)
    if m_hr:
        lo = _parse_dollar_str(m_hr.group(1))
        hi = _parse_dollar_str(m_hr.group(2))
        return (lo + hi) / 2, True

    # Bare-dollar fallback: strip metadata lines (Client spent $X, etc.)
    # to avoid treating client history as the job budget.
    body_lines = [
        ln for ln in text.splitlines() if not _METADATA_LINE.match(ln.strip())
    ]
    body = "\n".join(body_lines)
    amounts = [_parse_dollar_str(m2.group(1)) for m2 in _DOLLAR_AMOUNT.finditer(body)]
    candidates = [a for a in amounts if a >= 50]
    if candidates:
        return max(candidates), True

    return None, False


def _extract_urgency_signals(text: str) -> list[str]:
    """Match urgency keywords and deadline patterns. Deduped."""
    text_lower = text.lower()
    found: list[str] = [s for s in _URGENCY_EXACT if s in text_lower]
    found.extend(m.group(0).strip() for m in _DEADLINE_PATTERN.finditer(text))
    return list(dict.fromkeys(found))


def _extract_tech_keywords(text: str) -> list[str]:
    """Case-insensitive word-boundary match against known stack list."""
    text_lower = text.lower()
    return [
        kw
        for kw in _TECH_KEYWORDS
        if re.search(r"\b" + re.escape(kw) + r"\b", text_lower)
    ]


def _extract_red_flags(text: str) -> list[str]:
    """Match red flag pattern groups (one label per group)."""
    found: list[str] = []
    for patterns, label in _RED_FLAG_LABELS:
        if any(pat.search(text) for pat in patterns):
            found.append(label)
    return found


def _extract_category(description: str, tech_keywords: list[str]) -> Category | None:
    """First-match category from description and keywords. None if no match."""
    text_lower = description.lower()
    kw_lower = {k.lower() for k in tech_keywords}
    for category, signals in _CATEGORY_PATTERNS:
        for signal in signals:
            if signal in text_lower or signal in kw_lower:
                return category
    return None


def _detect_platform(text: str) -> Platform:
    """Infer platform from text signals. Falls back to FREELANCER."""
    text_lower = text.lower()
    upwork_hits = sum(1 for sig in _UPWORK_SIGNALS if sig in text_lower)
    reddit_hits = sum(1 for sig in _REDDIT_SIGNALS if sig in text_lower)
    if upwork_hits >= 2:
        return Platform.UPWORK
    if reddit_hits >= 1:
        return Platform.REDDIT
    if upwork_hits == 1 and "budget:" in text_lower:
        return Platform.UPWORK
    return Platform.FREELANCER


def _assign_confidence(
    budget: float | None,
    budget_inferred: bool,
    description: str,
    tech_keywords: list[str],
    category: Category | None,
    inferred_fields: list[str],
) -> ParseConfidence:
    """HIGH if budget+long desc+tech, MEDIUM if partial, LOW otherwise."""
    has_clean_budget = budget is not None and not budget_inferred
    long_description = len(description) > 100
    has_tech = bool(tech_keywords) or category is not None

    if has_clean_budget and long_description and has_tech:
        return ParseConfidence.HIGH

    has_some_extraction = (budget is not None) or long_description or has_tech
    if has_some_extraction and len(inferred_fields) <= 2:
        return ParseConfidence.MEDIUM

    return ParseConfidence.LOW


def _split_lines(text: str) -> list[str]:
    """Split text into non-empty stripped lines."""
    return [ln.strip() for ln in text.strip().splitlines() if ln.strip()]


def _build_parsed(
    title: str,
    description: str,
    raw: "RawListing",
    *,
    client_spend: float | None = None,
    client_hire_rate: float | None = None,
    extra_inferred: list[str] | None = None,
) -> ParsedListing:
    """Shared builder: run signal extraction, assign confidence, construct model."""
    text = raw.raw_text
    inferred = list(extra_inferred) if extra_inferred else []

    budget, budget_inferred = _extract_budget(text)
    if budget_inferred:
        inferred.append("budget")
    elif budget is None and client_spend is None:
        inferred.append("budget")

    if raw.platform is None:
        inferred.append("platform")

    urgency = _extract_urgency_signals(text)
    tech = _extract_tech_keywords(text)
    red_flags = _extract_red_flags(text)
    category = _extract_category(description, tech)
    confidence = _assign_confidence(
        budget, budget_inferred, description, tech, category, inferred
    )

    platform: Platform
    if raw.platform is not None:
        platform = raw.platform
    elif client_spend is not None:
        platform = Platform.UPWORK
    else:
        platform = _detect_platform(text)

    return ParsedListing(
        title=title,
        description=description,
        budget=budget,
        platform=platform,
        url=raw.source_url,
        client_spend_history=client_spend,
        client_hire_rate=client_hire_rate,
        tech_keywords=tech,
        urgency_signals=urgency,
        red_flags=red_flags,
        parse_confidence=confidence,
        inferred_fields=inferred,
        category=category,
    )


def _parse_upwork(raw: "RawListing") -> ParsedListing:
    """Parse Upwork-format text with Budget/Skills/Client labels."""
    text = raw.raw_text
    lines = _split_lines(text)
    title = lines[0] if lines else "Untitled"

    label_re = re.compile(
        r"^(?:budget|skills|client|hourly range|hire rate|"
        r"client spent|payment|posted|proposals?):",
        re.IGNORECASE,
    )
    desc_lines = [ln for ln in lines[1:] if not label_re.match(ln)]
    description = " ".join(desc_lines).strip() or text

    client_spend: float | None = None
    spend_m = re.search(r"[Cc]lient\s+spent\s+\$?([\d,]+(?:\.\d+)?(?:k)?)", text)
    if spend_m:
        client_spend = _parse_dollar_str(spend_m.group(1))

    client_hire_rate: float | None = None
    hire_m = re.search(r"[Hh]ire\s+rate\s*:?\s*([\d.]+)%", text)
    if hire_m:
        client_hire_rate = float(hire_m.group(1))

    return _build_parsed(
        title,
        description,
        raw,
        client_spend=client_spend,
        client_hire_rate=client_hire_rate,
    )


def _parse_reddit(raw: "RawListing") -> ParsedListing:
    """Parse Reddit [HIRING] freeform text."""
    cleaned = re.sub(
        r"^\[(?:HIRING|FOR HIRE)\]\s*", "", raw.raw_text.strip(), flags=re.IGNORECASE
    )
    lines = _split_lines(cleaned)
    title = lines[0] if lines else "Untitled"
    description = " ".join(lines[1:]).strip() if len(lines) > 1 else cleaned
    return _build_parsed(title, description, raw)


def _parse_generic(raw: "RawListing") -> ParsedListing:
    """Parse generic pasted listing. First line = title, rest = description."""
    lines = _split_lines(raw.raw_text)
    title = lines[0] if lines else "Untitled"
    description = " ".join(lines[1:]).strip() if len(lines) > 1 else raw.raw_text
    return _build_parsed(title, description, raw)


def parse_listings(raws: list["RawListing"]) -> list[ParsedListing]:
    """Public entry point: parse RawListings into ParsedListings.

    Auto-detects platform when not specified. Does NOT score or gate.
    """
    results: list[ParsedListing] = []
    for raw in raws:
        effective = (
            raw.platform if raw.platform is not None else _detect_platform(raw.raw_text)
        )
        if effective == Platform.UPWORK:
            results.append(_parse_upwork(raw))
        elif effective == Platform.REDDIT:
            results.append(_parse_reddit(raw))
        else:
            results.append(_parse_generic(raw))
    return results
