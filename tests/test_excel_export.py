"""
tests/test_excel_export.py
----------------------------
Unit tests for app/excel_export.py
"""

import io
import json
import pytest
from openpyxl import load_workbook

from app.excel_export import build_excel
from app.requirement_analysis import analyse_requirements
from app.test_case_generator import parse_ai_response


def _sample_test_cases():
    data = json.dumps([
        {
            "test_case_id": "TC-001",
            "requirement_id": "REQ-001",
            "test_scenario": "Login with valid credentials",
            "preconditions": "User is registered",
            "test_steps": "1. Open login page\n2. Enter email\n3. Enter password\n4. Click Login",
            "test_data": "Email: user@example.com, Password: ValidPass@1",
            "expected_result": "Dashboard is displayed",
            "priority": "High",
            "test_type": "Positive",
            "automation_feasibility": "High",
        }
    ])
    return parse_ai_response(data)


def _sample_analysis():
    text = (
        "The system shall allow users to log in with a valid email and password.\n"
        "Passwords must be at least 8 characters long."
    )
    return analyse_requirements(text)


class TestBuildExcel:

    def test_returns_bytes_and_valid_format(self):
        result = build_excel(_sample_test_cases(), _sample_analysis())
        assert isinstance(result, bytes)
        wb = load_workbook(io.BytesIO(result))
        assert "Test Cases" in wb.sheetnames
        assert "Requirement Analysis" in wb.sheetnames

    def test_with_execution_results(self):
        exec_results = [
            {
                "test_case_id": "TC-001",
                "test_scenario": "Login with valid credentials",
                "status": "PASSED",
                "expected_result": "Dashboard is displayed",
                "actual_result": "Dashboard is displayed",
                "error_message": "",
                "screenshot_path": "",
                "duration_seconds": 1.5,
                "executed_at": "2026-10-31T10:00:00",
            }
        ]
        result = build_excel(
            test_cases=_sample_test_cases(),
            analysis=_sample_analysis(),
            execution_results=exec_results,
        )
        wb = load_workbook(io.BytesIO(result))
        assert "Execution Results" in wb.sheetnames
        ws = wb["Execution Results"]
        assert ws.cell(row=3, column=3).value == "PASSED"

