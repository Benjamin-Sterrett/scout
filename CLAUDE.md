# Scout

## Session Start
Say: **"resume scout"** -- I'll check Linear for Scout issues, read `.handoff.md`, and pick up where we left off.

**Quick commands:**
- `linear issue list` -- see your current issues
- `linear issue start PRJ-##` -- start working on an issue

## Current Status
- **Phase:** Setup / Discovery
- **Last:** Project created (2026-04-01)
- **Done:** Initial setup
- **Next:** Run discovery research, synthesize findings, build v1 scoring model
- **Handoff:** See `.handoff.md` for session details

## Project Management

**Linear project:** Search Linear for "Scout" or check project list
- **Team:** Projects (PRJ)
- **Project:** Scout

## Vision

**Freelance job arbitrage system.** Converts messy freelance listings into structured tickets the dev-workflow can execute deterministically. Only runs jobs that score high on a defined ROI model.

**Core insight:** Others see messy jobs with unclear scope. We see structured problems with fast execution and high margin. The dev-workflow IS the unfair advantage.

### ROI Scoring Model

```
Score = (Clarity + Fit + Price) - (Effort + Risk)
```

Each dimension scored 1-5. Hard gates reject before scoring:
- Effort > 3 -> reject
- Clarity < 3 -> reject
- Fit < 3 -> reject

### Pipeline (v1)

1. **Intake** -- paste listings, Claude parses
2. **Filter** -- hard gates remove ~80%
3. **Score + Rank** -- top 3-5 returned
4. **Normalize** -- selected job becomes Linear ticket (problem statement, scope, assumptions, deliverables, acceptance criteria)
5. **Approve** -- human gate (initially)
6. **Execute** -- dev-workflow takes over

### Roadmap

- **v1:** Semi-manual. Paste listings, Claude scores + ranks, creates ticket, run workflow.
- **v2:** Automated intake (platform APIs/scraping), auto-create tickets.
- **v3:** Night Shift picks jobs + executes autonomously.

## Tech Stack

| Component | Technology |
|-----------|------------|
| Scoring engine | Python |
| Pipeline orchestration | Claude Code + dev-workflow |
| Issue tracking | Linear (PRJ team) |
| Platform intake | TBD (discovery needed) |

## Development Workflow (v5.7)

Use `/implement` or invoke the `dev-workflow` skill for any implementation task.

**Bug fixes:** Invoke `systematic-debugging` skill FIRST, then `dev-workflow`. Hook enforces `.debug-report.md` on `fix/*` branches.

**Full Path (Medium/High blast radius) -- 18 steps:**
IDENTIFY -> BRANCH -> DISCOVER -> PLAN -> VALIDATE -> APPROVE -> IMPLEMENT -> SCOPE-CHECK -> VERIFY -> SIMPLIFY -> REVIEW -> TRIAGE -> FIX -> RE-VERIFY -> DELIVER -> PR-REVIEW -> DEPLOY-VERIFY -> LINEAR-UPDATE

**Fast Path (Low blast radius) -- 7 steps:**
IDENTIFY -> DISCOVER -> IMPLEMENT -> VERIFY -> DELIVER -> PR-REVIEW -> HANDOFF

**Batch Path (2+ independent tickets) -- 8 orchestrator steps:**
IDENTIFY -> DEPENDENCY-MAP -> PLAN-BATCH -> VALIDATE-BATCH -> DISPATCH -> MONITOR -> INTEGRATE -> LINEAR-UPDATE

**Rules:**
- No work without a Linear issue
- Bug fixes require systematic debugging before dev-workflow (hook-enforced)
- One issue = one branch = one PR (max 500 LOC per PR)
- Dual review (Security + Codex) required before commit
- Codex must APPROVE PR before merge (both paths)
- Linear issues created for ALL review findings
- Build must pass before commit
- All hooks enforced globally -- no project-level overrides needed
- Context7 doc lookup mandatory before coding with any library (PLAN + IMPLEMENT)
- SCHEMA-CHECK runs as sub-step 0 of VERIFY
- DEPLOY-VERIFY runs after PR-REVIEW (auto-skips without `deploy-manifest.json`)

**Bloat Prevention (v4.3):**
- PLAN must include "Existing Patterns to Reuse" + LOC budget
- Check existing code before writing >50 new lines (reuse-or-justify)
- 300 LOC ceiling per file -- split or justify if exceeded
- Codex review flags duplication, monolithic components, hardcoded content

**Incremental PRs (v4.4):**
- Max 500 LOC per PR -- one sub-ticket = one branch = one PR
- PLAN step defines PR boundaries with LOC estimates
- SCOPE-CHECK enforces: `git diff --stat | tail -1` must show <=500 insertions

## LSP Tools (claude-lsp-bridge)

6 LSP-powered tools are available globally via the `claude-lsp-bridge` MCP server:
`find_definition`, `find_references`, `get_hover`, `get_diagnostics`, `find_symbol`, `list_file_symbols`

## Code Standards
- Type hints/annotations required
- macOS Keychain for all secrets (no env vars, no inline)
- Follow project-specific linting rules

## Handoff Rules

**Before ending session or at 70%+ context:**
1. Update `.handoff.md` with:
   - What was completed (issues, commits)
   - Current Linear status
   - What's blocked and on whom
   - Clear next steps
2. Update "Current Status" block above
3. Commit any uncommitted work

**Last Updated:** 2026-04-01
