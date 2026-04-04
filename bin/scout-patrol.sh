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

PROMPT=$(cat "$PROMPT_FILE")

# Run claude headlessly with chrome flag
# --print: non-interactive, outputs result and exits
# --chrome: enables claude-in-chrome MCP
# --max-turns 30: enough for a full patrol cycle
"$CLAUDE" --print --chrome --permission-mode bypassPermissions "$PROMPT" >> "$LOG_FILE" 2>&1

echo "--- Patrol complete $(date '+%Y-%m-%d %H:%M:%S') ---" >> "$LOG_FILE"
