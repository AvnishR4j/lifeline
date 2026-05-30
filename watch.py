#!/usr/bin/env python3
"""
Lifeline — auto-detection wrapper.

Runs an AI CLI (default: `claude`) inside a pseudo-terminal (PTY) so it stays
fully interactive, while Lifeline watches its output for a usage-limit message.
When the limit is detected, Lifeline fires the handoff automatically once the
wrapped session ends — so you resume in another CLI with full context, without
having to remember to run anything.

    python3 watch.py                 # wrap `claude`, hand off to codex on limit
    python3 watch.py --to codex      # explicit target
    python3 watch.py -- claude --foo # pass args through to the wrapped CLI
    python3 watch.py --selftest      # verify detection patterns, run nothing
"""

import argparse
import os
import pty
import re
import select
import shutil
import subprocess
import sys
import termios
import tty
from pathlib import Path

import handoff  # for SUPPORTED_TARGETS so --to is validated up front
import sources  # to map the wrapped CLI to a capture source

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


def run_wrapped(command, watcher: LimitWatcher) -> int:
    """Run `command` inside a PTY, mirroring output while feeding the watcher.
    Returns the child's exit status.

    We implement the relay manually (rather than pty.spawn) so we can:
      - feed every output chunk to the watcher, and
      - only forward stdin when stdin is a real TTY. pty.spawn busy-hangs when
        stdin is /dev/null or a pipe (non-interactive shells, CI, tests)."""
    pid, master_fd = pty.fork()
    if pid == 0:
        # Child: become the wrapped CLI.
        os.execvp(command[0], command)
        os._exit(127)  # only reached if exec fails

    stdin_fd = sys.stdin.fileno()
    stdin_is_tty = sys.stdin.isatty()
    saved = None
    if stdin_is_tty:
        # Raw mode so keystrokes pass straight through to the child's PTY.
        saved = termios.tcgetattr(stdin_fd)
        tty.setraw(stdin_fd)

    try:
        while True:
            watch_fds = [master_fd] + ([stdin_fd] if stdin_is_tty else [])
            try:
                rlist, _, _ = select.select(watch_fds, [], [])
            except (OSError, ValueError):
                break

            if master_fd in rlist:
                try:
                    data = os.read(master_fd, 1024)
                except OSError:
                    data = b""
                if not data:
                    break  # child closed the PTY -> it exited
                watcher.feed(data)
                os.write(sys.stdout.fileno(), data)

            if stdin_is_tty and stdin_fd in rlist:
                data = os.read(stdin_fd, 1024)
                if data:
                    os.write(master_fd, data)
    finally:
        if saved is not None:
            termios.tcsetattr(stdin_fd, termios.TCSAFLUSH, saved)
        os.close(master_fd)

    _, status = os.waitpid(pid, 0)
    if os.WIFEXITED(status):
        return os.WEXITSTATUS(status)
    if os.WIFSIGNALED(status):
        return 128 + os.WTERMSIG(status)
    return status


def fire_handoff(target: str, dry_run: bool, from_cli: str = "auto"):
    """Reuse handoff.py rather than duplicating capture/redact/launch logic."""
    argv = [sys.executable, str(HERE / "handoff.py"),
            "--to", target, "--from", from_cli]
    if dry_run:
        argv.append("--dry-run")
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
        print(f"  [{status}] {result} <- {text!r}"
              + (f"  (matched {w.matched_phrase!r})" if w.detected else ""))
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
    from_cli = Path(command[0]).name
    if from_cli not in sources.SUPPORTED_SOURCES:
        from_cli = "auto"

    # Default the target to the first known CLI that isn't the source, so wrapping
    # e.g. codex doesn't try to hand off codex→codex.
    if args.to is None:
        args.to = next(t for t in ("codex", "claude", "gemini") if t != from_cli)

    watcher = LimitWatcher()
    print(f"⚡ Lifeline watching `{command[0]}` for usage limits "
          f"(handoff target: {args.to})\n", file=sys.stderr)

    exit_code = run_wrapped(command, watcher)

    if not watcher.detected:
        print(f"\n⚡ Lifeline: `{command[0]}` exited without hitting a limit. "
              f"No handoff needed.", file=sys.stderr)
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
        sys.exit(exit_code)

    print(f"\n   Capturing context and handing off to {args.to}…\n", file=sys.stderr)
    sys.exit(fire_handoff(args.to, args.dry_run, from_cli))


if __name__ == "__main__":
    main()
