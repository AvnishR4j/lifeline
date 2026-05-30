#!/usr/bin/env python3
"""
Lifeline — Gemini source reader.

Reads the most recent Gemini CLI chat session and produces the same normalized
dict shape as the Claude/Codex readers, so the handoff pipeline is CLI-agnostic.

Gemini chat format (verified against gemini-cli 0.44.1):
  - chats live under ~/.gemini/tmp/<project>/chats/session-*.jsonl
  - one JSON object per line. The first line is session metadata
    (sessionId, projectHash, startTime, ...).
  - messages arrive two ways in the same log:
      * a `{"$set": {"messages": [...]}}` line that seeds the message list
      * bare append lines: {"id", "timestamp", "type", "content"}
    so we walk the file in order, taking messages from both.
  - a message `type` is "user" or "gemini"; `content` is either a plain string
    or a list of {text} blocks.
  - the working directory is recoverable from the `<session_context>` wrapper the
    CLI injects as the first user turn (which we otherwise skip as noise).
"""

import json
import re
import sys
from pathlib import Path

GEMINI_CHATS = Path.home() / ".gemini" / "tmp"
_PROJECTS_JSON = Path.home() / ".gemini" / "projects.json"

# Wrapper turns the CLI injects that are not real user input.
_NOISE_PREFIXES = (
    "<session_context>",
    "<environment_context>",
)

_WORKSPACE_RE = re.compile(r"Workspace Directories:\**\s*\n\s*-\s*(/\S+)")


def find_latest_session(session_dir: Path = None) -> Path:
    """Return the most recently modified Gemini chat session file."""
    search_root = session_dir or GEMINI_CHATS
    sessions = list(search_root.rglob("chats/session-*.jsonl"))
    if not sessions:
        # Tolerate naming/layout drift: any chat jsonl under the root.
        sessions = list(search_root.rglob("chats/*.jsonl")) or list(
            search_root.rglob("*.jsonl")
        )
    if not sessions:
        raise FileNotFoundError(f"No Gemini session files found under {search_root}")
    return max(sessions, key=lambda p: p.stat().st_mtime)


def _is_noise(text: str) -> bool:
    stripped = text.lstrip()
    return any(stripped.startswith(p) for p in _NOISE_PREFIXES)


def _text_of(content) -> str:
    """Gemini content is either a plain string or a list of {text} blocks."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("text")]
        return "\n".join(parts).strip()
    return ""


def _iter_messages(entries):
    """Yield message dicts in order, from both $set.messages and append lines."""
    for e in entries:
        if not isinstance(e, dict):
            continue
        if isinstance(e.get("$set"), dict):
            for m in e["$set"].get("messages", []):
                yield m
        elif e.get("type") and "content" in e:
            yield e


def _cwd_from_context(text: str):
    m = _WORKSPACE_RE.search(text)
    return m.group(1) if m else None


def _cwd_from_projects(session_path: Path):
    """Fallback: map the project folder name back to its workspace path."""
    try:
        project_seg = str(session_path).split("/tmp/")[1].split("/")[0]
        projects = json.loads(_PROJECTS_JSON.read_text()).get("projects", {})
        for path, name in projects.items():
            if name == project_seg:
                return path
    except (IndexError, OSError, json.JSONDecodeError, KeyError):
        pass
    return None


def parse_session(path: Path) -> dict:
    """Pull the useful fields out of a Gemini chat JSONL file."""
    entries = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    cwd = None
    title = None
    last_prompt = None
    conversation = []
    seen_ids = set()

    for m in _iter_messages(entries):
        mid = m.get("id")
        if mid is not None and mid in seen_ids:
            continue  # the seed batch and appends can overlap; dedupe by id
        if mid is not None:
            seen_ids.add(mid)

        mtype = m.get("type")
        role = "user" if mtype == "user" else (
            "assistant" if mtype in ("gemini", "model", "assistant") else None
        )
        if role is None:
            continue

        text = _text_of(m.get("content"))
        if not text:
            continue

        if _is_noise(text):
            # The session_context wrapper is noise, but it carries the cwd.
            if cwd is None:
                cwd = _cwd_from_context(text)
            continue

        conversation.append((role, text))
        if role == "user":
            last_prompt = text
            if title is None:
                title = text.splitlines()[0][:120]

    if cwd is None:
        cwd = _cwd_from_projects(path)

    return {
        "title": title,
        "cwd": cwd,
        "git_branch": None,  # Gemini chats don't record a git branch
        "last_prompt": last_prompt,
        "conversation": conversation,
        "session_file": str(path),
    }


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    session = find_latest_session(Path(arg) if arg else None)
    data = parse_session(session)
    import extractor

    print(extractor.build_handoff(data, source_name="Gemini", assistant_label="Gemini"))


if __name__ == "__main__":
    main()
