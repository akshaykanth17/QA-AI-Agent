"""
tests/test_requirement_analysis.py
-----------------------------------
Unit tests for app/requirement_analysis.py
"""

import pytest
from app.requirement_analysis import (
    AnalysisResult,
    RequirementItem,
    analyse_requirements,
    extract_text_from_file,
)


class TestAnalyseRequirements:

    def test_empty_string_returns_empty_result(self):
        result = analyse_requirements("")
        assert isinstance(result, AnalysisResult)
        assert result.requirements == []

    def test_single_sentence_creates_one_requirement(self):
        result = analyse_requirements("The system shall allow users to log in.")
        assert len(result.requirements) == 1
        assert result.requirements[0].req_id == "REQ-001"

    def test_validation_rule_detected(self):
        text = "Passwords must be at least 8 characters."
        result = analyse_requirements(text)
        assert len(result.validation_rules) > 0

    def test_ambiguity_detected(self):
        text = "The system should respond soon."
        result = analyse_requirements(text)
        assert any("soon" in a.lower() for a in result.ambiguities)


class TestExtractTextFromFile:

    def test_txt_file_extraction(self):
        content = "This is a test requirement."
        file_bytes = content.encode("utf-8")
        result = extract_text_from_file(file_bytes, "requirements.txt")
        assert result == content

    def test_unsupported_extension_raises_value_error(self):
        with pytest.raises(ValueError, match="Unsupported file type"):
            extract_text_from_file(b"data", "file.docx")

