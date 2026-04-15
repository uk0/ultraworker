"""Security utilities for LTM records.

Provides secret redaction and deduplication key generation.
"""

import hashlib
import re

# Patterns for sensitive tokens/keys
_SECRET_PATTERNS: list[tuple[str, str]] = [
    (r"xoxc-[A-Za-z0-9\-]+", "[REDACTED:slack-user-token]"),
    (r"xoxb-[A-Za-z0-9\-]+", "[REDACTED:slack-bot-token]"),
    (r"xoxd-[A-Za-z0-9\-]+", "[REDACTED:slack-cookie]"),
    (r"xoxp-[A-Za-z0-9\-]+", "[REDACTED:slack-legacy-token]"),
    (r"xoxs-[A-Za-z0-9\-]+", "[REDACTED:slack-session-token]"),
    (r"-----BEGIN [A-Z ]+-----[\s\S]*?-----END [A-Z ]+-----", "[REDACTED:pem-key]"),
    (r"AKIA[A-Z0-9]{16}", "[REDACTED:aws-access-key]"),
    (r"sk-ant-[A-Za-z0-9\-]+", "[REDACTED:anthropic-api-key]"),
    (r"sk-[A-Za-z0-9]{20,}", "[REDACTED:api-key]"),
    (r"ghp_[A-Za-z0-9]{36,}", "[REDACTED:github-pat]"),
    (r"gho_[A-Za-z0-9]{36,}", "[REDACTED:github-oauth]"),
    (r"AIza[A-Za-z0-9\-_]{35}", "[REDACTED:google-api-key]"),
]

_COMPILED_PATTERNS = [
    (re.compile(pattern), replacement) for pattern, replacement in _SECRET_PATTERNS
]


def redact_secrets(text: str) -> str:
    """Replace sensitive tokens/keys in text with [REDACTED:<type>].

    Args:
        text: Input text potentially containing secrets

    Returns:
        Text with secrets replaced
    """
    result = text
    for pattern, replacement in _COMPILED_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def generate_dedupe_key(content: str, step_ref: str, uris: list[str]) -> str:
    """Generate a deduplication key for a record.

    Uses SHA-256 hash of normalized content + step_ref + sorted URIs.

    Args:
        content: Main content text
        step_ref: Step reference string
        uris: List of URIs associated with the record

    Returns:
        Hex-encoded SHA-256 hash string
    """
    normalized_content = " ".join(content.lower().split())
    normalized_step_ref = step_ref.strip().lower()
    sorted_uris = sorted(uri.strip().lower() for uri in uris)

    combined = f"{normalized_content}|{normalized_step_ref}|{'|'.join(sorted_uris)}"
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()
