#!/usr/bin/env python3
"""
Lifeline — context extractor.

Reads the most recent Claude Code session and produces a structured handoff
summary (goal, recent conversation, code changes) so another AI CLI can resume
the work with zero re-explanation.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

CLAUDE_PROJECTS = Path.home() / ".claude" / "projects"

# Noise we never want to feed into a handoff prompt.
_META_PATTERNS = (
    "<local-command-caveat>",
    "<command-name>",
    "<command-message>",
    "<local-command-stdout>",
    "Caveat: The messages below were generated",
)


def find_latest_session(project_dir: Path = None) -> Path:
    """Return the most recently modified .jsonl session file."""
    search_root = project_dir or CLAUDE_PROJECTS
    sessions = list(search_root.rglob("*.jsonl"))
    if not sessions:
        raise FileNotFoundError(f"No Claude session files found under {search_root}")
    return max(sessions, key=lambda p: p.stat().st_mtime)


def _is_noise(text: str) -> bool:
    return any(pat in text for pat in _META_PATTERNS)


def parse_session(path: Path) -> dict:
    """Pull the useful fields out of a session JSONL file."""
    entries = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line:
            try:
                entry = json.loads(line)
                if isinstance(entry, dict):
                    entries.append(entry)
            except json.JSONDecodeError:
                continue

    title = None
    cwd = None
    git_branch = None
    last_prompt = None
    conversation = []  # list of (role, text)

    for e in entries:
        etype = e.get("type")

        if etype == "ai-title":
            title = e.get("aiTitle") or title

        elif etype == "system":
            cwd = e.get("cwd") or cwd
            git_branch = e.get("gitBranch") or git_branch

        elif etype == "last-prompt":
            last_prompt = e.get("lastPrompt") or last_prompt

        elif etype == "user" and not e.get("isMeta"):
            content = e.get("message", {}).get("content")
            text = _extract_user_text(content)
            if text and not _is_noise(text):
                conversation.append(("user", text))

        elif etype == "assistant":
            content = e.get("message", {}).get("content")
            text = _extract_assistant_text(content)
            if text:
                conversation.append(("assistant", text))

    return {
        "title": title,
        "cwd": cwd,
        "git_branch": git_branch,
        "last_prompt": last_prompt,
        "conversation": conversation,
        "session_file": str(path),
    }


def _extract_user_text(content) -> str:
    """User content is usually a plain string; lists are tool results (skip)."""
    if isinstance(content, str):
        return content.strip()
    return ""


def _extract_assistant_text(content) -> str:
    """Join text blocks; note tool calls compactly. Drop thinking/signatures."""
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""

    parts = []
    tools = []
    for block in content:
        btype = block.get("type")
        if btype == "text":
            txt = block.get("text", "").strip()
            if txt:
                parts.append(txt)
        elif btype == "tool_use":
            tools.append(block.get("name", "tool"))

    if tools:
        parts.append(f"[ran tools: {', '.join(tools)}]")
    return "\n".join(parts).strip()


def get_git_diff(cwd: str) -> str:
    """Return uncommitted changes in the working directory, if it's a repo."""
    if not cwd or not Path(cwd).exists():
        return ""
    try:
        result = subprocess.run(
            ["git", "-C", cwd, "diff", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return ""


def build_handoff(
    data: dict,
    source_name: str = "Claude Code",
    assistant_label: str = "Claude",
    max_turns: int = 12,
    max_diff_chars: int = 4000,
) -> str:
    """Render a markdown handoff prompt for another AI CLI.

    `source_name`/`assistant_label` describe which CLI the context came from, so
    the same renderer works for Claude, Codex, etc.
    """
    lines = []
    lines.append(f"# Resuming work from {source_name}\n")
    lines.append(
        "You are picking up a coding session that was interrupted (rate limit). "
        "Below is the full context. Continue exactly where it left off — do not "
        "re-ask the user to explain anything already covered here.\n"
    )

    lines.append("## Task")
    lines.append(data.get("title") or "(no title captured)")
    lines.append("")

    if data.get("cwd"):
        lines.append("## Environment")
        lines.append(f"- Working directory: `{data['cwd']}`")
        if data.get("git_branch"):
            lines.append(f"- Git branch: `{data['git_branch']}`")
        lines.append("")

    convo = data.get("conversation", [])
    recent = convo[-max_turns:]
    if recent:
        lines.append("## Recent conversation")
        for role, text in recent:
            label = "User" if role == "user" else assistant_label
            snippet = text if len(text) <= 600 else text[:600] + " …"
            lines.append(f"**{label}:** {snippet}\n")

    if data.get("last_prompt"):
        lines.append("## Last thing the user asked")
        lines.append(f"> {data['last_prompt']}")
        lines.append("")

    diff = get_git_diff(data.get("cwd"))
    if diff:
        if len(diff) > max_diff_chars:
            diff = diff[:max_diff_chars] + "\n… (diff truncated)"
        lines.append("## Uncommitted code changes (git diff HEAD)")
        lines.append("```diff")
        lines.append(diff)
        lines.append("```")
        lines.append("")

    lines.append("## Your job")
    lines.append(
        "Resume the work above. If the last user request was unfinished, complete it."
    )

    return "\n".join(lines)


def main():
    project_arg = sys.argv[1] if len(sys.argv) > 1 else None
    project_dir = Path(project_arg) if project_arg else None

    session = find_latest_session(project_dir)
    data = parse_session(session)
    handoff = build_handoff(data)
    print(handoff)


if __name__ == "__main__":
    main()
