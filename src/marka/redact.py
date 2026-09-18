"""Defense in depth for persisted text. Never a replacement for secret isolation."""

import re

_PATTERNS = (
    (re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{25,}\b"), "[REDACTED_TELEGRAM_TOKEN]"),
    (re.compile(r"\b(?:sk-|ghp_|github_pat_|gho_)[A-Za-z0-9_-]{16,}\b"), "[REDACTED_KEY]"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"), "[REDACTED_JWT]"),
    (re.compile(r"(?i)(\b(?:password|passwd|api[_-]?key|access[_-]?token|refresh[_-]?token|bot[_-]?token)\b\s*[=:]\s*)[^\s,;]+"), r"\1[REDACTED]"),
    (re.compile(r"(?is)-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----"), "[REDACTED_PRIVATE_KEY]"),
)


def redact(text: str) -> str:
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, str(text))
    return text
