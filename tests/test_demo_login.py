"""
tests/test_demo_login.py
------------------------
Deterministic tests for the Demo Login Application (Feature 8):
1. Valid login (demo@example.com / DemoPass@123) -> Success / Dashboard redirect
2. Invalid password -> "Invalid email or password. Please try again."
3. Empty email -> "Email address is required."
4. Empty password -> "Password is required."
5. Invalid email format -> "Email address format is invalid."

Tests verify actual assertions and do not mark as passed without verified conditions.
"""

import pytest
from app.demo.app import DEMO_EMAIL, DEMO_PASSWORD, app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


class TestDemoLoginApplication:

    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json["status"] == "ok"

    def test_valid_login(self, client):
        """Valid login scenario."""
        response = client.post(
            "/login",
            data={"email": DEMO_EMAIL, "password": DEMO_PASSWORD},
            follow_redirects=True,
        )
        assert response.status_code == 200
        html = response.data.decode("utf-8")
        assert "Welcome, demo@example.com!" in html
        assert "data-testid=\"welcome-message\"" in html

    def test_invalid_password(self, client):
        """Invalid password scenario."""
        response = client.post(
            "/login",
            data={"email": DEMO_EMAIL, "password": "WrongPassword999!"},
            follow_redirects=True,
        )
        assert response.status_code == 200
        html = response.data.decode("utf-8")
        assert "Invalid email or password. Please try again." in html
        assert "data-testid=\"error-message\"" in html

    def test_empty_email(self, client):
        """Empty email scenario."""
        response = client.post(
            "/login",
            data={"email": "", "password": DEMO_PASSWORD},
            follow_redirects=True,
        )
        assert response.status_code == 200
        html = response.data.decode("utf-8")
        assert "Email address is required." in html
        assert "data-testid=\"error-message\"" in html

    def test_empty_password(self, client):
        """Empty password scenario."""
        response = client.post(
            "/login",
            data={"email": DEMO_EMAIL, "password": ""},
            follow_redirects=True,
        )
        assert response.status_code == 200
        html = response.data.decode("utf-8")
        assert "Password is required." in html
        assert "data-testid=\"error-message\"" in html

    def test_invalid_email_format(self, client):
        """Invalid email format scenario."""
        response = client.post(
            "/login",
            data={"email": "not-an-email", "password": DEMO_PASSWORD},
            follow_redirects=True,
        )
        assert response.status_code == 200
        html = response.data.decode("utf-8")
        assert "Email address format is invalid." in html
        assert "data-testid=\"error-message\"" in html

