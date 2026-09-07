"""One entry point the graph uses to make untrusted text safe to hand an LLM:
fence it as data and screen it for injection.

Redaction is deliberately *not* applied here — the assistant may legitimately
need a phone number or address that appears in an email. Redaction belongs at
the logging / tracing boundary (`security.redaction`).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from security.injection import scan_for_injection


@dataclass
class GuardResult:
    safe_text: str          # fenced, ready to drop into a prompt
    flagged: bool
    reasons: list[str] = field(default_factory=list)


def wrap_untrusted(text: str, source: str) -> str:
    return (
        f'<untrusted_content source="{source}">\n'
        f"{text}\n"
        f"</untrusted_content>"
    )


def guard_untrusted_text(text: str, *, source: str, allow_llm: bool = True) -> GuardResult:
    verdict = scan_for_injection(text or "", allow_llm=allow_llm)
    return GuardResult(
        safe_text=wrap_untrusted(text or "", source),
        flagged=verdict.flagged,
        reasons=verdict.reasons,
    )
