# Lifeline

> When your AI hits its limit, your work shouldn't.

[![CI](https://github.com/AvnishR4j/lifeline/actions/workflows/ci.yml/badge.svg)](https://github.com/AvnishR4j/lifeline/actions/workflows/ci.yml)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-3776AB)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**v0.2.0 public beta** — macOS is the primary supported platform. Native
Windows, Linux, and WSL are beta-supported.

Lifeline runs Claude Code, Codex, or Gemini under protection. When the active AI
hits its usage limit, Lifeline captures that exact session and opens another AI
with the useful context already loaded.

```text
lifeline codex
      │
      ├── Codex works normally
      │
      ├── Codex hits its usage limit
      │
      └── Lifeline opens Claude or Gemini with the same context
```

No re-explanation. No guessing which session you meant. The original session
stays available.

https://github.com/user-attachments/assets/ad48a1b8-0ae7-4553-b266-0f4794500085

## The Important Rule

Start the AI from a **normal terminal** using Lifeline:

```bash
lifeline codex
```

Do not launch plain `codex` and expect Lifeline to detect its limit. Lifeline can
only automatically watch sessions that were started with `lifeline claude`,
`lifeline codex`, or `lifeline gemini`.

Also, do not type `lifeline switch ...` into an AI chat prompt. Run manual switch
commands from a **second normal terminal window or tab**.

## Use Lifeline In Three Steps

### 1. Start a protected session

```bash
lifeline codex
```

Lifeline asks where it should hand the session over if Codex reaches its limit:

```text
Start Codex under Lifeline protection.
When Codex hits its limit, switch to:
  1. Claude (default)
  2. Gemini
Choose [1-2] (default 1):
```

### 2. Work normally

Use Codex, Claude, or Gemini exactly as usual. Lifeline watches in the background
and tracks the exact transcript belonging to this protected launch.

You should see:

```text
⚡ Lifeline watching `codex` for usage limits (handoff target: claude)
   Protection active.
```

If that message was not shown when the AI started, the session is not protected.

### 3. Let Lifeline switch automatically

When Lifeline sees a real usage-limit message, it captures the exact protected
session and opens the selected target with its context. The target starts in the
captured project directory and remains protected, so a later limit can hand the
work back again.

You can also switch before the limit. Open another normal terminal and run:

```bash
lifeline switch claude
```

## Install And Run On Your Computer

### macOS

Requirements: Python 3.9+, and at least two authenticated supported AI CLIs.

```bash
# Install Lifeline directly from GitHub
python3 -m pip install --user --upgrade git+https://github.com/AvnishR4j/lifeline.git

# Confirm your setup
lifeline doctor

# Start a protected AI session
lifeline codex
```

If `lifeline` is not found after installation, add your user Python scripts
directory to `PATH`, then restart Terminal:

```bash
echo 'export PATH="$HOME/.local/bin:$HOME/Library/Python/3.9/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

On macOS, Lifeline opens the target in a new Terminal.app window while keeping
the limited session open. The resumed target remains under Lifeline protection.

### Windows

Use PowerShell or cmd. Python 3.9+ is required. Windows Terminal is recommended.

```powershell
py -m pip install --upgrade git+https://github.com/AvnishR4j/lifeline.git
lifeline doctor
lifeline codex
```

Native Windows automatically installs `pywinpty` for interactive ConPTY support.
For immediate handoffs, Lifeline tries Windows Terminal, PowerShell, then cmd.
Git Bash is best-effort.

### Linux

```bash
python3 -m pip install --user --upgrade git+https://github.com/AvnishR4j/lifeline.git
lifeline doctor
lifeline codex
```

On Linux, Lifeline watches the protected session and performs the handoff after
the limited CLI exits.

### WSL

Install and run Lifeline inside WSL using the Linux commands:

```bash
python3 -m pip install --user --upgrade git+https://github.com/AvnishR4j/lifeline.git
lifeline doctor
lifeline codex
```

WSL uses the Unix PTY backend. Native Windows and WSL sessions remain separate.

## Supported AI Tools

Install and authenticate at least two:

| CLI | Command | Login |
|---|---|---|
| [Claude Code](https://docs.anthropic.com/en/docs/claude-code) | `claude` | Follow Claude Code sign-in |
| [Codex CLI](https://github.com/openai/codex) | `codex` | `codex login` |
| [Gemini CLI](https://github.com/google-gemini/gemini-cli) | `gemini` | Run `gemini` and sign in |

All six directions are supported:

```text
Claude → Codex     Claude → Gemini
Codex  → Claude    Codex  → Gemini
Gemini → Claude    Gemini → Codex
```

## Commands You Will Use

```bash
# Start protected sessions
lifeline claude
lifeline codex
lifeline gemini

# Choose the fallback without being asked
lifeline codex --to gemini

# Switch a currently protected session from another terminal
lifeline switch claude

# Check installation, backends, CLIs, and transcript parsing
lifeline doctor

# Preview a manual handoff without launching the target
lifeline handoff --from codex --to gemini --dry-run
```

Other AI CLI arguments pass through:

```bash
lifeline claude --to gemini --model opus
```

The friendly launcher reserves `--to` for Lifeline. Put a literal underlying CLI
`--to` option after `--`:

```bash
lifeline codex --to gemini -- --to some-codex-value
```

## Why Did Lifeline Not Switch?

If the AI displays a usage limit but nothing happens:

1. Check whether the session was started with `lifeline codex`, `lifeline
   claude`, or `lifeline gemini`.
2. Look for the `⚡ Lifeline watching ...` startup message.
3. Run `lifeline doctor` from a normal terminal.
4. If the session was started directly, use a manual handoff:

```bash
lifeline handoff --from codex --to claude
```

Manual `lifeline switch` only sees sessions started under Lifeline protection.

## Advanced Usage

Use the full commands when you need an explicit source, target, dry run, or
confirmation behavior:

```bash
lifeline watch --to gemini -- claude
lifeline watch --yes --to codex -- claude
lifeline watch --new-terminal --to codex -- claude
lifeline handoff --from codex --to gemini --dry-run
lifeline handoff --from codex --to gemini --session-file ~/.codex/sessions/...jsonl
```

Explicit `--from` is the most reliable bidirectional manual form:

```bash
lifeline handoff --from claude --to codex
lifeline handoff --from claude --to gemini
lifeline handoff --from codex --to claude
lifeline handoff --from codex --to gemini
lifeline handoff --from gemini --to claude
lifeline handoff --from gemini --to codex

# Auto-detect is convenient, but explicit --from avoids ambiguity:
lifeline handoff --to codex

# Preview what would be sent without launching anything:
lifeline handoff --from codex --to gemini --dry-run
```

**Sources** (capture *from*, via `--from`): `claude`, `codex`, `gemini` (default: `auto`).
**Targets** (resume *in*, via `--to`): `codex`, `gemini`, `claude`.
(Gemini uses `gemini -i "<prompt>"`; verify the flag against your installed
`@google/gemini-cli` version.)

This will:
1. Resolve the selected source CLI session (Claude Code, Codex, or Gemini).
2. Extract the task, recent conversation, last prompt, and uncommitted `git diff`.
3. **Redact secrets** (see below) and warn you about what was scrubbed.
4. Write a secret-safe handoff file to `~/.lifeline/handoffs/`.
5. Launch the target CLI seeded with that context, in the captured project
   directory and under continued Lifeline protection when the source CLI is
   still installed.

### Diagnostics

```bash
lifeline doctor
```

`doctor` checks which supported CLIs are on `PATH`, whether each session root
exists, whether the latest session for each source can be parsed, and prints the
supported source→target matrix. Use it first if a specific direction such as
Codex→Claude or Gemini→Codex is not working.

## How it works

| File | Role |
|------|------|
| `watch.py` | Wraps an AI CLI in a PTY, watches output for a usage limit, auto-fires the handoff. |
| `terminal_backends.py` | Runs protected sessions through Unix PTY or native Windows ConPTY. |
| `terminal_launchers.py` | Opens immediate handoffs through Terminal.app or Windows Terminal/PowerShell/cmd. |
| `session_tracker.py` | Pins protected launches to exact transcripts and maintains the live-session registry used by `lifeline switch`. |
| `sources.py` | Registry of CLIs Lifeline can capture *from*; auto-detects the most recent session. |
| `extractor.py` | Reads the latest Claude session JSONL → normalized handoff data + renderer. |
| `codex_reader.py` | Reads the latest Codex `rollout-*.jsonl` session into the same normalized shape. |
| `gemini_reader.py` | Reads the latest Gemini chat session (`~/.gemini/tmp/*/chats/`) into the same shape. |
| `redact.py` | Scrubs secrets from text before it leaves the machine. |
| `handoff.py` | Orchestrates select source → capture → redact → write → launch target CLI. |

## Security model

The handoff ships session content to another AI provider, so:

- **Secret redaction** — `redact.py` scans for OpenAI/GitHub/AWS/Google/Slack
  keys, common service tokens, JWTs, credentials embedded in URLs, Bearer
  tokens, PEM private keys, and `.env`-style secret assignments, and replaces
  them with `[REDACTED:<kind>]`. It runs locally (regex only, no network, no
  cost) and prints a summary of what was redacted before launch.
- **Safe process launch** — native executables receive argv lists directly.
  Windows npm `.cmd` shims are replaced with their PowerShell companions so
  handoff text stays data instead of being re-parsed by a batch shell. Lifeline
  rejects batch-only targets that cannot safely preserve arbitrary context.
- **Private local storage** — handoff files live under
  `~/.lifeline/handoffs/`. Unix uses `0600` files in `0700` directories;
  Windows relies on the current user's profile-directory access controls.
- **Path safety** — `--project-dir` is validated to live under the selected
  source CLI's session root. Exact `--session-file` paths receive the same
  validation.
- **Metadata-only active registry** — live protected sessions are recorded under
  `~/.lifeline/active/` using `0700`/`0600` permissions. Records contain source,
  target, working directory, PID, session ID/path, and status; they do not copy
  transcript content.

### Known limitations (v0)

- **Beta support**: native Windows, Linux, and WSL are public-beta platforms.
  PowerShell and cmd are tested on Windows; Git Bash is best-effort.
- **Source coverage**: Lifeline can capture from **Claude Code**, **Codex**, and
  **Gemini** — all three work as both source and target (e.g. Codex→Claude,
  Gemini→Claude). Other CLIs (Cursor, …) are not yet supported (see roadmap).
- **Prompt injection**: session content is wrapped and labeled as historical
  context, but a determined injection inside the session could still influence the
  resuming CLI. Acceptable for v0 since the session is your own.
- The redacted inline handoff may be temporarily visible to local process-list
  inspection tools while the target CLI starts.
- Manual `lifeline switch` only targets live sessions launched under Lifeline.
  Advanced `lifeline handoff` retains latest-session discovery for unprotected
  sessions, so use explicit `--from` and `--session-file` when exact selection is
  required there.
- Redaction is pattern-based; novel secret formats may slip through. Review the
  `--dry-run` output for anything sensitive before a real handoff.

## Troubleshooting

Run `lifeline doctor` first. It reports the selected terminal backend, target CLI
paths, session roots, parser health, and native Windows `pywinpty` availability.

On Windows, reinstall with `py -m pip install --upgrade --force-reinstall
lifeline` if ConPTY support is missing. If immediate handoff cannot open a new
terminal, the generated handoff remains under `~/.lifeline/handoffs/` and the
error includes the next action.

Uninstall with `pipx uninstall lifeline` or `py -m pip uninstall lifeline`.

## Roadmap

- **Any→any handoff.** ✅ The source is pluggable via a `sources.py` registry and
  a `--from` flag, with `claude`, `codex`, and `gemini` readers all registered as
  launch targets — so any pair works (Codex→Claude, Gemini→Claude, …). The
  auto-detect wrapper (`watch.py`) recognizes all three CLIs' real limit messages
  and wires the wrapped CLI through as the capture source.
- More sources/targets: `cursor`, and others.
