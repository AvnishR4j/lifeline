# v0.2.0 Public Beta Release Checklist

## Automated Gates

- [ ] CI passes on macOS, Windows, and Linux for Python 3.9, 3.11, and 3.13.
- [ ] Wheel and source distribution pass `twine check`.
- [ ] Clean wheel installation passes on all three operating systems.
- [ ] Repository and history contain no secrets or private transcripts.

## Handoff Matrix

Validate on macOS and native Windows:

- [ ] Claude -> Codex
- [ ] Claude -> Gemini
- [ ] Codex -> Claude
- [ ] Codex -> Gemini
- [ ] Gemini -> Claude
- [ ] Gemini -> Codex

Validate representative protected launches and handoffs on Linux and WSL.

## Windows

- [ ] PowerShell and cmd protected launches work.
- [ ] Windows Terminal immediate handoff works.
- [ ] PowerShell fallback works without `wt.exe`.
- [ ] cmd fallback works without PowerShell.
- [ ] Unicode, Ctrl+C, resize, and paths containing spaces work.
- [ ] Multiple sessions, stale records, and failed targets behave safely.

## Publication

- [ ] TestPyPI installation passes on macOS, Windows, Linux, and WSL.
- [ ] Package version and `v0.2.0` tag match.
- [ ] PyPI Trusted Publishing environment is configured.
- [ ] GitHub release and PyPI contain identical artifacts.
