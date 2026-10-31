"""
browser/runner.py
-----------------
Playwright-based browser test executor.

Responsibilities:
- Launch a Chromium browser (headless by default).
- Navigate to the approved target URL.
- Execute a structured TestCase via deterministic locators.
- Capture a screenshot on failure.
- Return a structured ExecutionResult.

Safety rules enforced:
- URL must pass safety.is_url_allowed() before navigation.
- All log output passes through safety.sanitise_log().
- Destructive actions are blocked in safe mode.
"""

from __future__ import annotations

import base64
import os
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from app.browser.safety import is_url_allowed, sanitise_log
from app.test_case_generator import TestCase


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ExecutionResult:
    """Result of executing a single test case in the browser."""
    test_case_id: str
    test_scenario: str
    status: str          # PASSED | FAILED | BLOCKED | SKIPPED | ERROR
    expected_result: str
    actual_result: str
    error_message: str = ""
    screenshot_path: str = ""   # relative path to screenshot file
    logs: List[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    executed_at: str = ""

    def to_dict(self) -> Dict:
        return {
            "test_case_id": self.test_case_id,
            "test_scenario": self.test_scenario,
            "status": self.status,
            "expected_result": self.expected_result,
            "actual_result": self.actual_result,
            "error_message": self.error_message,
            "screenshot_path": self.screenshot_path,
            "logs": sanitise_log("\n".join(self.logs)),
            "duration_seconds": self.duration_seconds,
            "executed_at": self.executed_at,
        }


# ---------------------------------------------------------------------------
# Screenshot directory
# ---------------------------------------------------------------------------

_SCREENSHOT_DIR = Path("screenshots")


def _ensure_screenshot_dir() -> Path:
    _SCREENSHOT_DIR.mkdir(exist_ok=True)
    return _SCREENSHOT_DIR


# ---------------------------------------------------------------------------
# Main executor
# ---------------------------------------------------------------------------

def execute_test_case(
    test_case: TestCase,
    target_url: str,
    headless: bool = True,
    timeout_ms: int = 10000,
    slow_mo_ms: int = 0,
) -> ExecutionResult:
    """
    Execute a single TestCase in a Playwright Chromium browser.

    Parameters
    ----------
    test_case : TestCase
    target_url : str
        Base URL of the application under test (must be on the allowlist).
    headless : bool
        Run browser headless (default True). If False, opens a visible browser window.
    timeout_ms : int
        Default Playwright timeout in milliseconds.
    slow_mo_ms : int
        Slow down Playwright actions by milliseconds (e.g. 800ms to watch live).

    Returns
    -------
    ExecutionResult
    """
    start = time.time()
    logs: List[str] = []
    screenshot_path = ""
    executed_at = datetime.now(timezone.utc).isoformat()

    def log(msg: str) -> None:
        logs.append(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] {msg}")

    # ── Safety check ──────────────────────────────────────────────────────
    if not is_url_allowed(target_url):
        return ExecutionResult(
            test_case_id=test_case.test_case_id,
            test_scenario=test_case.test_scenario,
            status="BLOCKED",
            expected_result=test_case.expected_result,
            actual_result="Test blocked — target URL is not on the approved domain list.",
            error_message=f"URL not allowed: {target_url}",
            logs=logs,
            duration_seconds=time.time() - start,
            executed_at=executed_at,
        )

    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout
    except ImportError:
        return ExecutionResult(
            test_case_id=test_case.test_case_id,
            test_scenario=test_case.test_scenario,
            status="ERROR",
            expected_result=test_case.expected_result,
            actual_result="Playwright is not installed.",
            error_message="Run: playwright install chromium",
            logs=logs,
            duration_seconds=time.time() - start,
            executed_at=executed_at,
        )

    log(f"Starting test: {test_case.test_case_id} — {test_case.test_scenario}")
    log(f"Target URL: {target_url}")

    try:
        browser_args = [
            "--start-maximized",
            "--window-position=50,50",
            "--window-size=1280,800",
            "--disable-infobars",
        ] if not headless else []

        with sync_playwright() as pw:
            # Try launching installed Google Chrome first for desktop visibility; fallback to bundled Chromium
            browser = None
            if not headless:
                try:
                    browser = pw.chromium.launch(
                        channel="chrome",
                        headless=False,
                        slow_mo=slow_mo_ms,
                        args=browser_args,
                    )
                except Exception:
                    browser = None

            if browser is None:
                browser = pw.chromium.launch(
                    headless=headless,
                    slow_mo=slow_mo_ms,
                    args=browser_args,
                )

            context = browser.new_context(viewport={"width": 1280, "height": 800} if not headless else None)
            page = context.new_page()
            page.set_default_timeout(timeout_ms)

            # Collect browser console messages
            page.on("console", lambda msg: log(f"[Browser:{msg.type}] {msg.text}"))

            log("Browser launched. Navigating to target URL...")
            page.goto(target_url, wait_until="domcontentloaded")
            log(f"Page title: {page.title()}")

            # Delegate to the appropriate runner based on test scenario keywords
            actual_result, status = _dispatch_test(page, test_case, target_url, log)

            if not headless and slow_mo_ms > 0:
                page.wait_for_timeout(1000)

            # Capture visual evidence of the actual browser state
            screenshot_path = _capture_screenshot(page, test_case.test_case_id)
            log(f"Browser screenshot captured: {screenshot_path}")

            browser.close()
            log(f"Test completed with status: {status}")

    except Exception as exc:
        tb = traceback.format_exc()
        error_msg = str(exc)
        log(f"EXCEPTION: {error_msg}")
        log(tb)

        # Attempt screenshot even on unexpected error
        try:
            with sync_playwright() as pw2:
                b2 = pw2.chromium.launch(headless=headless)
                p2 = b2.new_page()
                p2.goto(target_url, wait_until="domcontentloaded")
                screenshot_path = _capture_screenshot(p2, test_case.test_case_id + "_error")
                b2.close()
        except Exception:
            pass

        return ExecutionResult(
            test_case_id=test_case.test_case_id,
            test_scenario=test_case.test_scenario,
            status="ERROR",
            expected_result=test_case.expected_result,
            actual_result=f"Unexpected error during test execution: {error_msg}",
            error_message=sanitise_log(error_msg),
            screenshot_path=screenshot_path,
            logs=logs,
            duration_seconds=time.time() - start,
            executed_at=executed_at,
        )

    return ExecutionResult(
        test_case_id=test_case.test_case_id,
        test_scenario=test_case.test_scenario,
        status=status,
        expected_result=test_case.expected_result,
        actual_result=actual_result,
        screenshot_path=screenshot_path,
        logs=logs,
        duration_seconds=time.time() - start,
        executed_at=executed_at,
    )


# ---------------------------------------------------------------------------
# Test dispatcher & Step-by-Step User Action Executor
# ---------------------------------------------------------------------------

def _dispatch_test(page, test_case: TestCase, base_url: str, log) -> tuple:
    """
    Execute tests strictly according to the steps specified by the user.

    Returns
    -------
    (actual_result: str, status: str)
    """
    return _execute_user_steps(page, test_case, base_url, log)


def _get_site_defaults(base_url: str) -> tuple:
    """Return default (valid_user, valid_pass) for the target application."""
    u = (base_url or "").lower()
    if "sauce" in u:
        return "standard_user", "secret_sauce"
    if "the-internet" in u or "herokuapp" in u:
        return "tomsmith", "SuperSecretPassword!"
    if "practicetest" in u:
        return "student", "Password123"
    return "demo@example.com", "DemoPass@123"


def _resolve_input_value(step: str, is_username: bool, base_url: str, fallback: str) -> str:
    """Extract or intelligently infer the value to type into the input field."""
    import re
    s_low = step.lower()
    default_user, default_pass = _get_site_defaults(base_url)
    default_val = default_user if is_username else default_pass
    invalid_val = "invalid_user@example.com" if is_username else "WrongPass999!"

    # 1. Quoted string: 'value' or "value"
    val_match = re.search(r'[\'"]([^\'"]+)[\'"]', step)
    if val_match:
        return val_match.group(1).strip()

    # 2. Explicit clear/empty instruction
    if any(w in s_low for w in ["empty", "blank", "clear", "leave", "omit", "do not enter"]):
        return ""

    # 3. Explicit invalid keywords
    if any(w in s_low for w in ["invalid", "wrong", "incorrect", "bad", "fake"]):
        return invalid_val

    # 4. Explicit valid keywords (e.g. "enter valid name", "enter valid password")
    if any(w in s_low for w in ["valid", "correct", "demo", "real", "standard"]):
        return default_val

    # 5. Extract word following keyword: e.g. "enter name demo@example.com"
    kw = r'(?:name|username|email|mail|password|pwd|pass)[:\s=]+([^\s,]+)'
    m = re.search(kw, step, re.IGNORECASE)
    if m:
        candidate = m.group(1).strip()
        if candidate.lower() not in ("a", "an", "the", "is", "field", "input", "box", "valid", "invalid", "and"):
            return candidate

    # 6. Fallback from test_data or site default
    return fallback or default_val


def _execute_user_steps(page, test_case: TestCase, base_url: str, log) -> tuple:
    """
    Parse and execute ONLY the exact steps defined by the user in test_case.test_steps.
    Does not perform unrequested actions (e.g. will NOT click submit unless requested in steps).
    """
    from app.browser.locators import (
        fill_email, fill_password, click_login,
        get_error_message, is_logged_in,
    )
    import re

    raw_steps = (test_case.test_steps or "").strip()
    # If test_steps is empty or placeholder, fall back to scenario text
    if not raw_steps or raw_steps.lower() in ("n/a", "none", "see scenario", "see test scenario"):
        raw_steps = test_case.test_scenario or ""

    fallback_email, fallback_password = _parse_credentials(test_case.test_data, raw_steps)

    # Split steps by newlines or numbered list patterns (e.g. "1. ... 2. ...")
    lines = [s.strip() for s in re.split(r'(?:\r?\n|\b\d+[\.:\)]\s*)', raw_steps) if s.strip()]

    # If still no lines, fall back to credentials in test_data if present
    if not lines:
        lines = []
        if fallback_email:
            lines.append(f"Enter email '{fallback_email}'")
        if fallback_password:
            lines.append(f"Enter password '{fallback_password}'")
        if fallback_email or fallback_password:
            lines.append("Click 'Sign In'")
        else:
            lines.append("Verify page loaded")

    username_kws = ["email", "mail", "username", "user", "name", "login id", "account", "id"]
    password_kws = ["password", "pwd", "pass", "secret"]
    click_kws = ["click", "press", "tap", "submit", "sign in", "login button", "log in button"]

    button_clicked = False
    email_performed = False
    password_performed = False
    entered_email_val = ""
    entered_password_val = ""

    try:
        for idx, step in enumerate(lines, start=1):
            s_low = step.lower().strip()
            log(f"Step {idx}: {step}")

            # 1. Navigation step
            if any(w in s_low for w in ["navigate", "go to", "open", "visit"]) and not any(w in s_low for w in click_kws):
                target_match = re.search(r'(https?://[^\s\'"]+|/[^\s\'"]*)', step)
                if target_match:
                    dest = target_match.group(1)
                    if dest.startswith("/"):
                        from urllib.parse import urljoin
                        dest = urljoin(base_url, dest)
                    page.goto(dest, wait_until="domcontentloaded")
                    log(f"-> Navigated to: {dest}")
                continue

            # 2. Email / Username step (matches "name", "username", "email", "mail", "user")
            is_email_step = any(w in s_low for w in username_kws) and not any(w in s_low for w in ["click", "button"])
            if is_email_step:
                email_performed = True
                val = _resolve_input_value(step, is_username=True, base_url=base_url, fallback=fallback_email)
                fill_email(page, val)
                entered_email_val = val
                log(f"-> Entered email/username: '{val}'")
                page.wait_for_timeout(400)

            # 3. Password step
            is_pwd_step = any(w in s_low for w in password_kws) and not any(w in s_low for w in ["click", "button"])
            if is_pwd_step:
                password_performed = True
                val = _resolve_input_value(step, is_username=False, base_url=base_url, fallback=fallback_password)
                fill_password(page, val)
                entered_password_val = val
                log("-> Entered password: [REDACTED]")
                page.wait_for_timeout(400)

            # 4. Click / Submit step
            is_click_step = any(w in s_low for w in click_kws)
            if is_click_step:
                button_clicked = True
                click_login(page)
                log("-> Clicked submit/login button")
                page.wait_for_timeout(800)

        # ── Outcome Evaluation ──
        # If user steps explicitly requested clicking submit, evaluate login outcome
        if button_clicked:
            logged_in = is_logged_in(page)
            error_msg = get_error_message(page) if not logged_in else ""
            actual, status = _evaluate_login_outcome(
                logged_in=logged_in,
                error_msg=error_msg,
                expected_result=test_case.expected_result,
                test_type=test_case.test_type,
            )
            log(f"Outcome evaluated: {actual} -> {status}")
            return actual, status

        # If user did NOT specify clicking submit, verify that the requested steps were executed
        actions_done = []
        if email_performed:
            actions_done.append(f"entered username/email '{entered_email_val}'")
        if password_performed:
            actions_done.append("entered password")
        if not actions_done:
            actions_done.append("verified page loaded")

        actual = f"Steps completed successfully: {', '.join(actions_done)} (form was not submitted)."
        log(actual)
        return actual, "PASSED"

    except Exception as exc:
        actual = f"Step execution failed: {exc}"
        log(f"ERROR: {actual}")
        return actual, "FAILED"


def _evaluate_login_outcome(
    logged_in: bool,
    error_msg: str,
    expected_result: str,
    test_type: str = "",
) -> tuple:
    """
    Determine whether the actual login outcome matches the expected result.

    Returns (actual_result: str, status: str)
    """
    import re
    exp_lower = (expected_result or "").lower().strip()
    type_lower = (test_type or "").lower().strip()

    # 1. Check for explicit success intent (e.g. "login successful", "dashboard", "welcome")
    has_success_intent = any(kw in exp_lower for kw in ["success", "dashboard", "welcome", "logged in", "redirect", "landing"])

    # 2. Check for explicit negation / error patterns
    negative_patterns = [
        r"\bnot\s+success",
        r"\bshould\s+not\b",
        r"\bmust\s+not\b",
        r"\bcannot\b",
        r"\bcan't\b",
        r"\bunable\b",
        r"\bfail",              # fail, failed, fails, failure
        r"\bunsuccessful\b",
        r"\berror\b",
        r"\binvalid\b",
        r"\bincorrect\b",
        r"\bempty\b",
        r"\brequired\b",
        r"\bformat\b",
        r"\breject",
        r"\bblock",
        r"\bdisallow",
        r"\bdeni",              # denied, denies
        r"\bwarn",
    ]
    has_negation = any(re.search(p, exp_lower) for p in negative_patterns)

    # Resolve intent:
    # If expected_result has success wording but also has negation ("login should not success", "not redirect"), it is NEGATIVE.
    if has_negation:
        expects_success = False
        expects_failure = True
    elif has_success_intent:
        expects_success = True
        expects_failure = False
    elif type_lower in ("negative", "validation"):
        expects_success = False
        expects_failure = True
    else:
        expects_success = True
        expects_failure = False

    if logged_in:
        actual = "Login successful. Dashboard/welcome page is displayed."
        if expects_failure:
            # Expected rejection/failure, but login succeeded! Security / validation violation
            return actual, "FAILED"
        else:
            return actual, "PASSED"

    if error_msg:
        actual = f"Login failed. Error message displayed: '{error_msg}'"
        if expects_success:
            # Expected success, but login failed with error -> FAILED
            return actual, "FAILED"
        elif expects_failure:
            # Expected failure, and error was correctly displayed -> PASSED
            return actual, "PASSED"
        else:
            return actual, "FAILED"

    # No success, no explicit error (remained on login page)
    actual = "Login attempted. Form remained unsubmitted or no clear message displayed."
    if expects_failure:
        return actual, "PASSED"
    return actual, "FAILED"


def _parse_credentials(test_data: str, test_steps: str = "") -> tuple:
    """
    Extract email/username and password from test_data string or test_steps.

    Supports formats like:
    - "Email: user@example.com, Password: ValidPass@1"
    - "Username: standard_user, Password: secret_sauce"
    - "enter username 'demo@example.com' enter password 'DemoPass@123'"
    - Raw email addresses like 'demo@example.com' anywhere in text
    - "N/A" -> returns ("", "")
    """
    import re
    email = ""
    password = ""

    data_str = test_data or ""
    steps_str = test_steps or ""
    combined = f"{data_str} {steps_str}"

    # 1. Look in test_data first
    if data_str and data_str.strip().upper() != "N/A":
        email_match = re.search(r'(?i)(?:email|username|user)[:\s=]+[\'"]?([^\s,\'"]+)[\'"]?', data_str)
        if email_match:
            val = email_match.group(1).strip()
            if val.lower() not in ("the", "a", "an", "is", "field", "input"):
                email = val

        pwd_match = re.search(r'(?i)(?:password|pwd|pass)[:\s=]+[\'"]?([^\s,\'"]+)[\'"]?', data_str)
        if pwd_match:
            password = pwd_match.group(1).strip()

    # 2. Look in test_steps
    if not email and steps_str:
        s_email = re.search(r'(?i)(?:email|username|user)[\s\w]*[\'"]([^\'"]+)[\'"]', steps_str)
        if s_email:
            email = s_email.group(1).strip()
        else:
            u_email = re.search(r'(?i)(?:email|username|user)[:\s=]+([^\s,]+)', steps_str)
            if u_email:
                val = u_email.group(1).strip()
                if val.lower() not in ("the", "a", "an", "is", "field", "input"):
                    email = val

    # 3. If email still empty, search for raw email pattern
    if not email:
        raw_email = re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b', combined)
        if raw_email:
            email = raw_email.group(0).strip()

    # 4. Search for password in steps if not found yet
    if not password and steps_str:
        s_pwd = re.search(r'(?i)(?:password|pwd|pass)[\s\w]*[\'"]([^\'"]+)[\'"]', steps_str)
        if s_pwd:
            password = s_pwd.group(1).strip()
        else:
            u_pwd = re.search(r'(?i)(?:password|pwd|pass)[:\s=]+([^\s,]+)', steps_str)
            if u_pwd:
                val = u_pwd.group(1).strip()
                if val.lower() not in ("the", "a", "an", "is", "field", "input"):
                    password = val

    return email, password


# ---------------------------------------------------------------------------
# Screenshot helper
# ---------------------------------------------------------------------------

def _capture_screenshot(page, name: str) -> str:
    """Capture a screenshot and return the relative file path."""
    try:
        screenshot_dir = _ensure_screenshot_dir()
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"{name}_{ts}.png"
        path = screenshot_dir / filename
        page.screenshot(path=str(path), full_page=True)
        return str(path)
    except Exception:
        return ""

