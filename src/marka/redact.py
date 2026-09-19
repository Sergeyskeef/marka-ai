"""Defense in depth for persisted text. Never a replacement for secret isolation."""

import re

_PATTERNS = (
    # Legacy serialized text can put a letter (including a literal "\\n")
    # directly before the numeric prefix; a word boundary misses that case.
    (re.compile(r"(?<!\d)\d{6,12}:[A-Za-z0-9_-]{25,}\b"), "[REDACTED_TELEGRAM_TOKEN]"),
    (re.compile(r"\b(?:sk-|ghp_|github_pat_|gho_)[A-Za-z0-9_-]{16,}\b"), "[REDACTED_KEY]"),
    (re.compile(r"\b(?:xox[baprs]-|glpat-|AIza)[A-Za-z0-9_-]{16,}\b"), "[REDACTED_SERVICE_KEY]"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"), "[REDACTED_JWT]"),
    (re.compile(r"(?i)(\b(?:password|passwd|api[_-]?key|access[_-]?token|refresh[_-]?token|bot[_-]?token|пароль|токен)\b[\"']?\s*[=:]\s*[\"']?)[^\s,;\"'{}\[\]<>]+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(\bBearer\s+)[A-Za-z0-9._~+/-]{12,}=*"), r"\1[REDACTED_BEARER]"),
    (re.compile(r"(?i)(https?://)[^\s/:@]+:[^\s/@]+@"), r"\1[REDACTED_CREDENTIALS]@"),
    (re.compile(r"(?is)-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----"), "[REDACTED_PRIVATE_KEY]"),
)


def redact(text: str) -> str:
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, str(text))
    return text


def redact_value(value):
    """Redact string leaves before JSON serialization so structure survives."""
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {str(key): "[REDACTED]" if re.fullmatch(r"(?i)password|passwd|api[_-]?key|access[_-]?token|refresh[_-]?token|bot[_-]?token|пароль|токен", str(key))
                else redact_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [redact_value(item) for item in value]
    return value
