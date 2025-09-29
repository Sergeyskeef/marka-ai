import re
SECRET_PATTERNS = [re.compile(r'(?:AWS|SECRET|TOKEN|PASSWORD)[A-Z0-9_]*=\\S+', re.I)]

def redact(text: str) -> str:
    t = text
    for p in SECRET_PATTERNS:
        t = p.sub("[REDACTED]", t)
    return t
