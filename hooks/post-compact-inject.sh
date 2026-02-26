#!/usr/bin/env bash
# SessionStart (compact) hook: Re-injects the design decisions summary into
# Claude's context after a compaction event.
#
# stdout → gets prepended to Claude's context (this is the injection mechanism)
# stderr → shown to the user only, not to Claude

set -euo pipefail

# Read the JSON payload from stdin
PAYLOAD=$(cat)

# Extract cwd from payload; fall back to $PWD
CWD=$(printf '%s' "$PAYLOAD" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    print(d.get('cwd') or '')
except Exception:
    print('')
" 2>/dev/null || true)

if [[ -z "$CWD" ]]; then
    CWD="$PWD"
fi

# Compute project key (must match the Python script's logic)
KEY=$(python3 -c "
import hashlib, sys
cwd = sys.argv[1]
print(hashlib.md5(cwd.encode()).hexdigest()[:16])
" "$CWD" 2>/dev/null || true)

GLOBAL_FILE="$HOME/.claude/design-decisions/${KEY}.md"
LOCAL_FILE="${CWD}/.claude/design-decisions.md"

# Prefer local project file, fall back to global
DECISIONS_FILE=""
if [[ -f "$LOCAL_FILE" ]]; then
    DECISIONS_FILE="$LOCAL_FILE"
elif [[ -f "$GLOBAL_FILE" ]]; then
    DECISIONS_FILE="$GLOBAL_FILE"
fi

if [[ -z "$DECISIONS_FILE" ]]; then
    echo "[post-compact] No design decisions file found for project: $CWD" >&2
    exit 0
fi

echo "[post-compact] Injecting design decisions from $DECISIONS_FILE" >&2

# Everything below goes to STDOUT → injected into Claude's context
cat <<'HEADER'
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️  CONTEXT RESTORED AFTER COMPACTION — CRITICAL DESIGN CONTEXT ⚠️
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
The conversation was compacted. The following design decisions were
recorded BEFORE compaction. You MUST adhere to them. Do NOT suggest
any approach listed under "REJECTED APPROACHES" or "EXPLICIT DO-NOTs".
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

HEADER

cat "$DECISIONS_FILE"

cat <<'FOOTER'

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
End of pre-compaction design context. Treat the above as ground truth.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FOOTER
