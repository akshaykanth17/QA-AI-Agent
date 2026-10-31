"""
tests/test_test_case_generator.py
-----------------------------------
Unit tests for app/test_case_generator.py
"""

import json
import pytest
import pandas as pd

from app.test_case_generator import (
    TestCase,
    filter_test_cases,
    parse_ai_response,
    generate_heuristic_test_cases,
    test_cases_to_dataframe as cases_to_df,
)


def _make_tc_dict(**overrides):
    base = {
        "test_case_id": "TC-001",
        "requirement_id": "REQ-001",
        "test_scenario": "Verify user can log in with valid credentials",
        "preconditions": "User is registered",
        "test_steps": "1. Navigate to login\n2. Enter credentials\n3. Click Login",
        "test_data": "Email: user@example.com, Password: ValidPass@1",
        "expected_result": "User is redirected to dashboard",
        "priority": "High",
        "test_type": "Positive",
        "automation_feasibility": "High",
    }
    base.update(overrides)
    return base


class TestParseAiResponse:

    def test_valid_json_array_parses(self):
        raw = json.dumps([_make_tc_dict()])
        result = parse_ai_response(raw)
        assert len(result) == 1
        assert isinstance(result[0], TestCase)
        assert result[0].automation_feasibility == "High"

    def test_strips_markdown_code_fence(self):
        raw = "```json\n" + json.dumps([_make_tc_dict()]) + "\n```"
        result = parse_ai_response(raw)
        assert len(result) == 1

    def test_filter_test_cases(self):
        cases = [
            _make_tc_dict(test_case_id="TC-001", priority="High", test_scenario="Valid login"),
            _make_tc_dict(test_case_id="TC-002", priority="Low", test_scenario="Password reset"),
        ]
        df = cases_to_df(parse_ai_response(json.dumps(cases)))
        filtered = filter_test_cases(df, priority_filter=["High"])
        assert len(filtered) == 1
        assert filtered["Test Case ID"].iloc[0] == "TC-001"

    def test_heuristic_generator_auth(self):
        cases = generate_heuristic_test_cases("Users must log in using an email and password.")
        assert len(cases) >= 5
        types = {c.test_type for c in cases}
        assert "Positive" in types
        assert "Negative" in types
        assert "Validation" in types

    def test_heuristic_generator_empty_fallback(self):
        cases = generate_heuristic_test_cases("")
        assert len(cases) >= 2
        assert cases[0].test_case_id == "TC-001"

