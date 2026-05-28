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

HERE = Path(__file__).resolve().parent

# Strip ANSI escape sequences before matching, so colored TUI output doesn't
# hide the limit message.
ANSI_RE = re.compile(rb"\x1b\[[0-9;?]*[ -/]*[@-~]")

# Phrases that signal an involuntary usage/rate-limit interruption. Kept
# reasonably specific to avoid false positives on ordinary output.
LIMIT_PATTERNS = [
    re.compile(r"usage limit reached", re.I),
    re.compile(r"you'?ve reached your usage limit", re.I),
    re.compile(r"rate limit(?:ed| reached| exceeded)", re.I),
    re.compile(r"\blimit reached\b", re.I),
    re.compile(r"resets? at\b", re.I),
    re.compile(r"approaching .* usage limit", re.I),
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
            if m:
                self.detected = True
                self.matched_phrase = m.group(0)
                return
        # Keep a small tail so a phrase spanning two reads is still caught.
        self._tail = buf[-512:]


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


def fire_handoff(target: str, dry_run: bool):
    """Reuse handoff.py rather than duplicating capture/redact/launch logic."""
    argv = [sys.executable, str(HERE / "handoff.py"), "--to", target]
    if dry_run:
        argv.append("--dry-run")
    return subprocess.run(argv).returncode


def selftest():
    """Verify detection on representative strings without running any CLI."""
    cases = [
        ("Usage limit reached. Resets at 2pm.", True),
        ("\x1b[31mYou've reached your usage limit\x1b[0m for Claude Pro.", True),
        ("Error: rate limited, try again later", True),
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
    parser.add_argument("--to", default="codex",
                        help="Target CLI to hand off to (default: codex).")
    parser.add_argument("--dry-run", action="store_true",
                        help="On detection, build the handoff but don't launch the target CLI.")
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

    watcher = LimitWatcher()
    print(f"⚡ Lifeline watching `{command[0]}` for usage limits "
          f"(handoff target: {args.to})\n", file=sys.stderr)

    exit_code = run_wrapped(command, watcher)

    if watcher.detected:
        print("\n" + "=" * 60, file=sys.stderr)
        print(f"⚡ Lifeline: usage limit detected "
              f"(matched {watcher.matched_phrase!r}).", file=sys.stderr)
        print(f"   Capturing context and handing off to {args.to}…", file=sys.stderr)
        print("=" * 60 + "\n", file=sys.stderr)
        sys.exit(fire_handoff(args.to, args.dry_run))
    else:
        print(f"\n⚡ Lifeline: `{command[0]}` exited without hitting a limit. "
              f"No handoff needed.", file=sys.stderr)
        sys.exit(exit_code)


if __name__ == "__main__":
    main()
