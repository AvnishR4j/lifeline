#!/usr/bin/env python3
"""
Lifeline — Codex source reader.

Reads the most recent Codex CLI session (rollout-*.jsonl) and produces the same
normalized dict shape as the Claude reader (`extractor.parse_session`), so the
handoff renderer and the rest of the pipeline don't care which CLI the context
came from.

Codex rollout format (verified against codex-cli 0.135.0):
  - one JSON object per line; top-level `type` is one of
    session_meta | turn_context | response_item | event_msg
  - `session_meta.payload`   → cwd, id, cli_version
  - `turn_context.payload`   → cwd (per turn)
  - `response_item.payload`  → when payload.type == "message", a user/assistant/
    developer turn whose `content` is a list of {type, text} blocks
    (user: input_text, assistant: output_text). function_call / reasoning items
    are tool/thinking noise we skip.
"""

import json
import sys
from pathlib import Path

CODEX_SESSIONS = Path.home() / ".codex" / "sessions"

# Wrapper blocks Codex injects into the transcript that are not real user turns.
_NOISE_PREFIXES = (
    "<environment_context>",
    "<user_instructions>",
    "<permissions instructions>",
    "<permissions>",
)


def find_latest_session(session_dir: Path = None) -> Path:
    """Return the most recently modified rollout-*.jsonl session file."""
    search_root = session_dir or CODEX_SESSIONS
    sessions = list(search_root.rglob("rollout-*.jsonl"))
    if not sessions:
        # Fall back to any .jsonl in case the naming scheme shifts.
        sessions = list(search_root.rglob("*.jsonl"))
    if not sessions:
        raise FileNotFoundError(f"No Codex session files found under {search_root}")
    return max(sessions, key=lambda p: p.stat().st_mtime)


def _is_noise(text: str) -> bool:
    stripped = text.lstrip()
    return any(stripped.startswith(p) for p in _NOISE_PREFIXES)


def _join_text(content) -> str:
    """Codex message content is a list of {type, text} blocks; join their text."""
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    parts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("text")]
    return "\n".join(parts).strip()


def parse_session(path: Path) -> dict:
    """Pull the useful fields out of a Codex rollout JSONL file."""
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

    cwd = None
    last_prompt = None
    title = None
    conversation = []  # list of (role, text)

    for e in entries:
        etype = e.get("type")
        payload = e.get("payload", {}) or {}

        if etype in ("session_meta", "turn_context"):
            cwd = payload.get("cwd") or cwd

        elif etype == "response_item" and payload.get("type") == "message":
            role = payload.get("role")
            if role not in ("user", "assistant"):
                continue  # skip developer/system wrappers
            text = _join_text(payload.get("content"))
            if not text or _is_noise(text):
                continue
            conversation.append((role, text))
            if role == "user":
                last_prompt = text
                if title is None:
                    # Codex has no session title; derive one from the first ask.
                    title = text.splitlines()[0][:120]

    return {
        "title": title,
        "cwd": cwd,
        "git_branch": None,  # Codex rollouts don't record a git branch
        "last_prompt": last_prompt,
        "conversation": conversation,
        "session_file": str(path),
    }


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    session = find_latest_session(Path(arg) if arg else None)
    data = parse_session(session)
    # Lazy import so this module stays usable standalone.
    import extractor

    print(extractor.build_handoff(data, source_name="Codex", assistant_label="Codex"))


if __name__ == "__main__":
    main()
