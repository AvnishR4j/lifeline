#!/usr/bin/env python3
"""
Lifeline — auto-detection wrapper.

Runs an AI CLI (default: `claude`) inside the platform's interactive terminal
backend while Lifeline watches its output for a usage-limit message. macOS and
native Windows can immediately open the target in a new terminal while leaving
the limited session open. Linux and WSL hand off after the wrapped session ends.

    python3 watch.py                 # wrap `claude`, hand off to codex on limit
    python3 watch.py --to codex      # explicit target
    python3 watch.py -- claude --foo # pass args through to the wrapped CLI
    python3 watch.py --selftest      # verify detection patterns, run nothing
"""

import argparse
import ntpath
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import handoff  # for SUPPORTED_TARGETS so --to is validated up front
import session_tracker
import sources  # to map the wrapped CLI to a capture source
import terminal_backends
import terminal_launchers

HERE = Path(__file__).resolve().parent

# Strip ANSI escape sequences before matching, so colored TUI output doesn't
# hide the limit message.
ANSI_RE = re.compile(rb"\x1b\[[0-9;?]*[ -/]*[@-~]")

# Phrases that signal an involuntary usage/rate-limit interruption.
#
# These are derived from the ACTUAL strings shipped in each CLI, not guesses:
#   - Claude Code (binary v2.1.156): "usage limit reached" is its canonical
#     blocked-state phrase; "/upgrade to increase your usage limit." is the nudge.
#   - Codex (codex-cli 0.135.0): "You've hit your usage limit for <plan>"; its own
#     retry logic keys on "rate limit" / "too many requests" / "429".
#   - Gemini (gemini-cli 0.44.1): "Usage limit reached for <model>" and "Rate
#     limit exceeded." (both already covered below); quota errors surface as the
#     Google API status "RESOURCE_EXHAUSTED" / "429 Too Many Requests".
# We keep the patterns SPECIFIC to usage/rate limits, because these CLIs emit
# several other "... limit reached" messages that must NOT trigger a handoff (see
# _NON_LIMIT_PATTERNS and the selftest): a bare "limit reached" match would fire
# on all of them.
LIMIT_PATTERNS = [
    re.compile(r"usage limit reached", re.I),
    re.compile(r"reached your (?:usage|account|plan) limit", re.I),
    re.compile(r"hit your (?:usage|account|plan) limit", re.I),  # Codex
    re.compile(r"upgrade to increase your usage limit", re.I),
    re.compile(r"approaching .{0,30}usage limit", re.I),
    re.compile(r"rate limit(?:ed|ing| reached| exceeded)", re.I),
    re.compile(r"too many requests", re.I),       # Codex/Gemini 429 surface text
    re.compile(r"resource_exhausted", re.I),      # Google API quota status (Gemini)
    # Session / weekly / monthly limit banners, e.g. "5-hour limit reached ∙
    # resets in 2h" — require a window word adjacent to "limit" + reached/reset.
    re.compile(r"\b(?:\d+-hour|hourly|weekly|monthly|session)\b[^.\n]{0,40}\blimit\b[^.\n]{0,40}\b(?:reached|reset)", re.I),
]

# Look-alikes that contain "limit" but are NOT usage/rate-limit interruptions.
# If a chunk matches a LIMIT_PATTERN but the surrounding text also matches one of
# these, we suppress it (defends the broader rate-limit pattern against e.g.
# "Server is temporarily limiting requests (not your usage limit)").
_NON_LIMIT_PATTERNS = [
    re.compile(r"context limit", re.I),
    re.compile(r"not your usage limit", re.I),
    re.compile(r"fast limit reached", re.I),          # only disables fast mode
    re.compile(r"(?:concurrent|export|recursion|size|stack|jit) limit", re.I),
]


class LimitWatcher:
    """Scans a byte stream for a usage-limit message, tolerant of ANSI codes
    and phrases split across read chunks."""

    def __init__(self):
        self._tail = b""          # carry-over so cross-chunk matches still hit
        self.detected = False
        self.matched_phrase = None

    def feed(self, data: bytes):
        if self.detected or not data:
            return
        buf = self._tail + data
        text = ANSI_RE.sub(b"", buf).decode("utf-8", "ignore")
        for pat in LIMIT_PATTERNS:
            m = pat.search(text)
            if m and not self._is_false_positive(text):
                self.detected = True
                self.matched_phrase = m.group(0)
                return
        # Keep a small tail so a phrase spanning two reads is still caught.
        self._tail = buf[-512:]

    @staticmethod
    def _is_false_positive(text: str) -> bool:
        """True if the text is a look-alike (context/fast/server limit), not an
        actual usage/rate-limit interruption."""
        return any(p.search(text) for p in _NON_LIMIT_PATTERNS)


def feed_and_notify(watcher: LimitWatcher, data: bytes, on_detect=None):
    """Feed output and invoke a callback exactly once on first detection."""
    was_detected = watcher.detected
    watcher.feed(data)
    if watcher.detected and not was_detected and on_detect is not None:
        on_detect(watcher)


def sync_window_size(master_fd: int, source_fd: int) -> bool:
    """Copy the real terminal dimensions to the wrapped CLI's PTY."""
    return terminal_backends.sync_window_size(master_fd, source_fd)


def run_wrapped(command, watcher: LimitWatcher, on_detect=None, on_activity=None) -> int:
    """Run the command through the native interactive-terminal backend."""
    return terminal_backends.run_wrapped(command, watcher, on_detect, on_activity)


def fire_handoff(target: str, dry_run: bool, from_cli: str = "auto",
                 new_terminal: bool = False, session_file=None):
    """Reuse handoff.py rather than duplicating capture/redact/launch logic."""
    argv = [sys.executable, str(HERE / "handoff.py"),
            "--to", target, "--from", from_cli]
    if dry_run:
        argv.append("--dry-run")
    if new_terminal:
        argv.append("--new-terminal")
    if session_file is not None:
        argv.extend(["--session-file", str(session_file)])
    return subprocess.run(argv).returncode


def _confirm(question: str, default_yes: bool, auto_yes: bool) -> bool:
    """Ask a yes/no question. Returns True to proceed.

    --yes (auto_yes) or a non-interactive stdin both proceed without prompting,
    so scripts/tests/the demo aren't blocked waiting on input."""
    if auto_yes or not sys.stdin.isatty():
        return True
    suffix = "[Y/n]" if default_yes else "[y/N]"
    try:
        answer = input(f"\n   {question} {suffix} ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    if not answer:
        return default_yes
    return answer in ("y", "yes")


def source_for_command(command_name: str) -> str:
    """Map a wrapped executable name to a Lifeline source key."""
    name = ntpath.basename(command_name)
    path = Path(name)
    from_cli = path.stem if path.suffix.lower() in (".cmd", ".exe", ".bat") else path.name
    return from_cli if from_cli in sources.SUPPORTED_SOURCES else "auto"


def default_target_for_source(from_cli: str) -> str:
    """Deterministic default target for demos, docs, and tests."""
    for target in ("codex", "claude", "gemini"):
        if target != from_cli:
            return target
    return "codex"


def selftest():
    """Verify detection on representative strings without running any CLI."""
    cases = [
        # --- real Claude Code usage-limit signals (should DETECT) ---
        ("Claude usage limit reached ∙ resets in 2h", True),
        ("\x1b[31mClaude usage limit reached\x1b[0m — check plan", True),
        ("/upgrade to increase your usage limit.", True),
        ("You've reached your usage limit for Claude Pro.", True),
        ("5-hour limit reached ∙ resets in 2h", True),
        ("Error: rate limited, try again later", True),
        ("approaching your usage limit", True),
        # --- real Codex usage-limit signals (should DETECT) ---
        ("You've hit your usage limit for GPT-5.", True),
        ("You've hit your usage limit. Upgrade to Pro or try again at 7:26 AM.", True),
        ("stream error: 429 Too Many Requests", True),
        # --- real Gemini usage-limit signals (should DETECT) ---
        ("Usage limit reached for gemini-2.5-pro", True),
        ("Rate limit exceeded. Try again later.", True),
        ("ApiError: status RESOURCE_EXHAUSTED", True),
        # --- look-alikes that must NOT trigger a handoff ---
        ("Context limit reached — use /compact to continue", False),
        ("Fast limit reached and temporarily disabled", False),
        ("Server is temporarily limiting requests (not your usage limit)", False),
        ("Concurrent export limit reached", False),
        ("You've hit your character limit for this field", False),
        # --- ordinary output ---
        ("Compiling project... 42 files, no limit on output here", False),
        ("the rate of growth was high", False),
    ]
    ok = True
    for text, expected in cases:
        w = LimitWatcher()
        # Feed in two chunks to also exercise cross-chunk handling.
        mid = len(text) // 2
        w.feed(text[:mid].encode())
        w.feed(text[mid:].encode())
        result = "DETECT" if w.detected else "clear "
        status = "PASS" if w.detected == expected else "FAIL"
        if w.detected != expected:
            ok = False
        print(f"  [{status}] {result} <- {ascii(text)}"
              + (f"  (matched {ascii(w.matched_phrase)})" if w.detected else ""))
    print("selftest:", "ALL PASS" if ok else "FAILURES")
    return 0 if ok else 1


def main():
    parser = argparse.ArgumentParser(
        description="Wrap an AI CLI and auto-hand off when its usage limit hits."
    )
    parser.add_argument("--to", default=None, choices=sorted(handoff.SUPPORTED_TARGETS),
                        help="Target CLI to hand off to (default: the first of "
                             "codex/claude/gemini that isn't the wrapped CLI).")
    parser.add_argument("--dry-run", action="store_true",
                        help="On detection, build the handoff but don't launch the target CLI.")
    parser.add_argument("-y", "--yes", action="store_true",
                        help="Skip the confirmation prompt and hand off automatically.")
    parser.add_argument("--new-terminal", action="store_true",
                        help="Immediately open the target in a new terminal when "
                             "supported and leave the limited session open.")
    parser.add_argument("--selftest", action="store_true",
                        help="Run detection self-tests and exit.")
    parser.add_argument("command", nargs=argparse.REMAINDER,
                        help="The CLI to wrap (default: claude). Prefix with -- to pass flags.")
    args = parser.parse_args()

    if args.selftest:
        sys.exit(selftest())

    command = args.command
    # Drop a leading "--" separator if argparse left it in.
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        command = ["claude"]

    if shutil.which(command[0]) is None:
        sys.exit(f"Command not found on PATH: {command[0]}")

    # Map the wrapped CLI to a capture source so the handoff reads the RIGHT
    # session (not just whatever was most recent). Unknown CLIs fall back to auto.
    from_cli = source_for_command(command[0])

    # Default the target to the first known CLI that isn't the source, so wrapping
    # e.g. codex doesn't try to hand off codex→codex.
    if args.to is None:
        args.to = default_target_for_source(from_cli)
    elif args.to == from_cli:
        sys.exit(f"Source and target are both '{from_cli}'. Pick a different --to.")
    if shutil.which(args.to) is None:
        sys.exit(
            f"Target CLI '{args.to}' not found on PATH. Install it or choose "
            "a different --to."
        )

    if args.new_terminal and not terminal_launchers.supports_new_terminal():
        print("⚡ Lifeline: immediate new-terminal handoff is unavailable here; falling back "
              "to handoff after the wrapped CLI exits.", file=sys.stderr)
        args.new_terminal = False

    command, _ = session_tracker.prepare_command(from_cli, command)
    tracker = None
    if from_cli in sources.SUPPORTED_SOURCES:
        tracker = session_tracker.SessionTracker(
            from_cli, args.to, command,
            session_tracker.command_cwd(from_cli, command, Path.cwd()),
            session_tracker.ActiveRegistry(),
        )

    watcher = LimitWatcher()
    immediate = {"attempted": False, "success": False}

    def _open_new_terminal(detected_watcher):
        immediate["attempted"] = True
        print("\n" + "=" * 60, file=sys.stderr)
        print(f"⚡ Lifeline: usage limit detected "
              f"(matched {detected_watcher.matched_phrase!r}).", file=sys.stderr)
        print(f"   Opening {args.to} in a new terminal; "
              f"`{command[0]}` will remain open here.", file=sys.stderr)
        print("=" * 60 + "\n", file=sys.stderr)
        try:
            # stdin is still in raw mode inside the PTY callback. If resolution
            # is ambiguous, retry after the wrapped CLI exits so the user can
            # choose from a normal terminal prompt.
            session_file = tracker.require_session(prompt=False) if tracker else None
            immediate["success"] = (
                fire_handoff(
                    args.to, args.dry_run, from_cli, new_terminal=True,
                    session_file=session_file,
                ) == 0
            )
        except (RuntimeError, session_tracker.AmbiguousSessionError) as e:
            print(f"⚡ Lifeline: {e}", file=sys.stderr)
            immediate["success"] = False
        if not immediate["success"]:
            print("⚡ Lifeline: new-terminal handoff failed. It will retry after "
                  "this session exits.", file=sys.stderr)

    print(f"⚡ Lifeline watching `{command[0]}` for usage limits "
          f"(handoff target: {args.to})\n", file=sys.stderr)
    print(f"   Protection active. If `{command[0]}` hits its usage limit, "
          f"Lifeline will hand this exact session to {args.to}.", file=sys.stderr)
    print(f"   To switch manually, open another terminal and run "
          f"`lifeline switch {args.to}`. Do not type it into the AI prompt.\n",
          file=sys.stderr)

    try:
        exit_code = run_wrapped(
            command,
            watcher,
            on_detect=_open_new_terminal if args.new_terminal else None,
            on_activity=tracker.observe if tracker else None,
        )
    finally:
        if tracker:
            tracker.observe(force=True)

    if not watcher.detected:
        print(f"\n⚡ Lifeline: `{command[0]}` exited without hitting a limit. "
              f"No handoff needed.", file=sys.stderr)
        if tracker:
            tracker.close()
        sys.exit(exit_code)

    if immediate["success"]:
        if args.dry_run:
            print("\n⚡ Lifeline: immediate handoff dry run completed. "
                  "No second handoff needed.", file=sys.stderr)
        else:
            print(f"\n⚡ Lifeline: {args.to} was already opened in a new terminal. "
                  f"No second handoff needed.", file=sys.stderr)
        if tracker:
            tracker.close()
        sys.exit(exit_code)

    # A usage limit was seen during the session. Make it obvious what happened,
    # then confirm before launching — the user may have waited out the limit and
    # kept working, in which case they don't want a handoff.
    print("\n" + "=" * 60, file=sys.stderr)
    print(f"⚡ Lifeline: a usage limit was detected during this session "
          f"(matched {watcher.matched_phrase!r}).", file=sys.stderr)
    print(f"   Lifeline can resume your work in {args.to} with full context.",
          file=sys.stderr)
    print("=" * 60, file=sys.stderr)

    if not _confirm(f"Resume in {args.to} now?", default_yes=True,
                    auto_yes=args.yes):
        print(f"\n   Skipped. Run `lifeline handoff --to {args.to}` later "
              f"to resume whenever you want.", file=sys.stderr)
        if tracker:
            tracker.close()
        sys.exit(exit_code)

    print(f"\n   Capturing context and handing off to {args.to}…\n", file=sys.stderr)
    try:
        session_file = tracker.require_session() if tracker else None
        result = fire_handoff(args.to, args.dry_run, from_cli, session_file=session_file)
    except (RuntimeError, session_tracker.AmbiguousSessionError) as e:
        sys.exit(f"Exact session selection failed: {e}")
    finally:
        if tracker:
            tracker.close()
    sys.exit(result)


if __name__ == "__main__":
    main()
