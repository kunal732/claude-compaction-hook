#!/usr/bin/env python3
"""
PreCompact hook: Reads the conversation transcript, uses claude -p to extract
design decisions, and saves them to a persistent file per project.

The saved file is then re-injected into context by the SessionStart (compact) hook.
"""

import json
import sys
import subprocess
import os
import hashlib
from datetime import datetime
from pathlib import Path


def project_key(cwd: str) -> str:
    return hashlib.md5(cwd.encode()).hexdigest()[:16]


def read_transcript(transcript_path: str) -> list:
    entries = []
    try:
        with open(transcript_path, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    except (FileNotFoundError, IOError) as e:
        print(f"[pre-compact] Could not read transcript: {e}", file=sys.stderr)
    return entries


def extract_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    return ""


def build_conversation(entries: list) -> str:
    """Reconstruct readable conversation from JSONL transcript entries."""
    lines = []
    for entry in entries:
        # Claude Code transcript format varies; try multiple schemas
        role = entry.get("type") or entry.get("role") or ""
        msg = entry.get("message") or entry
        content = msg.get("content", "") if isinstance(msg, dict) else ""
        text = extract_text(content).strip()

        if not text:
            continue

        if role in ("user", "human"):
            label = "USER"
        elif role == "assistant":
            label = "ASSISTANT"
        else:
            continue

        # Truncate long messages to keep prompt size reasonable
        if len(text) > 3000:
            text = text[:3000] + "\n[...truncated...]"
        lines.append(f"[{label}]\n{text}")

    # Keep the last 80 exchanges max
    return "\n\n---\n\n".join(lines[-80:])


def generate_summary(conversation: str, cwd: str) -> str | None:
    prompt = f"""You are preserving design context before a context window compaction event.

Project: {cwd}

Conversation history:
===
{conversation}
===

Produce a structured "Design Decisions & Anti-Regression Guide" document.
Be exhaustive on rejected approaches — this is the #1 cause of post-compaction regression.

Use exactly this structure:

## CURRENT APPROACH
What implementation approach has been chosen. Be specific.

## REJECTED APPROACHES — DO NOT SUGGEST THESE
List EVERY approach that was considered and rejected, with the reason.
Format each as: "- [REJECTED] <approach>: <why it was rejected>"
This section must be exhaustive. If something was tried and abandoned, list it here.

## KEY DESIGN DECISIONS
Numbered list of concrete decisions made, with rationale.

## HARD CONSTRAINTS
Technical requirements, non-negotiables, environment constraints.

## EXPLICIT DO-NOTs
Bulleted list of specific things NOT to do, derived from the above decisions.

## CURRENT STATE
What has been built/decided so far and what remains.

Keep each section concise but complete."""

    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--output-format", "text"],
            capture_output=True,
            text=True,
            timeout=120,
            env={**os.environ, "CLAUDE_SKIP_HOOKS": "1"},
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        print(f"[pre-compact] claude -p failed: {result.stderr[:500]}", file=sys.stderr)
    except subprocess.TimeoutExpired:
        print("[pre-compact] claude -p timed out after 120s", file=sys.stderr)
    except FileNotFoundError:
        print("[pre-compact] 'claude' CLI not found in PATH", file=sys.stderr)
    return None


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError, ValueError):
        payload = {}

    cwd = payload.get("cwd") or os.getcwd()
    transcript_path = payload.get("transcript_path", "")
    trigger = payload.get("trigger", "auto")
    session_id = payload.get("session_id", "unknown")

    print(f"[pre-compact] trigger={trigger} cwd={cwd}", file=sys.stderr)

    if not transcript_path:
        print("[pre-compact] No transcript_path in payload; skipping.", file=sys.stderr)
        sys.exit(0)

    entries = read_transcript(transcript_path)
    if not entries:
        print("[pre-compact] Transcript is empty; skipping.", file=sys.stderr)
        sys.exit(0)

    print(f"[pre-compact] {len(entries)} transcript entries found.", file=sys.stderr)
    conversation = build_conversation(entries)
    if not conversation.strip():
        print("[pre-compact] No extractable conversation text; skipping.", file=sys.stderr)
        sys.exit(0)

    print("[pre-compact] Generating design decisions summary...", file=sys.stderr)
    summary = generate_summary(conversation, cwd)
    if not summary:
        print("[pre-compact] Summary generation failed; skipping.", file=sys.stderr)
        sys.exit(0)

    # --- Persist the summary ---
    key = project_key(cwd)
    storage_dir = Path.home() / ".claude" / "design-decisions"
    storage_dir.mkdir(parents=True, exist_ok=True)
    output_file = storage_dir / f"{key}.md"

    header = (
        f"# Design Decisions & Anti-Regression Guide\n"
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        f"**Project:** {cwd}\n"
        f"**Session:** {session_id}\n"
        f"**Compaction trigger:** {trigger}\n\n"
    )

    output_file.write_text(header + summary)
    print(f"[pre-compact] Saved to {output_file}", file=sys.stderr)

    # Also write to .claude/ inside the project if that dir exists
    project_dot_claude = Path(cwd) / ".claude"
    if project_dot_claude.is_dir():
        local_file = project_dot_claude / "design-decisions.md"
        local_file.write_text(header + summary)
        print(f"[pre-compact] Also saved to {local_file}", file=sys.stderr)

    sys.exit(0)


if __name__ == "__main__":
    main()
