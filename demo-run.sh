#!/usr/bin/env bash
# Lifeline demo runner — gives a clean, repeatable 30-second recording in one take.
#
#   bash demo-run.sh           # auto-detection story (wrap -> limit -> handoff)
#   bash demo-run.sh manual    # manual story (one command after a limit)
#
# Records best on a large font, dark terminal.

set -e
cd "$(dirname "$0")"

pause() { sleep "${1:-1.5}"; }
say()   { printf "\n\033[1;36m# %s\033[0m\n" "$1"; }

if [ "$1" = "manual" ]; then
  say "I'm deep in a Claude Code session... and I just hit my usage limit."
  pause 2
  say "One command resumes everything in Codex — zero re-explanation:"
  pause 1
  echo "\$ lifeline handoff --to codex"
  pause 1
  lifeline handoff --to codex
else
  say "I run Claude through Lifeline so it can catch a usage limit for me:"
  pause 1
  echo "\$ lifeline claude --to codex"
  pause 2
  say "Simulating the moment the limit hits mid-task:"
  pause 1
  lifeline watch --to codex -- bash -c \
    "echo 'Editing payment-retry.py — fixing the backoff logic...'; sleep 1; echo; echo 'Claude usage limit reached ∙ resets in 2h'"
fi
