#!/usr/bin/env python3
"""
Lifeline — secret redaction.

Before any session context leaves the machine (it gets shipped to another AI
provider during handoff), scrub common secret shapes. Pure local regex — no
network, no cost. Returns the cleaned text plus a count of what was redacted so
the caller can warn the user.
"""

import re
from collections import Counter

# (kind, compiled pattern). Order matters: more specific patterns first so a
# token isn't half-eaten by the generic env-var rule.
_PATTERNS = [
    # PEM private key blocks (multi-line).
    ("private-key", re.compile(
        r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----"
        r".*?-----END (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----",
        re.DOTALL,
    )),
    # OpenAI-style keys: sk-... / sk-proj-...
    ("openai-key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{16,}\b")),
    # GitHub tokens: gho_, ghp_, ghu_, ghs_, ghr_, and fine-grained github_pat_
    ("github-token", re.compile(r"\b(?:gh[opusr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b")),
    # AWS access key IDs.
    ("aws-key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    # Google API keys.
    ("google-key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    # Slack tokens.
    ("slack-token", re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{10,}\b")),
    # Common service-token formats.
    ("service-token", re.compile(
        r"\b(?:npm_[A-Za-z0-9]{20,}|glpat-[A-Za-z0-9_-]{20,}|"
        r"hf_[A-Za-z0-9]{20,}|(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{16,})\b"
    )),
    # Standalone JSON Web Tokens, even when not prefixed by "Bearer".
    ("jwt", re.compile(
        r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"
    )),
    # Credentials embedded in URLs such as postgres://user:password@host/db.
    ("url-credentials", re.compile(
        r"(?i)\b([a-z][a-z0-9+.-]*://)[^/\s:@]+:[^/\s@]+@"
    )),
    # Bearer tokens in headers/text.
    ("bearer-token", re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{16,}")),
    # .env-style assignments where the name hints at a secret. Captures the
    # name so we can keep it but mask the value.
    ("env-secret", re.compile(
        r"(?im)^(\s*(?:(?:export|set)\s+|\$env:)?[A-Z0-9_]*"
        r"(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD|PWD|CREDENTIAL|PRIVATE|API)[A-Z0-9_]*\s*[=:]\s*)"
        r"['\"]?[^\s'\"]{6,}['\"]?"
    )),
]


def redact(text: str):
    """Return (cleaned_text, findings_counter).

    findings_counter maps secret-kind -> number of redactions.
    """
    if not text:
        return text, Counter()

    findings = Counter()

    def _make_sub(kind, keep_prefix=False):
        def _sub(match):
            findings[kind] += 1
            if keep_prefix:
                # env-secret: preserve "NAME=" / "export NAME=" prefix, mask value.
                return f"{match.group(1)}[REDACTED:{kind}]"
            if kind == "url-credentials":
                return f"{match.group(1)}[REDACTED:{kind}]@"
            return f"[REDACTED:{kind}]"
        return _sub

    cleaned = text
    for kind, pattern in _PATTERNS:
        keep_prefix = kind == "env-secret"
        cleaned = pattern.sub(_make_sub(kind, keep_prefix), cleaned)

    return cleaned, findings


def summarize(findings) -> str:
    """Human-readable one-liner for a findings counter, or '' if nothing found."""
    if not findings:
        return ""
    total = sum(findings.values())
    parts = ", ".join(f"{n} {kind}" for kind, n in sorted(findings.items()))
    plural = "s" if total != 1 else ""
    return f"Redacted {total} secret{plural}: {parts}"


if __name__ == "__main__":
    # Quick self-test.
    sample = (
        "Here is my key sk-proj-ABCDEF0123456789abcdef and token gho_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789\n"
        "OPENAI_API_KEY=supersecretvalue123\n"
        "Authorization: Bearer eyJhbGciOiToken1234567890abcdef\n"
        "AWS key AKIAIOSFODNN7EXAMPLE here\n"
    )
    cleaned, found = redact(sample)
    print(cleaned)
    print("---")
    print(summarize(found))
