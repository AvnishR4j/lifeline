# Changelog

## 0.2.1

- Fixed native Windows ConPTY keyboard input by sending text values to
  `pywinpty` instead of unsupported byte strings.
- Stopped injecting the removed Gemini CLI `--session-id` argument and preserved
  exact-session discovery through the newly created transcript and workspace.
- Made Claude, Codex, and Gemini transcript readers tolerate Windows encoding
  differences and malformed bytes.
- Added Windows workspace-path parsing for Gemini sessions.

## 0.2.0 - Public Beta

- Added bidirectional Claude Code, Codex, and Gemini handoffs.
- Added exact session tracking and live protected-session switching.
- Resumed targets now stay under Lifeline protection and start in the captured
  project directory.
- Added immediate new-terminal handoffs on macOS and native Windows.
- Added native Windows ConPTY support through a Windows-only `pywinpty` dependency.
- Pinned native Windows support to the compatible `pywinpty` 2.x line.
- Windows npm command shims now use their PowerShell companions to preserve
  arbitrary handoff text and reject unsafe batch-only launch paths.
- Added Linux and WSL fallback behavior.
- Added diagnostics, expanded secret redaction, secret-safe handoff storage,
  packaging, and reliability tests.

## 0.1.0

- Initial Claude Code to Codex handoff demo.
