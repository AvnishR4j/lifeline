#!/usr/bin/env python3
"""
Lifeline — source registry.

Which AI CLIs Lifeline can capture context *from*. Mirrors the `TARGETS`
registry in handoff.py (which CLIs it can hand off *to*). Each Source exposes a
uniform interface — `find_latest(dir)` and `parse(path)` returning the normalized
dict that `extractor.build_handoff` consumes — so the rest of the pipeline never
branches on which CLI the session came from.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Tuple

import codex_reader
import extractor


@dataclass(frozen=True)
class Source:
    name: str  # CLI key, e.g. "claude"
    display_name: str  # human label for the handoff header, e.g. "Claude Code"
    assistant_label: str  # how to label the assistant's turns, e.g. "Claude"
    root: Path  # default session search root (also the path-safety boundary)
    find_latest: Callable[[Optional[Path]], Path]
    parse: Callable[[Path], dict]


SOURCES = {
    "claude": Source(
        name="claude",
        display_name="Claude Code",
        assistant_label="Claude",
        root=extractor.CLAUDE_PROJECTS,
        find_latest=extractor.find_latest_session,
        parse=extractor.parse_session,
    ),
    "codex": Source(
        name="codex",
        display_name="Codex",
        assistant_label="Codex",
        root=codex_reader.CODEX_SESSIONS,
        find_latest=codex_reader.find_latest_session,
        parse=codex_reader.parse_session,
    ),
}

SUPPORTED_SOURCES = set(SOURCES)


def get_source(name: str) -> Source:
    try:
        return SOURCES[name]
    except KeyError:
        raise ValueError(f"Unsupported source: {name}")


def detect_latest_source() -> Tuple[Source, Path]:
    """Pick the source whose most recent session file is the newest overall.

    Lets `--from auto` just resume whatever CLI you were last using.
    """
    best = None  # (mtime, Source, Path)
    for src in SOURCES.values():
        try:
            path = src.find_latest(None)
        except FileNotFoundError:
            continue
        mtime = path.stat().st_mtime
        if best is None or mtime > best[0]:
            best = (mtime, src, path)
    if best is None:
        roots = ", ".join(str(s.root) for s in SOURCES.values())
        raise FileNotFoundError(f"No sessions found for any known source CLI (looked in: {roots})")
    return best[1], best[2]
