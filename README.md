# Scout

Freelance job scoring engine. Takes raw job listings, parses them into structured data, runs them through an 8-dimension scoring model with hard gates, and normalizes winners into Linear tickets.

## How it works

```
Raw listing → Parse → Gate check → Score (8 dimensions) → Rank → Normalize to ticket
```

**Hard gates** reject before scoring — effort too high, budget too low, MVP/equity traps, unverified payment. If a listing passes gates, it gets scored across 8 weighted dimensions:

| Dimension | Weight | Direction |
|-----------|--------|-----------|
| Clarity | 1.5x | Higher = better defined scope |
| Fit | 1.5x | Higher = closer to core stack |
| Price | 1.0x | Higher = better budget |
| Urgency | 1.0x | Higher = faster turnaround needed |
| Effort | 1.0x | Subtracted — lower effort = better |
| Risk | 1.0x | Subtracted — lower risk = better |
| Client Risk | 1.0x | Subtracted — verified clients score lower |
| Technical Risk | 1.0x | Subtracted — isolated work scores lower |

Scores map to response SLAs: >= 12 = respond in 30 min, >= 8 = 60 min, >= 5 = 4 hours.

## Stack

- Python 3.12+
- Pydantic v2 for data contracts
- 5-stage pipeline: `RawListing → ParsedListing → ScoredListing → ApprovedListing → NormalizedTicket`

## Usage

```bash
# Score a listing via CLI
python -m scout score "Fix webhook auth failure in Next.js app. Budget $400..."

# Run the full pipeline
python -m scout pipeline listings.json
```

## Project structure

```
src/scout/
├── models.py       # Pydantic data contracts (5 stages)
├── intake.py       # Multi-format parser (text, JSON, structured)
├── gates.py        # Hard gate checks (8 gates)
├── scoring.py      # 8-dimension scoring + bonuses + SLA
├── pipeline.py     # Pipeline orchestrator
├── normalizer.py   # Converts scored listings to Linear tickets
└── cli.py          # CLI interface
```

## Testing

```bash
python -m pytest tests/ -v
```

## License

MIT
