# Lifeline

> When your AI hits its limit, your work shouldn't.

When an AI coding CLI (Claude Code, Codex, Gemini, …) hits its usage limit
mid-task, you're forced to switch tools — and lose all context. Lifeline captures
the state of the interrupted session and lets you resume in a different CLI with a
single command, **zero re-explanation**.

It targets the *involuntary interruption* moment: not a manual switch you chose,
but the forced one when the limit hits.

## Usage

```bash
# When Claude Code hits its limit, resume in Codex:
python3 handoff.py --to codex

# Preview what would be sent without launching anything:
python3 handoff.py --to codex --dry-run
```

This will:
1. Find your most recent Claude Code session (`~/.claude/projects/`).
2. Extract the task, recent conversation, last prompt, and uncommitted `git diff`.
3. **Redact secrets** (see below) and warn you about what was scrubbed.
4. Write a secret-safe handoff file to `.lifeline/` (gitignored, `0600`).
5. Launch the target CLI seeded with that context.

## How it works

| File | Role |
|------|------|
| `extractor.py` | Reads the latest Claude session JSONL → structured markdown handoff. |
| `redact.py` | Scrubs secrets from text before it leaves the machine. |
| `handoff.py` | Orchestrates capture → redact → write → launch target CLI. |

## Security model

The handoff ships session content to another AI provider, so:

- **Secret redaction** — `redact.py` scans for OpenAI/GitHub/AWS/Google/Slack
  keys, Bearer tokens, PEM private keys, and `.env`-style secret assignments, and
  replaces them with `[REDACTED:<kind>]`. It runs locally (regex only, no network,
  no cost) and prints a summary of what was redacted before launch.
- **No command injection** — the target CLI is launched with an argv list
  (`subprocess.run([...])`), never a shell string. The full handoff goes into a
  file, not a CLI argument (avoids `ARG_MAX` and leaking into `ps`).
- **Restrictive perms** — handoff files are written `0600` in a `0700` directory,
  and `.lifeline/` is gitignored so handoffs are never committed.
- **Path safety** — `--project-dir` is validated to live under
  `~/.claude/projects`.

### Known limitations (v0)

- **Prompt injection**: session content is wrapped and labeled as historical
  context, but a determined injection inside the session could still influence the
  resuming CLI. Acceptable for v0 since the session is your own.
- Redaction is pattern-based; novel secret formats may slip through. Review the
  `--dry-run` output for anything sensitive before a real handoff.

## Roadmap

- Auto-detection: wrap the CLI and fire on "Usage limit reached" automatically.
- More targets: `gemini`, `cursor`.
- Packaging as an installable CLI.
