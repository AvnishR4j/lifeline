# Security Policy

## Reporting

Report vulnerabilities privately through GitHub Security Advisories for this
repository. Do not open a public issue containing secrets, raw transcripts, or
proof-of-concept credentials.

## Data Handling

Lifeline reads local AI CLI transcripts, redacts common secret formats, and sends
the resulting handoff to the selected AI provider. Redaction is pattern-based and
cannot guarantee removal of every secret. Review `--dry-run` output when handling
sensitive work.

Handoff files are stored under `~/.lifeline/handoffs/`. Active-session records
under `~/.lifeline/active/` contain metadata only. Unix permissions are restricted
to the current user; Windows relies on the user's profile directory permissions.
