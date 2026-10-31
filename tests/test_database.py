"""
tests/test_database.py
----------------------
Unit tests for app/database/db.py:
- SQLite table initialization
- Run creation and completion
- Result storage and retrieval
- Aggregate statistics calculation
"""

import os
import pytest
from app.database.db import (
    complete_run,
    create_run,
    get_aggregate_stats,
    get_all_runs,
    get_results_for_run,
    initialise_db,
    save_result,
)


@pytest.fixture
def temp_db(tmp_path):
    db_file = str(tmp_path / "test_history_temp.db")
    initialise_db(db_file)
    return db_file


class TestDatabase:

    def test_create_and_get_run(self, temp_db):
        run_id = create_run(
            target_url="http://localhost:5000/login",
            project_name="Unit Test Run",
            environment="Local",
            db_path=temp_db,
        )
        assert run_id > 0

        runs = get_all_runs(db_path=temp_db)
        assert len(runs) == 1
        assert runs[0]["project_name"] == "Unit Test Run"
        assert runs[0]["target_url"] == "http://localhost:5000/login"

    def test_save_result_and_complete_run(self, temp_db):
        run_id = create_run(
            target_url="http://localhost:5000/login",
            project_name="Run with Results",
            db_path=temp_db,
        )

        res1 = {
            "test_case_id": "TC-001",
            "test_scenario": "Valid Login",
            "status": "PASSED",
            "expected_result": "Dashboard displayed",
            "actual_result": "Dashboard displayed",
            "duration_seconds": 1.2,
        }
        res2 = {
            "test_case_id": "TC-002",
            "test_scenario": "Invalid Password",
            "status": "FAILED",
            "expected_result": "Error displayed",
            "actual_result": "No error message",
            "error_message": "Element not found",
            "duration_seconds": 2.1,
        }

        save_result(run_id, res1, db_path=temp_db)
        save_result(run_id, res2, defect_report={"defect_title": "No error on invalid pass"}, db_path=temp_db)

        complete_run(run_id, [res1, res2], db_path=temp_db)

        results = get_results_for_run(run_id, db_path=temp_db)
        assert len(results) == 2
        assert results[0]["status"] == "PASSED"
        assert results[1]["status"] == "FAILED"
        assert results[1]["defect_report"]["defect_title"] == "No error on invalid pass"

        stats = get_aggregate_stats(db_path=temp_db)
        assert stats["total_runs"] == 1
        assert stats["total_tests"] == 2
        assert stats["passed"] == 1
        assert stats["failed"] == 1

