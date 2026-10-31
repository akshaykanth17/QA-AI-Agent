"""
browser/locators.py
-------------------
Element location strategies for the demo login application.

Uses data-testid attributes as the primary locator strategy (most reliable).
Falls back to semantic HTML selectors if testid attributes are not present.

These locators target the local demo login app at app/demo/app.py.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Login form interactions
# ---------------------------------------------------------------------------

def fill_email(page, email: str) -> None:
    """Fill the email/username input field."""
    selectors = [
        '[data-testid="email-input"]',
        '[data-testid="username"]',
        '[data-test="username"]',
        '#user-name',
        '#username',
        'input[name="user-name"]',
        'input[name="username"]',
        'input[type="email"]',
        'input[name="email"]',
        '#email',
        'input[placeholder*="username" i]',
        'input[placeholder*="email" i]',
    ]
    for sel in selectors:
        locator = page.locator(sel).first
        if locator.count() > 0:
            locator.fill(email)
            return
    # Fallback to first text/email input on page
    fallback = page.locator('input[type="text"], input[type="email"]').first
    if fallback.count() > 0:
        fallback.fill(email)


def fill_password(page, password: str) -> None:
    """Fill the password input field."""
    selectors = [
        '[data-testid="password-input"]',
        '[data-test="password"]',
        '#password',
        'input[name="password"]',
        'input[type="password"]',
    ]
    for sel in selectors:
        locator = page.locator(sel).first
        if locator.count() > 0:
            locator.fill(password)
            return


def click_login(page) -> None:
    """Click the login/submit button."""
    selectors = [
        '[data-testid="login-button"]',
        '[data-test="login-button"]',
        '#login-button',
        'input[type="submit"]',
        'button[type="submit"]',
        'button:has-text("Login")',
        'button:has-text("Log in")',
        'button:has-text("Sign in")',
        'button:has-text("Submit")',
    ]
    for sel in selectors:
        locator = page.locator(sel).first
        if locator.count() > 0:
            locator.click()
            return


def get_error_message(page) -> str:
    """
    Return the text of any error message displayed on the page.
    Returns empty string if no error element is found.
    """
    selectors = [
        '[data-test="error"]',
        '[data-testid="error-message"]',
        '#flash',
        '.flash',
        '.error-message',
        '.alert-danger',
        '.alert-error',
        '[role="alert"]',
        '#error',
        '.error',
        '.show',
    ]
    for selector in selectors:
        el = page.locator(selector).first
        if el.count() > 0:
            try:
                text = el.inner_text(timeout=2000).strip()
                if text:
                    return text
            except Exception:
                pass
    return ""


def is_logged_in(page) -> bool:
    """
    Return True if the page shows indicators of a successful login.
    Checks for welcome messages, dashboard elements, products, or logout links.
    """
    success_selectors = [
        '[data-testid="welcome-message"]',
        '[data-testid="dashboard"]',
        '#shopping_cart_container',
        '.inventory_list',
        '.title:has-text("Products")',
        '.welcome',
        '#welcome',
        'text=Welcome',
        'text=Dashboard',
        'text=Logged In Successfully',
        'text=Secure Area',
        'text=Logout',
        'text=Log out',
        'a[href*="logout"]',
        '#react-burger-menu-btn',
    ]
    for selector in success_selectors:
        try:
            el = page.locator(selector).first
            if el.count() > 0 and el.is_visible(timeout=1000):
                return True
        except Exception:
            pass
    return False

