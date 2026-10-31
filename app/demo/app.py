"""
demo/app.py
-----------
Local Flask demo login application — for testing purposes ONLY.

Features:
- Single login endpoint with deterministic validation.
- Known credentials: demo@example.com / DemoPass@123
- Clear error messages for all invalid scenarios.
- data-testid attributes on all interactive elements for Playwright.

Run with:
    python -m app.demo.app

Serves on http://localhost:5000 by default.
DEMO_PORT environment variable overrides the port.
"""

from __future__ import annotations

import os
import re
import sys

# ---------------------------------------------------------------------------
# Flask import guard
# ---------------------------------------------------------------------------
try:
    from flask import Flask, render_template, request, redirect, url_for, session
except ImportError:
    print("Flask is not installed. Run: pip install flask")
    sys.exit(1)

app = Flask(__name__, template_folder="templates")
app.secret_key = "demo-secret-key-not-for-production"

# ---------------------------------------------------------------------------
# Demo credentials — fixed and deterministic for test repeatability
# ---------------------------------------------------------------------------
DEMO_EMAIL = "demo@example.com"
DEMO_PASSWORD = "DemoPass@123"

# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _validate_email(email: str) -> str:
    """Return an error message or empty string if valid."""
    if not email or not email.strip():
        return "Email address is required."
    if not _EMAIL_RE.match(email.strip()):
        return "Email address format is invalid."
    return ""


def _validate_password(password: str) -> str:
    """Return an error message or empty string if valid."""
    if not password:
        return "Password is required."
    return ""


def _check_credentials(email: str, password: str) -> str:
    """
    Validate credentials against the demo account.
    Returns an error string or "" on success.
    """
    email_err = _validate_email(email)
    if email_err:
        return email_err

    pwd_err = _validate_password(password)
    if pwd_err:
        return pwd_err

    if email.strip().lower() != DEMO_EMAIL.lower() or password != DEMO_PASSWORD:
        return "Invalid email or password. Please try again."

    return ""


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/", methods=["GET"])
def index():
    return redirect(url_for("login"))


@app.route("/login", methods=["GET"])
def login():
    return render_template("login.html", error=None)


@app.route("/login", methods=["POST"])
def login_post():
    email = request.form.get("email", "")
    password = request.form.get("password", "")

    error = _check_credentials(email, password)
    if error:
        return render_template("login.html", error=error), 200

    session["user"] = email
    return redirect(url_for("dashboard"))


@app.route("/dashboard")
def dashboard():
    user = session.get("user")
    if not user:
        return redirect(url_for("login"))
    return render_template("dashboard.html", user=user)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/health")
def health():
    """Health-check endpoint for tests."""
    return {"status": "ok", "app": "demo-login"}, 200


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("DEMO_PORT", 5000))
    print(f"\n  Demo Login App running at http://localhost:{port}")
    print(f"  Demo credentials: {DEMO_EMAIL} / {DEMO_PASSWORD}")
    print("  Press Ctrl+C to stop.\n")
    app.run(port=port, debug=False, use_reloader=False)

