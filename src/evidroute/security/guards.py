from __future__ import annotations

import ipaddress
import re
from pathlib import Path
from urllib.parse import urlparse

INJECTION_PATTERNS = (
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"reveal\s+(the\s+)?system\s+prompt", re.IGNORECASE),
    re.compile(r"developer\s+message", re.IGNORECASE),
    re.compile(r"execute\s+(this\s+)?command", re.IGNORECASE),
)
EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_PATTERN = re.compile(r"(?<!\w)(?:\+?\d[\d .()-]{7,}\d)")


def detect_prompt_injection(text: str) -> list[str]:
    return [
        f"pattern_{index}"
        for index, pattern in enumerate(INJECTION_PATTERNS)
        if pattern.search(text)
    ]


def redact_pii(text: str) -> tuple[str, list[str]]:
    flags: list[str] = []
    redacted = EMAIL_PATTERN.sub("[REDACTED_EMAIL]", text)
    if redacted != text:
        flags.append("EMAIL")
    next_text = PHONE_PATTERN.sub("[REDACTED_PHONE]", redacted)
    if next_text != redacted:
        flags.append("PHONE")
    return next_text, flags


def is_safe_public_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    if parsed.username or parsed.password:
        return False
    if parsed.hostname.lower() in {"localhost", "localhost.localdomain"}:
        return False
    try:
        address = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        return True
    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
    )


def safe_local_path(root: Path, candidate: str) -> Path:
    resolved_root = root.resolve()
    resolved_candidate = (resolved_root / candidate).resolve()
    if resolved_candidate != resolved_root and resolved_root not in resolved_candidate.parents:
        raise ValueError("path escapes the permitted root")
    return resolved_candidate
