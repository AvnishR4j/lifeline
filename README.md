# Lifeline

> When your AI hits its limit, your work shouldn't.

When an AI coding CLI (Claude Code, Codex, Gemini, …) hits its usage limit
mid-task, you're forced to switch tools — and lose all context. Lifeline captures
the state of the interrupted session and lets you resume in a different CLI with a
single command, **zero re-explanation**.

It targets the *involuntary interruption* moment: not a manual switch you chose,
but the forced one when the limit hits.

## Demo

▶️ **[Watch the 30-second demo](https://github.com/AvnishR4j/lifeline/blob/main/lifeline-demo.mp4)**
— Claude Code hits a usage limit, and Lifeline resumes the work in Codex with full
context, zero re-explanation.

<!-- To make the video autoplay inline here instead of as a link: open this README
     in GitHub's web editor (the pencil icon), drag `lifeline-demo.mp4` into the
     editor at this spot — GitHub uploads it and inserts a player URL that embeds
     inline — then commit. -->

## Usage

### Automatic (recommended)

Wrap your AI CLI. Lifeline watches its output and, the moment a usage limit
appears, hands your context off to another CLI when the session ends — you don't
have to remember to run anything.

```bash
python3 watch.py                 # wraps `claude`, hands off to codex on a limit
python3 watch.py --to codex      # explicit target
python3 watch.py --to gemini     # hand off to Gemini CLI instead
python3 watch.py -- claude --foo # pass extra flags through to the wrapped CLI
```

### Manual

Run the handoff yourself when a limit hits:

```bash
python3 handoff.py --to codex     # or: --to gemini

# Preview what would be sent without launching anything:
python3 handoff.py --to codex --dry-run
```

Supported targets: `codex`, `gemini`. (Gemini uses `gemini -i "<prompt>"`; verify
the flag against your installed `@google/gemini-cli` version.)

This will:
1. Find your most recent Claude Code session (`~/.claude/projects/`).
2. Extract the task, recent conversation, last prompt, and uncommitted `git diff`.
3. **Redact secrets** (see below) and warn you about what was scrubbed.
4. Write a secret-safe handoff file to `.lifeline/` (gitignored, `0600`).
5. Launch the target CLI seeded with that context.

## How it works

| File | Role |
|------|------|
| `watch.py` | Wraps an AI CLI in a PTY, watches output for a usage limit, auto-fires the handoff. |
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

- **One-directional**: Lifeline currently only captures **Claude Code** as the
  source (it reads `~/.claude/projects/*.jsonl`). The reverse — e.g. resuming a
  rate-limited *Codex* session in Claude — is not yet supported (see roadmap).
- **Prompt injection**: session content is wrapped and labeled as historical
  context, but a determined injection inside the session could still influence the
  resuming CLI. Acceptable for v0 since the session is your own.
- Redaction is pattern-based; novel secret formats may slip through. Review the
  `--dry-run` output for anything sensitive before a real handoff.

## Roadmap

- **Bidirectional / any→any handoff.** Today capture is Claude-specific. Make the
  source pluggable via a "source registry" mirroring the existing `TARGETS`
  registry in `handoff.py`, so any CLI can be the source *or* the destination
  (e.g. Codex→Claude when Codex hits its limit). Needed pieces: a reader per CLI
  (Codex already stores history at `~/.codex/sessions/.../rollout-*.jsonl`;
  Gemini stores its own), registering `claude`/`gemini` as launch targets, each
  CLI's real limit-message string, and a `--from <cli>` flag to select the reader.
- More targets: `cursor`, and others.
- Packaging as an installable CLI.
