"""Scrub secrets out of anything written to a ticket.

Callers sometimes say "my password is ..." without being asked. Tickets are read by many people,
so passwords, one-time codes, and card numbers never reach them."""

import re

# Words that commonly follow "password is" without being the password itself.
_NOT_SECRETS = r"(?:expired|wrong|incorrect|invalid|not|locked|reset|correct|too|the|still|being|no|now|fine|ok)\b"

_PATTERNS = [
    (re.compile(rf"(?i)\b(password|passcode|passphrase|pin)(\s+(?:is|was)\s+|\s*[:=]\s*)(?!{_NOT_SECRETS})\S+"),
     r"\1\2[redacted]"),
    (re.compile(r"\b(?:\d[ -]?){12,18}\d\b"), "[card number redacted]"),
    (re.compile(r"(?<![\w-])\d{6}(?![\w-])"), "[code redacted]"),
]


def redact(text: str | None) -> str:
    text = text or ""
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text
