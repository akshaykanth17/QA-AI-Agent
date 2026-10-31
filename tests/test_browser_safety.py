"""
tests/test_browser_safety.py
-----------------------------
Unit tests for app/browser/safety.py:
- URL allowlist
- Private IP blocking
- Safe mode action guards
- Credential & token log sanitisation
"""

import pytest
from app.browser.safety import (
    check_action_allowed,
    get_allowed_domains,
    is_safe_mode,
    is_url_allowed,
    sanitise_log,
    sanitise_log_line,
)


class TestBrowserSafety:

    def test_localhost_and_loopback_allowed_by_default(self):
        assert is_url_allowed("http://localhost:5000/login") is True
        assert is_url_allowed("http://127.0.0.1:8000/test") is True

    def test_unapproved_domain_blocked(self, monkeypatch):
        monkeypatch.setenv("ALLOWED_DOMAINS", "example.com")
        assert is_url_allowed("https://malicious-site.com") is False
        assert is_url_allowed("https://example.com/login") is True

    def test_subdomain_matching(self, monkeypatch):
        monkeypatch.setenv("ALLOWED_DOMAINS", "staging.testapp.com")
        assert is_url_allowed("https://staging.testapp.com/dashboard") is True
        assert is_url_allowed("https://unapproved.com") is False

    def test_private_ip_blocked_unless_explicitly_allowed(self, monkeypatch):
        monkeypatch.setenv("ALLOWED_DOMAINS", "localhost")
        assert is_url_allowed("http://192.168.1.10/admin") is False
        assert is_url_allowed("http://10.0.0.5:8080") is False

    def test_invalid_scheme_blocked(self):
        assert is_url_allowed("ftp://localhost:21") is False
        assert is_url_allowed("javascript:alert(1)") is False

    def test_safe_mode_blocks_destructive_actions(self, monkeypatch):
        monkeypatch.setenv("SAFE_MODE", "true")
        assert check_action_allowed("click_button") is True
        assert check_action_allowed("enter_text") is True
        assert check_action_allowed("delete") is False
        assert check_action_allowed("purchase") is False
        assert check_action_allowed("checkout") is False
        assert check_action_allowed("change_password") is False

    def test_safe_mode_disabled(self, monkeypatch):
        monkeypatch.setenv("SAFE_MODE", "false")
        assert check_action_allowed("delete") is True

    def test_log_sanitisation(self):
        dirty = "Login attempt with password: SuperSecretPassword123! on port 5000"
        clean = sanitise_log_line(dirty)
        assert "SuperSecretPassword123!" not in clean
        assert "[REDACTED]" in clean

    def test_openai_key_sanitisation(self):
        dirty = "Calling OpenAI with key sk-1234567890abcdef1234567890"
        clean = sanitise_log_line(dirty)
        assert "sk-1234567890abcdef1234567890" not in clean
        assert "[REDACTED]" in clean

