"""
test_case_generator.py
----------------------
Transforms the AI model's JSON output into structured TestCase objects
and provides utilities for filtering and searching.

Extended from v1: added automation_feasibility field.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pandas as pd


# ---------------------------------------------------------------------------
# Data structure
# ---------------------------------------------------------------------------

@dataclass
class TestCase:
    """A single manual / automated test case."""
    __test__ = False  # Prevent pytest from collecting this data class as a test

    test_case_id: str
    requirement_id: str
    test_scenario: str
    preconditions: str
    test_steps: str
    test_data: str
    expected_result: str
    priority: str           # High | Medium | Low
    test_type: str          # Positive | Negative | Boundary | Edge Case | Validation | Error Handling
    automation_feasibility: str = "Medium"  # High | Medium | Low

    def to_dict(self) -> Dict[str, Any]:
        return {
            "Test Case ID": self.test_case_id,
            "Requirement ID": self.requirement_id,
            "Test Scenario": self.test_scenario,
            "Preconditions": self.preconditions,
            "Test Steps": self.test_steps,
            "Test Data": self.test_data,
            "Expected Result": self.expected_result,
            "Priority": self.priority,
            "Test Type": self.test_type,
            "Automation Feasibility": self.automation_feasibility,
        }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

REQUIRED_KEYS = {
    "test_case_id",
    "requirement_id",
    "test_scenario",
    "preconditions",
    "test_steps",
    "test_data",
    "expected_result",
    "priority",
    "test_type",
}

VALID_PRIORITIES = {"High", "Medium", "Low"}
VALID_TEST_TYPES = {
    "Positive",
    "Negative",
    "Boundary",
    "Edge Case",
    "Validation",
    "Error Handling",
}
VALID_AUTOMATION_FEASIBILITY = {"High", "Medium", "Low"}


def parse_ai_response(ai_response: str) -> List[TestCase]:
    """
    Parse the AI model's response string into a list of :class:`TestCase` objects.

    The AI is instructed to return a JSON array.  This function handles
    minor formatting issues (markdown code fences, trailing commas, etc.).

    Parameters
    ----------
    ai_response:
        Raw string from the AI model.

    Returns
    -------
    List of validated TestCase objects.

    Raises
    ------
    ValueError
        If the response cannot be parsed or contains no valid test cases.
    """
    if not ai_response or not ai_response.strip():
        raise ValueError("AI returned an empty response.")

    json_str = _extract_json(ai_response)
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"AI response is not valid JSON: {exc}\n\nRaw response:\n{ai_response[:500]}"
        ) from exc

    if not isinstance(data, list):
        # Sometimes the AI wraps it: {"test_cases": [...]}
        if isinstance(data, dict):
            for key in ("test_cases", "testCases", "cases", "results"):
                if key in data and isinstance(data[key], list):
                    data = data[key]
                    break
            else:
                raise ValueError("AI response JSON is an object but contains no test cases array.")
        else:
            raise ValueError("AI response JSON must be an array of test case objects.")

    test_cases: List[TestCase] = []
    for idx, item in enumerate(data):
        if not isinstance(item, dict):
            continue
        tc = _dict_to_test_case(item, fallback_id=f"TC-{idx + 1:03d}")
        if tc:
            test_cases.append(tc)

    if not test_cases:
        raise ValueError("No valid test cases could be extracted from the AI response.")

    return test_cases


def test_cases_to_dataframe(test_cases: List[TestCase]) -> pd.DataFrame:
    """Convert a list of TestCase objects to a pandas DataFrame."""
    _columns = [
        "Test Case ID", "Requirement ID", "Test Scenario", "Preconditions",
        "Test Steps", "Test Data", "Expected Result", "Priority", "Test Type",
        "Automation Feasibility",
    ]
    if not test_cases:
        return pd.DataFrame(columns=_columns)
    return pd.DataFrame([tc.to_dict() for tc in test_cases])


def filter_test_cases(
    df: pd.DataFrame,
    search_query: str = "",
    priority_filter: Optional[List[str]] = None,
    type_filter: Optional[List[str]] = None,
) -> pd.DataFrame:
    """
    Filter a test-case DataFrame by free-text search, priority, and test type.

    Parameters
    ----------
    df:
        Full test-case DataFrame.
    search_query:
        Case-insensitive substring search across all columns.
    priority_filter:
        List of priorities to keep (e.g. ["High", "Medium"]).
    type_filter:
        List of test types to keep.

    Returns
    -------
    Filtered DataFrame (original unchanged).
    """
    result = df.copy()

    if search_query and search_query.strip():
        query = search_query.strip().lower()
        mask = result.apply(
            lambda row: row.astype(str).str.lower().str.contains(query, regex=False).any(),
            axis=1,
        )
        result = result[mask]

    if priority_filter:
        result = result[result["Priority"].isin(priority_filter)]

    if type_filter:
        result = result[result["Test Type"].isin(type_filter)]

    return result


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> str:
    """Strip markdown code fences and isolate the JSON portion."""
    # Remove ```json ... ``` or ``` ... ```
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = text.replace("```", "")

    # Find the first '[' and last ']'
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        return text[start: end + 1]

    # Fallback: try the whole string
    return text.strip()


def _dict_to_test_case(data: Dict[str, Any], fallback_id: str) -> Optional[TestCase]:
    """Convert a raw dict to a TestCase, normalising keys and values."""
    # Normalise keys: lower-case + replace spaces/hyphens with underscores
    normalised: Dict[str, str] = {}
    for k, v in data.items():
        norm_key = k.lower().replace(" ", "_").replace("-", "_")
        normalised[norm_key] = str(v).strip() if v is not None else ""

    # Map common key aliases
    _apply_aliases(normalised)

    # Ensure all required keys exist
    for key in REQUIRED_KEYS:
        if key not in normalised or not normalised[key]:
            normalised[key] = _default_value(key, fallback_id)

    # Sanitise controlled-vocabulary fields
    priority = _normalise_priority(normalised["priority"])
    test_type = _normalise_test_type(normalised["test_type"])
    automation_feasibility = _normalise_priority(
        normalised.get("automation_feasibility", "Medium")
    )

    return TestCase(
        test_case_id=normalised["test_case_id"],
        requirement_id=normalised["requirement_id"],
        test_scenario=normalised["test_scenario"],
        preconditions=normalised["preconditions"],
        test_steps=normalised["test_steps"],
        test_data=normalised["test_data"],
        expected_result=normalised["expected_result"],
        priority=priority,
        test_type=test_type,
        automation_feasibility=automation_feasibility,
    )


_KEY_ALIASES: Dict[str, str] = {
    "id": "test_case_id",
    "tc_id": "test_case_id",
    "case_id": "test_case_id",
    "req_id": "requirement_id",
    "scenario": "test_scenario",
    "steps": "test_steps",
    "data": "test_data",
    "expected": "expected_result",
    "result": "expected_result",
    "type": "test_type",
    "pre_conditions": "preconditions",
    "pre_condition": "preconditions",
    "automation": "automation_feasibility",
    "feasibility": "automation_feasibility",
}


def _apply_aliases(d: Dict[str, str]) -> None:
    for alias, canonical in _KEY_ALIASES.items():
        if alias in d and canonical not in d:
            d[canonical] = d[alias]


def _default_value(key: str, fallback_id: str) -> str:
    defaults = {
        "test_case_id": fallback_id,
        "requirement_id": "REQ-001",
        "test_scenario": "Unspecified scenario",
        "preconditions": "None",
        "test_steps": "See test scenario",
        "test_data": "N/A",
        "expected_result": "System behaves as specified",
        "priority": "Medium",
        "test_type": "Positive",
    }
    return defaults.get(key, "N/A")


def _normalise_priority(value: str) -> str:
    title = value.strip().title()
    if title in VALID_PRIORITIES:
        return title
    lower = value.lower()
    if "high" in lower or "critical" in lower:
        return "High"
    if "low" in lower or "minor" in lower:
        return "Low"
    return "Medium"


def _normalise_test_type(value: str) -> str:
    title = value.strip().title()
    if title in VALID_TEST_TYPES:
        return title
    lower = value.lower()
    mapping = {
        "positive": "Positive",
        "happy": "Positive",
        "negative": "Negative",
        "invalid": "Negative",
        "boundary": "Boundary",
        "bva": "Boundary",
        "edge": "Edge Case",
        "validation": "Validation",
        "field": "Validation",
        "error": "Error Handling",
        "exception": "Error Handling",
    }
    for keyword, canonical in mapping.items():
        if keyword in lower:
            return canonical
    return "Positive"


def generate_heuristic_test_cases(
    requirements_text: str = "",
    analysis: Optional[Any] = None,
) -> List[TestCase]:
    """Generate deterministic, rule-based test cases without requiring an AI/OpenAI key.

    Analyzes requirements and validation rules to produce comprehensive positive,
    negative, validation, and boundary test cases.
    """
    if analysis is None and requirements_text.strip():
        from app.requirement_analysis import analyse_requirements
        analysis = analyse_requirements(requirements_text)

    cases: List[TestCase] = []
    tc_index = 1

    text_lower = (requirements_text + " " + (analysis.raw_text if analysis else "")).lower()
    is_auth_related = any(kw in text_lower for kw in ["login", "sign in", "signin", "auth", "password", "credential", "user"])

    if is_auth_related:
        cases.append(
            TestCase(
                test_case_id=f"TC-{tc_index:03d}",
                requirement_id="REQ-AUTH-01",
                test_scenario="User authenticates successfully with valid credentials",
                preconditions="User is on the target login page",
                test_steps="1. Navigate to target URL\n2. Enter valid username/email\n3. Enter valid password\n4. Click 'Sign In' or 'Login'",
                test_data="Username: standard_user, Password: ValidPassword@123",
                expected_result="Authentication successful. User redirected to dashboard / landing page.",
                priority="High",
                test_type="Positive",
                automation_feasibility="High",
            )
        )
        tc_index += 1

        cases.append(
            TestCase(
                test_case_id=f"TC-{tc_index:03d}",
                requirement_id="REQ-AUTH-02",
                test_scenario="User submits incorrect or invalid password",
                preconditions="User is on the target login page",
                test_steps="1. Enter valid username/email\n2. Enter incorrect password 'WrongPassword!99'\n3. Click 'Sign In' or 'Login'",
                test_data="Username: standard_user, Password: WrongPassword!99",
                expected_result="Authentication rejected. Error message displayed indicating invalid credentials.",
                priority="High",
                test_type="Negative",
                automation_feasibility="High",
            )
        )
        tc_index += 1

        cases.append(
            TestCase(
                test_case_id=f"TC-{tc_index:03d}",
                requirement_id="REQ-AUTH-03",
                test_scenario="User attempts submission with empty required fields",
                preconditions="User is on the target login page",
                test_steps="1. Leave username/email field empty\n2. Enter password\n3. Click 'Sign In' or 'Login'",
                test_data="Username: , Password: ValidPassword@123",
                expected_result="Submission blocked. Validation error displayed requesting required fields.",
                priority="Medium",
                test_type="Validation",
                automation_feasibility="High",
            )
        )
        tc_index += 1

        cases.append(
            TestCase(
                test_case_id=f"TC-{tc_index:03d}",
                requirement_id="REQ-AUTH-04",
                test_scenario="User enters malformed email or username format",
                preconditions="User is on the target login page",
                test_steps="1. Enter malformed username 'invalid_user@@domain..com'\n2. Enter valid password\n3. Click 'Sign In' or 'Login'",
                test_data="Username: invalid_user@@domain..com, Password: ValidPassword@123",
                expected_result="Validation error displayed indicating invalid format.",
                priority="Medium",
                test_type="Negative",
                automation_feasibility="High",
            )
        )
        tc_index += 1

        cases.append(
            TestCase(
                test_case_id=f"TC-{tc_index:03d}",
                requirement_id="REQ-AUTH-05",
                test_scenario="User enters special characters or SQL injection strings",
                preconditions="User is on the target login page",
                test_steps="1. Enter input with special characters \"' OR '1'='1\"\n2. Enter password\n3. Click 'Sign In' or 'Login'",
                test_data="Username: ' OR '1'='1, Password: TestPassword",
                expected_result="System safely handles special characters without crashing; rejects unauthorized access.",
                priority="Medium",
                test_type="Boundary",
                automation_feasibility="High",
            )
        )
        tc_index += 1

    # If there are specific requirements extracted, generate corresponding cases
    if analysis and analysis.requirements:
        for req in analysis.requirements:
            if is_auth_related and tc_index > 5:
                break
            cases.append(
                TestCase(
                    test_case_id=f"TC-{tc_index:03d}",
                    requirement_id=req.req_id,
                    test_scenario=f"Verify requirement: {req.description[:60]}",
                    preconditions="System is in standard initial state",
                    test_steps=f"1. Perform action specified in {req.req_id}\n2. Verify system response",
                    test_data="Standard test dataset",
                    expected_result=f"System satisfies requirement: {req.description[:80]}",
                    priority="High" if req.category == "functional" else "Medium",
                    test_type="Positive" if req.category == "functional" else "Validation",
                    automation_feasibility="High",
                )
            )
            tc_index += 1

    # Fallback if nothing was generated
    if not cases:
        cases = [
            TestCase(
                test_case_id="TC-001",
                requirement_id="REQ-GEN-01",
                test_scenario="Verify primary page workflow with valid inputs",
                preconditions="Target application is loaded",
                test_steps="1. Navigate to target URL\n2. Provide valid inputs into form fields\n3. Click submit",
                test_data="Standard valid test data",
                expected_result="Action succeeds and confirmation is displayed.",
                priority="High",
                test_type="Positive",
                automation_feasibility="High",
            ),
            TestCase(
                test_case_id="TC-002",
                requirement_id="REQ-GEN-02",
                test_scenario="Verify field validation when mandatory inputs are omitted",
                preconditions="Target application is loaded",
                test_steps="1. Navigate to target URL\n2. Leave mandatory fields blank\n3. Click submit",
                test_data="Empty fields",
                expected_result="Validation error displayed indicating missing fields.",
                priority="Medium",
                test_type="Validation",
                automation_feasibility="High",
            ),
        ]

    return cases

