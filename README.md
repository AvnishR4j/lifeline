

https://github.com/user-attachments/assets/ad48a1b8-0ae7-4553-b266-0f4794500085

# Lifeline

> When your AI hits its limit, your work shouldn't.

When an AI coding CLI (Claude Code, Codex, Gemini, …) hits its usage limit
mid-task, you're forced to switch tools — and lose all context. Lifeline captures
the state of the interrupted session and lets you resume in a different CLI with a
single command, **zero re-explanation**.

It targets the *involuntary interruption* moment: not a manual switch you chose,
but the forced one when the limit hits.

_30-second demo above: Claude Code hits a usage limit, and Lifeline resumes the
work in Codex with full context, zero re-explanation._

## Requirements

- **OS:** macOS or Linux. (Windows isn't supported yet — the auto-detect wrapper
  uses Unix PTYs.)
- **Python 3.8+** — no third-party packages, pure standard library.
- **The source CLI:** [Claude Code](https://docs.anthropic.com/en/docs/claude-code)
  (Lifeline reads its local session files under `~/.claude/projects/`).
- **At least one target CLI, installed _and_ authenticated:**
  - [Codex CLI](https://github.com/openai/codex) — `codex login`
  - and/or [Gemini CLI](https://github.com/google-gemini/gemini-cli) — `gemini` (sign in once)

  If your target isn't logged in, the handoff will launch it but you'll just land
  on its login screen — so authenticate it first.

## Quickstart

```bash
# Install (pure Python, no dependencies)
pipx install git+https://github.com/AvnishR4j/lifeline.git
# or: pip install git+https://github.com/AvnishR4j/lifeline.git

# Manual: after Claude Code hits a limit, resume in Codex with full context
lifeline handoff --to codex          # or --to gemini

# Preview exactly what would be sent first (nothing is launched):
lifeline handoff --to codex --dry-run
```

For the **automatic** experience, start Claude Code through Lifeline instead of
launching `claude` directly (see Usage below).

> Prefer not to install? It's pure standard library — `git clone` and run the
> scripts directly (`python3 handoff.py …` / `python3 watch.py …`).

## Usage

### Automatic (recommended)

Wrap your AI CLI. Lifeline watches its output and, the moment a usage limit
appears, hands your context off to another CLI when the session ends — you don't
have to remember to run anything.

```bash
lifeline watch                 # wraps `claude`, hands off to codex on a limit
lifeline watch --to codex      # explicit target
lifeline watch --to gemini     # hand off to Gemini CLI instead
lifeline watch -- claude --foo # pass extra flags through to the wrapped CLI
```

### Manual

Run the handoff yourself when a limit hits:

```bash
lifeline handoff --to codex     # or: --to gemini, --to claude

# By default Lifeline auto-detects the source CLI (whichever you used most
# recently). Pin it explicitly with --from:
lifeline handoff --from codex --to claude    # Codex hit its limit → resume in Claude
lifeline handoff --from claude --to gemini   # Claude hit its limit → resume in Gemini

# Preview what would be sent without launching anything:
lifeline handoff --to codex --dry-run
```

**Sources** (capture *from*, via `--from`): `claude`, `codex` (default: `auto`).
**Targets** (resume *in*, via `--to`): `codex`, `gemini`, `claude`.
(Gemini uses `gemini -i "<prompt>"`; verify the flag against your installed
`@google/gemini-cli` version.)

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
| `sources.py` | Registry of CLIs Lifeline can capture *from*; auto-detects the most recent session. |
| `extractor.py` | Reads the latest Claude session JSONL → normalized handoff data + renderer. |
| `codex_reader.py` | Reads the latest Codex `rollout-*.jsonl` session into the same normalized shape. |
| `redact.py` | Scrubs secrets from text before it leaves the machine. |
| `handoff.py` | Orchestrates select source → capture → redact → write → launch target CLI. |

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

- **Source coverage**: Lifeline can capture from **Claude Code** and **Codex**
  today (both directions work, e.g. Codex→Claude). **Gemini** as a *source* is not
  yet supported — it can only be a target for now (see roadmap).
- **Prompt injection**: session content is wrapped and labeled as historical
  context, but a determined injection inside the session could still influence the
  resuming CLI. Acceptable for v0 since the session is your own.
- Redaction is pattern-based; novel secret formats may slip through. Review the
  `--dry-run` output for anything sensitive before a real handoff.

## Roadmap

- **Any→any handoff.** ✅ The source is now pluggable via a `sources.py` registry
  and a `--from` flag, with `claude` and `codex` readers and `claude` registered
  as a launch target — so Codex→Claude works. **Remaining:** a **Gemini source
  reader** (so Gemini can be captured *from*, not just handed off *to*), and
  teaching `watch.py` each CLI's real limit-message string so auto-detection works
  when wrapping a non-Claude CLI.
- More targets: `cursor`, and others.
