#!/bin/bash
# Scout Patrol — Headless Upwork scanner
# Runs via launchd every 15 min, 7AM-11PM CT
# Uses claude --print --chrome to browse Upwork and score listings

set -euo pipefail

CLAUDE="/Users/benjaminsterrett/.local/bin/claude"
PROMPT_FILE="/Users/benjaminsterrett/.claude/reference/scout-patrol-prompt.md"
LOG_DIR="/Users/benjaminsterrett/Projects/scout/data/logs"
LOG_FILE="$LOG_DIR/patrol-$(date +%Y-%m-%d).log"

mkdir -p "$LOG_DIR"

echo "--- Scout Patrol $(date '+%Y-%m-%d %H:%M:%S') ---" >> "$LOG_FILE"

# Check hours (7AM-11PM CT). Launchd handles scheduling but double-check.
HOUR=$(TZ=America/Chicago date +%H)
if [ "$HOUR" -lt 7 ] || [ "$HOUR" -ge 23 ]; then
    echo "Outside patrol hours ($HOUR CT). Skipping." >> "$LOG_FILE"
    exit 0
fi

# Check if Chrome is running (required for chrome extension)
if ! pgrep -x "Google Chrome" > /dev/null 2>&1; then
    echo "Chrome not running. Skipping patrol." >> "$LOG_FILE"
    exit 0
fi

# Read the patrol prompt
if [ ! -f "$PROMPT_FILE" ]; then
    echo "Prompt file missing: $PROMPT_FILE" >> "$LOG_FILE"
    exit 1
fi

PROMPT="Current date/time: $(TZ=America/Chicago date '+%Y-%m-%d %I:%M %p CT')

$(cat "$PROMPT_FILE")"

# Run claude headlessly with chrome flag
# --print: non-interactive, outputs result and exits
# --chrome: enables claude-in-chrome MCP
# --allowedTools: restrict to only tools the patrol needs (security hardening)
# --setting-sources user: load only user-level settings, not project settings
# Isolation: run from empty temp dir so CLAUDE.md auto-discovery finds nothing
# --add-dir: grant access to tracker file directory
PATROL_WORKDIR=$(mktemp -d)
trap 'rm -rf "$PATROL_WORKDIR"' EXIT
cd "$PATROL_WORKDIR"
"$CLAUDE" --print --chrome --permission-mode bypassPermissions \
  --setting-sources user \
  --add-dir /Users/benjaminsterrett/Projects/scout/data \
  --allowedTools "mcp__claude-in-chrome__navigate mcp__claude-in-chrome__computer mcp__claude-in-chrome__get_page_text mcp__claude-in-chrome__find mcp__claude-in-chrome__form_input mcp__claude-in-chrome__tabs_context_mcp mcp__claude-in-chrome__tabs_create_mcp mcp__claude-in-chrome__read_page mcp__claude-in-chrome__javascript_tool Bash(/Users/benjaminsterrett/Projects/scout/bin/scout-telegram.sh:*) Read Write" \
  <<< "$PROMPT" >> "$LOG_FILE" 2>&1

echo "--- Patrol complete $(date '+%Y-%m-%d %H:%M:%S') ---" >> "$LOG_FILE"
