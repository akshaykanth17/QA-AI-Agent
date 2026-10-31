"""
tests/test_ai_service.py
-------------------------
Unit tests for app/ai_service.py:
- API key & model getters
- Mocked test case generation
- Mocked failure analysis
"""

import os
import pytest
from unittest.mock import MagicMock, patch


class TestGetApiKey:

    def test_raises_when_env_var_missing(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        from app.ai_service import get_api_key
        with pytest.raises(EnvironmentError, match="OPENAI_API_KEY"):
            get_api_key()

    def test_raises_when_env_var_is_placeholder(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-your-key-here")
        from app.ai_service import get_api_key
        with pytest.raises(EnvironmentError):
            get_api_key()

    def test_returns_key_when_set(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key-abc123")
        from app.ai_service import get_api_key
        assert get_api_key() == "sk-test-key-abc123"


class TestGetModel:

    def test_returns_default_model(self, monkeypatch):
        monkeypatch.delenv("OPENAI_MODEL", raising=False)
        from app.ai_service import get_model
        assert get_model() == "gpt-4o-mini"

    def test_returns_configured_model(self, monkeypatch):
        monkeypatch.setenv("OPENAI_MODEL", "gpt-4o")
        from app.ai_service import get_model
        assert get_model() == "gpt-4o"


class TestAiServiceMocked:

    def test_generate_test_cases(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-fake-key")

        fake_content = '[{"test_case_id": "TC-001", "test_scenario": "Test"}]'
        mock_choice = MagicMock()
        mock_choice.message.content = fake_content
        mock_response = MagicMock(choices=[mock_choice])

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        with patch("app.ai_service.OpenAI", return_value=mock_client):
            from app.ai_service import generate_test_cases
            from app.requirement_analysis import AnalysisResult
            res = generate_test_cases("Requirement text", AnalysisResult())
            assert res == fake_content

    def test_analyse_failure(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-fake-key")

        fake_json = (
            '{"failure_summary": "Login failed with 401", '
            '"root_causes": ["[AI Hypothesis] Bad password"], '
            '"defect_title": "Login Error", '
            '"severity": "High", '
            '"steps_to_reproduce": "1. Enter bad pass", '
            '"expected_result": "Error", '
            '"actual_result": "401", '
            '"ai_confidence": "High"}'
        )
        mock_choice = MagicMock()
        mock_choice.message.content = fake_json
        mock_response = MagicMock(choices=[mock_choice])

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        with patch("app.ai_service.OpenAI", return_value=mock_client):
            from app.ai_service import analyse_failure
            defect = analyse_failure(
                test_case_id="TC-001",
                test_scenario="Login test",
                expected_result="Dashboard",
                actual_result="Error",
                error_message="401 Unauthorized",
                log_snippet="Logs here",
            )
            assert defect["defect_title"] == "Login Error"
            assert defect["severity"] == "High"
            assert "[AI Hypothesis]" in defect["root_causes"][0]

