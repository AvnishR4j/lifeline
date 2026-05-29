#!/usr/bin/env bash
# Lifeline demo runner — gives a clean, repeatable 30-second recording in one take.
#
#   bash demo-run.sh           # auto-detection story (wrap -> limit -> handoff)
#   bash demo-run.sh manual    # manual story (one command after a limit)
#
# Records best on a large font, dark terminal. Clears old handoffs first so only
# the fresh one appears on screen.

set -e
cd "$(dirname "$0")"
rm -f .lifeline/*.md 2>/dev/null || true

pause() { sleep "${1:-1.5}"; }
say()   { printf "\n\033[1;36m# %s\033[0m\n" "$1"; }

if [ "$1" = "manual" ]; then
  say "I'm deep in a Claude Code session... and I just hit my usage limit."
  pause 2
  say "One command resumes everything in Codex — zero re-explanation:"
  pause 1
  echo "\$ python3 handoff.py --to codex"
  pause 1
  python3 handoff.py --to codex
else
  say "I run Claude through Lifeline so it can catch a usage limit for me:"
  pause 1
  echo "\$ python3 watch.py --to codex -- <your real claude session>"
  pause 2
  say "Simulating the moment the limit hits mid-task:"
  pause 1
  python3 watch.py --to codex -y -- bash -c \
    "echo 'Editing payment-retry.py — fixing the backoff logic...'; sleep 1; echo; echo 'Claude usage limit reached ∙ resets in 2h'"
fi
