# Lifeline — 30-second demo script

Goal: show Claude Code hitting a limit and Codex resuming with full context,
zero re-explanation. Record with QuickTime (Cmd+Shift+5) or `asciinema`.

## Setup (before recording)

- One terminal window, large readable font, dark theme.
- Be inside a small real project so the `git diff` capture has something to show.
- Have Codex logged in (`codex login status` → "Logged in").
- Close other noisy apps; clean prompt.

## The shot list (~30s)

**[0–5s] The setup — show the pain.**
Have a Claude Code session mid-task on screen. On-screen caption:
> "90 minutes into debugging. Then…"

**[5–10s] The interruption.**
The limit message appears:
```
Usage limit reached. Resets at 2pm.
```
Caption: "Normally: switch tools, lose everything, re-explain for 15 minutes."

**[10–13s] One command.**
Type and run:
```bash
python3 ~/lifeline/handoff.py --to codex
```
Caption: "With Lifeline: one command."

**[13–20s] The magic — Codex wakes up knowing everything.**
Codex opens and immediately states the task, what was done, and the next step —
without being told. Let the viewer read it.
Caption: "Codex resumes — zero re-explanation."

**[20–27s] The trust beat (your differentiator).**
Point at the `⚠ Redacted N secrets` line / show that the API key in the session
became `[REDACTED:openai-key]`.
Caption: "Your secrets never leave your machine."

**[27–30s] The close.**
Full-screen text:
> **Lifeline — when your AI hits its limit, your work shouldn't.**
> github.com/AvnishR4j/lifeline

## Tighter alternative (fully automatic)

For an even stronger version, wrap Claude so nothing is typed at all:
```bash
python3 ~/lifeline/watch.py --to codex
```
…work until the limit hits, and the handoff fires by itself. Caption:
"You don't even run a command. Lifeline catches the limit for you."

## Tips

- Pre-write the synthetic-secret line into your session so the redaction beat
  has something concrete to show.
- Keep captions short; the demo should be legible at 2x speed.
- Export at 1080p; trim dead air ruthlessly — every second past 30 loses people.
