#!/usr/bin/env python3
"""
Lifeline — environment diagnostics.

Checks whether each supported CLI is installed, whether each known session root
exists, and whether Lifeline can find and parse the latest session for every
source. This is intentionally read-only.
"""

import argparse
import importlib.util
import importlib.metadata
import os
import platform
import shutil
import sys

import handoff
import session_tracker
import sources
import terminal_backends
import terminal_launchers


def check_runtime():
    try:
        version = importlib.metadata.version("lifeline")
    except importlib.metadata.PackageNotFoundError:
        version = "development checkout"
    rows = [
        (True, _ok(f"Lifeline: {version}")),
        (True, _ok(f"OS: {platform.platform()}")),
        (True, _ok(f"Python: {platform.python_version()}")),
        (True, _ok(f"wrapper backend: {terminal_backends.backend_name()}")),
        (True, _ok(f"new-terminal backend: {terminal_launchers.launcher_name()}")),
    ]
    if os.name == "nt":
        available = importlib.util.find_spec("winpty") is not None
        rows.append((
            available,
            _ok("pywinpty available") if available else
            _warn("pywinpty missing; automatic protection cannot run"),
        ))
    if terminal_backends.is_wsl():
        rows.append((True, _ok("WSL detected; using Unix PTY backend")))
    return rows


def check_registry():
    try:
        records = session_tracker.ActiveRegistry().live()
    except OSError as exc:
        return [(False, _warn(f"active-session registry unavailable: {exc}"))]
    return [(True, _ok(f"active-session registry healthy: {len(records)} live session(s)"))]


def _ok(label: str) -> str:
    return f"OK    {label}"


def _warn(label: str) -> str:
    return f"WARN  {label}"


def check_clis():
    rows = []
    for name in sorted(handoff.SUPPORTED_TARGETS):
        path = shutil.which(name)
        if path:
            rows.append((True, _ok(f"{name} found at {path}")))
        else:
            rows.append((False, _warn(f"{name} not found on PATH")))
    return rows


def check_sources():
    rows = []
    for name in sorted(sources.SUPPORTED_SOURCES):
        source = sources.get_source(name)
        if source.root.exists():
            rows.append((True, _ok(f"{source.display_name} session root exists: {source.root}")))
        else:
            rows.append((False, _warn(f"{source.display_name} session root missing: {source.root}")))
            continue

        try:
            session = source.find_latest(None)
        except Exception as exc:
            rows.append((False, _warn(f"{source.display_name} latest session not found: {exc}")))
            continue

        rows.append((True, _ok(f"{source.display_name} latest session: {session}")))

        try:
            data = source.parse(session)
        except Exception as exc:
            rows.append((False, _warn(f"{source.display_name} latest session failed to parse: {exc}")))
            continue

        turns = len(data.get("conversation", []))
        cwd = data.get("cwd") or "(cwd unavailable)"
        useful = bool(data.get("title") or data.get("last_prompt") or turns)
        rows.append((
            True,
            _ok(f"{source.display_name} parse works: {turns} turns, cwd {cwd}")
            if useful else
            _warn(f"{source.display_name} latest session parsed but contains no useful turns"),
        ))
    return rows


def print_matrix():
    print("\nSupported handoff matrix:")
    for src in sorted(sources.SUPPORTED_SOURCES):
        targets = [dst for dst in sorted(handoff.SUPPORTED_TARGETS) if dst != src]
        print(f"  {src} -> {', '.join(targets)}")
    print("  same-source handoff is intentionally blocked")


def main():
    parser = argparse.ArgumentParser(
        description="Check Lifeline CLI installs, session sources, and parser health."
    )
    parser.parse_args()

    print("Lifeline doctor\n")

    print("Runtime:")
    runtime_rows = check_runtime()
    for _, line in runtime_rows:
        print(f"  {line}")

    print("\nCLI targets:")
    rows = check_clis()
    for _, line in rows:
        print(f"  {line}")

    print("\nSession sources:")
    source_rows = check_sources()
    for _, line in source_rows:
        print(f"  {line}")

    print("\nActive registry:")
    registry_rows = check_registry()
    for _, line in registry_rows:
        print(f"  {line}")

    print_matrix()

    # Missing individual targets are warnings, because users may only need one.
    # No targets or any source parse failure means the supported matrix cannot
    # work fully on this machine.
    target_ok = any(ok for ok, _ in rows)
    source_ok = all(ok for ok, _ in source_rows)
    runtime_ok = all(ok for ok, _ in runtime_rows)
    registry_ok = all(ok for ok, _ in registry_rows)
    return 0 if runtime_ok and target_ok and source_ok and registry_ok else 1


if __name__ == "__main__":
    sys.exit(main())
