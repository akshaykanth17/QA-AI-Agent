"""
browser/safety.py
-----------------
Domain allowlist and action safety guard for browser automation.

Safety rules:
- Only allow navigation to explicitly approved domains.
- localhost and 127.0.0.1 are always permitted as dev/test targets.
- Private network ranges (10.x, 172.16-31.x, 192.168.x) are blocked by
  default unless the domain is explicitly listed.
- Destructive actions are disabled when SAFE_MODE=true (the default).
- Credentials are never written to logs.
"""

from __future__ import annotations

import os
import re
from typing import List, Set
from urllib.parse import urlparse


# ---------------------------------------------------------------------------
# Always-allowed hosts (local test environments & standard QA practice sites)
# ---------------------------------------------------------------------------

_ALWAYS_ALLOWED: Set[str] = {
    "localhost",
    "127.0.0.1",
    "saucedemo.com",
    "www.saucedemo.com",
    "the-internet.herokuapp.com",
    "practicetestautomation.com",
}

# Private IPv4 ranges (blocked unless explicitly allowed)
_PRIVATE_PATTERNS = [
    re.compile(r"^10\.\d+\.\d+\.\d+$"),
    re.compile(r"^172\.(1[6-9]|2\d|3[01])\.\d+\.\d+$"),
    re.compile(r"^192\.168\.\d+\.\d+$"),
]

# Destructive action keywords — blocked in safe mode
_DESTRUCTIVE_ACTIONS = {
    "delete",
    "remove",
    "drop",
    "destroy",
    "checkout",
    "purchase",
    "buy",
    "pay",
    "submit_payment",
    "change_password",
    "reset_password",
    "send_message",
    "send_email",
}


def get_allowed_domains() -> Set[str]:
    """
    Return the set of approved target domains.

    Reads ALLOWED_DOMAINS from the environment (comma-separated).
    localhost and 127.0.0.1 are always included.
    """
    env_val = os.environ.get("ALLOWED_DOMAINS", "")
    extra = {d.strip().lower() for d in env_val.split(",") if d.strip()}
    return _ALWAYS_ALLOWED | extra


def is_url_allowed(url: str) -> bool:
    """
    Return True if *url* is safe to navigate to.

    A URL is allowed if:
    - Its hostname is in the approved domain list, OR
    - Its hostname is localhost / 127.0.0.1.

    A URL is blocked if:
    - Its hostname falls in a private IP range AND is not explicitly listed.
    - The scheme is not http or https.

    Parameters
    ----------
    url : str
        Full URL to validate.

    Returns
    -------
    bool
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return False

    if parsed.scheme not in ("http", "https"):
        return False

    host = (parsed.hostname or "").lower()
    if not host:
        return False

    allowed = get_allowed_domains()

    # Exact match
    if host in allowed:
        return True

    # Subdomain match — e.g. staging.myapp.example.com matches myapp.example.com
    for domain in allowed:
        if host == domain or host.endswith("." + domain):
            return True

    # Block private ranges unless explicitly listed
    if _is_private_ip(host):
        return False

    return False


def _is_private_ip(host: str) -> bool:
    """Return True if *host* looks like a private IP address."""
    return any(p.match(host) for p in _PRIVATE_PATTERNS)


def is_safe_mode() -> bool:
    """Return True if SAFE_MODE is enabled (default: True)."""
    val = os.environ.get("SAFE_MODE", "true").strip().lower()
    return val not in ("false", "0", "no", "off")


def check_action_allowed(action_name: str) -> bool:
    """
    Return True if the given action is permitted.

    In safe mode, destructive actions are blocked.
    action_name is compared case-insensitively against the blocked list.

    Parameters
    ----------
    action_name : str
        Name of the action to check (e.g. "delete", "checkout").

    Returns
    -------
    bool
    """
    if not is_safe_mode():
        return True
    return action_name.lower().strip() not in _DESTRUCTIVE_ACTIONS


def sanitise_log_line(line: str) -> str:
    """
    Redact potential secrets from a single log line.

    Replaces values that look like passwords, tokens, or API keys
    with [REDACTED] so they are not written to reports or screenshots.

    Parameters
    ----------
    line : str

    Returns
    -------
    str
    """
    # Redact key=value patterns where key suggests a secret
    line = re.sub(
        r'(?i)(password|passwd|pwd|token|api[_-]?key|secret|auth|credential)[=:\s]+\S+',
        r'\1=[REDACTED]',
        line,
    )
    # Redact Bearer tokens
    line = re.sub(r'(?i)(Bearer\s+)\S+', r'\1[REDACTED]', line)
    # Redact OpenAI-style keys (sk-...)
    line = re.sub(r'sk-[A-Za-z0-9\-_]{20,}', '[REDACTED]', line)
    return line


def sanitise_log(log: str) -> str:
    """Apply sanitise_log_line to every line of a multi-line log string."""
    return "\n".join(sanitise_log_line(line) for line in log.splitlines())

