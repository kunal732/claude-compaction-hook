# claude-compaction-hook

Prevents design decision regressions after Claude Code context compaction.

When Claude Code compacts the context window, the summarization process can lose nuance -- particularly around approaches that were explored and discarded. This creates regressions where Claude re-suggests something you already ruled out. This hook explicitly captures design decisions and rejected approaches before compaction and re-injects them afterward, so that context survives intact.

## What it does

1. **Before compaction** -- reads the full conversation transcript and uses `claude -p` to extract:
   - Current approach (what you ARE doing)
   - Rejected approaches (what NOT to suggest again)
   - Key design decisions with rationale
   - Hard constraints
   - Explicit do-nots

2. **After compaction** -- injects that summary back into Claude's context before you type your next message

3. **Manual command** -- run `/design-decisions` at any time to generate a snapshot

## Requirements

- [Claude Code](https://claude.ai/code) CLI installed
- Python 3 (ships with macOS and most Linux distros)

## Install

**1. Copy the hook scripts:**

```bash
cp hooks/pre-compact-decisions.py ~/.claude/hooks/
cp hooks/post-compact-inject.sh ~/.claude/hooks/
chmod +x ~/.claude/hooks/pre-compact-decisions.py ~/.claude/hooks/post-compact-inject.sh
```

**2. Copy the slash command:**

```bash
cp commands/design-decisions.md ~/.claude/commands/
```

**3. Add the hooks to `~/.claude/settings.json`:**

```json
{
  "hooks": {
    "PreCompact": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"$HOME/.claude/hooks/pre-compact-decisions.py\"",
            "timeout": 120
          }
        ]
      }
    ],
    "SessionStart": [
      {
        "matcher": "compact",
        "hooks": [
          {
            "type": "command",
            "command": "bash \"$HOME/.claude/hooks/post-compact-inject.sh\""
          }
        ]
      }
    ]
  }
}
```

If you already have a `hooks` block, merge these entries in -- don't replace the whole block.

No restart needed. Hooks are active immediately.

## Where summaries are saved

- `~/.claude/design-decisions/<project-hash>.md` -- always written
- `<project>/.claude/design-decisions.md` -- written if `.claude/` already exists in your project

## File structure

```
hooks/
  pre-compact-decisions.py   # PreCompact hook -- reads transcript, generates summary
  post-compact-inject.sh     # SessionStart(compact) hook -- re-injects summary
commands/
  design-decisions.md        # /design-decisions slash command
```
