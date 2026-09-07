"""Regex PII redaction.

Used for anything that gets written to logs or LangSmith trace metadata — never
applied silently to model input, since that would break legitimate requests
("what's the address in that email?").
"""

import re

_PATTERNS: list[tuple[str, re.Pattern]] = [
    # API / token-ish strings first (most specific)
    ("KEY", re.compile(r"\b(?:sk|pk|rk|ghp|gho|xox[baprs])[-_][A-Za-z0-9]{16,}\b")),
    ("KEY", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("CARD", re.compile(r"\b(?:\d[ -]?){13,16}\b")),
    ("PHONE", re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")),
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
]


def redact_pii(text: str) -> str:
    if not text:
        return text
    for label, pattern in _PATTERNS:
        text = pattern.sub(f"[REDACTED_{label}]", text)
    return text


def redact_for_log(text: str, limit: int = 500) -> str:
    """Redact and truncate — the shape you want in a log line."""
    red = redact_pii(text or "")
    return red if len(red) <= limit else red[:limit] + "…"
