"""
tests/test_runner_evaluation.py
--------------------------------
Tests for Playwright runner test outcome evaluation:
Verifies that expected results (both positive and negative phrasing)
are correctly asserted against actual browser outcomes.
"""

import pytest
from app.browser.runner import _evaluate_login_outcome, _parse_credentials


class TestRunnerOutcomeEvaluation:

    def test_user_scenario_login_should_not_success(self):
        """User's exact scenario: 'login should not success' with email format error."""
        actual, status = _evaluate_login_outcome(
            logged_in=False,
            error_msg="Email address format is invalid.",
            expected_result="login should not success",
            test_type="Negative",
        )
        assert status == "PASSED"
        assert "Email address format is invalid." in actual

    def test_negative_phrasings_pass_on_error(self):
        """Various negative expected result phrasing should all pass when error occurs."""
        phrasings = [
            "login should not success",
            "Login should fail",
            "User should not be able to log in",
            "Invalid credentials error message is displayed",
            "System rejects login",
            "Should not log in",
            "Unsuccessful login",
            "Error displayed",
            "Cannot log in",
        ]
        for phrase in phrasings:
            _, status = _evaluate_login_outcome(
                logged_in=False,
                error_msg="Invalid email or password.",
                expected_result=phrase,
                test_type="Negative",
            )
            assert status == "PASSED", f"Failed for phrase: '{phrase}'"

    def test_positive_phrasings_pass_on_login(self):
        """Positive login should pass when user is logged in."""
        phrasings = [
            "Login successful. Dashboard is displayed.",
            "User redirected to welcome page",
            "Dashboard displayed",
            "Successful login",
        ]
        for phrase in phrasings:
            _, status = _evaluate_login_outcome(
                logged_in=True,
                error_msg="",
                expected_result=phrase,
                test_type="Positive",
            )
            assert status == "PASSED", f"Failed for phrase: '{phrase}'"

    def test_expected_success_fails_when_error_occurs(self):
        """If test expects success but error occurs, test must fail."""
        _, status = _evaluate_login_outcome(
            logged_in=False,
            error_msg="Invalid credentials",
            expected_result="Login successful. Dashboard is displayed.",
            test_type="Positive",
        )
        assert status == "FAILED"

    def test_user_scenario_expected_success_actual_failed_must_be_failed(self):
        """User's exact scenario: Expected success, but login failed with 'Email address is required.' -> MUST BE FAILED!"""
        actual, status = _evaluate_login_outcome(
            logged_in=False,
            error_msg="Email address is required.",
            expected_result="Login successful. Dashboard / landing page is displayed.",
            test_type="Boundary",  # Even if type was accidentally set to Boundary
        )
        assert status == "FAILED"
        assert "Email address is required." in actual

    def test_expected_failure_fails_if_login_succeeds(self):
        """If test expects rejection (security test), but login succeeds, test must fail."""
        _, status = _evaluate_login_outcome(
            logged_in=True,
            error_msg="",
            expected_result="login should not success",
            test_type="Negative",
        )
        assert status == "FAILED"

    def test_parse_credentials_from_steps(self):
        """Credentials specified inside steps should be extracted."""
        email, pwd = _parse_credentials(
            test_data="N/A",
            test_steps="1. Enter email 'test@domain.com'\n2. Enter password 'Pass123!'",
        )
        assert email == "test@domain.com"
        assert pwd == "Pass123!"

    def test_execute_user_steps_only_performs_specified_actions(self):
        """If user only specifies entering username, submit button must NOT be clicked."""
        from unittest.mock import MagicMock
        from app.browser.runner import _execute_user_steps
        from app.test_case_generator import TestCase

        mock_page = MagicMock()
        mock_locator = MagicMock()
        mock_locator.first = mock_locator
        mock_locator.count.return_value = 1
        mock_page.locator.return_value = mock_locator

        logs = []
        tc = TestCase(
            test_case_id="TC-001",
            requirement_id="REQ-001",
            test_scenario="enter the username",
            preconditions="On login page",
            test_steps="1. Enter email 'demo@example.com'",
            test_data="N/A",
            expected_result="Username is entered",
            priority="High",
            test_type="Positive",
        )

        actual, status = _execute_user_steps(mock_page, tc, "http://localhost:5000/login", logs.append)

        assert status == "PASSED"
        assert "entered username/email 'demo@example.com'" in actual
        assert "form was not submitted" in actual
        # Verify submit button was NOT clicked!
        mock_locator.click.assert_not_called()

    def test_user_step_enter_valid_name_fills_default_email(self):
        """User wrote 'enter valid name' — must infer and type default valid email."""
        from unittest.mock import MagicMock
        from app.browser.runner import _execute_user_steps
        from app.test_case_generator import TestCase

        mock_page = MagicMock()
        mock_locator = MagicMock()
        mock_locator.first = mock_locator
        mock_locator.count.return_value = 1
        mock_page.locator.return_value = mock_locator

        logs = []
        tc = TestCase(
            test_case_id="TC-001",
            requirement_id="REQ-001",
            test_scenario="enter valid name",
            preconditions="On login page",
            test_steps="enter valid name",
            test_data="N/A",
            expected_result="Valid name is entered",
            priority="High",
            test_type="Positive",
        )

        actual, status = _execute_user_steps(mock_page, tc, "http://localhost:5000/login", logs.append)

        assert status == "PASSED"
        assert "demo@example.com" in actual
        mock_locator.fill.assert_called_with("demo@example.com")
        mock_locator.click.assert_not_called()



