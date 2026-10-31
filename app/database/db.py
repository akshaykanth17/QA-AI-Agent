"""
database/db.py
--------------
SQLite persistence layer for test execution history.

Tables:
  test_runs      — One row per batch execution run.
  test_results   — One row per individual test case result within a run.

The database file is created automatically on first use.
"""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Generator, List, Optional


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_DEFAULT_DB_PATH = "test_history.db"


def get_db_path() -> str:
    return os.environ.get("TEST_DB_PATH", _DEFAULT_DB_PATH)


# ---------------------------------------------------------------------------
# Connection helper
# ---------------------------------------------------------------------------

@contextmanager
def _get_conn(db_path: Optional[str] = None) -> Generator[sqlite3.Connection, None, None]:
    path = db_path or get_db_path()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Schema initialisation
# ---------------------------------------------------------------------------

_CREATE_RUNS_TABLE = """
CREATE TABLE IF NOT EXISTS test_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_name    TEXT    NOT NULL DEFAULT 'Unnamed Project',
    target_url      TEXT    NOT NULL,
    environment     TEXT    NOT NULL DEFAULT 'Local',
    started_at      TEXT    NOT NULL,
    completed_at    TEXT,
    total           INTEGER NOT NULL DEFAULT 0,
    passed          INTEGER NOT NULL DEFAULT 0,
    failed          INTEGER NOT NULL DEFAULT 0,
    blocked         INTEGER NOT NULL DEFAULT 0,
    skipped         INTEGER NOT NULL DEFAULT 0,
    error_count     INTEGER NOT NULL DEFAULT 0
);
"""

_CREATE_RESULTS_TABLE = """
CREATE TABLE IF NOT EXISTS test_results (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          INTEGER NOT NULL REFERENCES test_runs(id),
    test_case_id    TEXT    NOT NULL,
    test_scenario   TEXT    NOT NULL,
    status          TEXT    NOT NULL,
    expected_result TEXT,
    actual_result   TEXT,
    error_message   TEXT,
    screenshot_path TEXT,
    logs            TEXT,
    duration_seconds REAL   DEFAULT 0.0,
    executed_at     TEXT,
    defect_report   TEXT    -- JSON blob from AI failure analysis
);
"""


def initialise_db(db_path: Optional[str] = None) -> None:
    """Create tables if they do not exist."""
    with _get_conn(db_path) as conn:
        conn.execute(_CREATE_RUNS_TABLE)
        conn.execute(_CREATE_RESULTS_TABLE)


# ---------------------------------------------------------------------------
# Public API — Runs
# ---------------------------------------------------------------------------

def create_run(
    target_url: str,
    project_name: str = "Unnamed Project",
    environment: str = "Local",
    db_path: Optional[str] = None,
) -> int:
    """
    Insert a new test run record and return its ID.

    Parameters
    ----------
    target_url : str
    project_name : str
    environment : str
    db_path : str, optional

    Returns
    -------
    int — the new run ID
    """
    initialise_db(db_path)
    with _get_conn(db_path) as conn:
        cursor = conn.execute(
            """INSERT INTO test_runs
               (project_name, target_url, environment, started_at)
               VALUES (?, ?, ?, ?)""",
            (project_name, target_url, environment, datetime.now(timezone.utc).isoformat()),
        )
        return cursor.lastrowid


def complete_run(run_id: int, results: List[Dict], db_path: Optional[str] = None) -> None:
    """
    Update a test run record with final counts and completion time.

    Parameters
    ----------
    run_id : int
    results : list of ExecutionResult.to_dict()
    """
    counts = {"PASSED": 0, "FAILED": 0, "BLOCKED": 0, "SKIPPED": 0, "ERROR": 0}
    for r in results:
        status = r.get("status", "ERROR")
        counts[status] = counts.get(status, 0) + 1

    with _get_conn(db_path) as conn:
        conn.execute(
            """UPDATE test_runs SET
               completed_at=?, total=?, passed=?, failed=?, blocked=?, skipped=?, error_count=?
               WHERE id=?""",
            (
                datetime.now(timezone.utc).isoformat(),
                len(results),
                counts["PASSED"],
                counts["FAILED"],
                counts["BLOCKED"],
                counts["SKIPPED"],
                counts["ERROR"],
                run_id,
            ),
        )


def get_all_runs(db_path: Optional[str] = None) -> List[Dict]:
    """Return all test runs, newest first."""
    initialise_db(db_path)
    with _get_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM test_runs ORDER BY id DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def get_run(run_id: int, db_path: Optional[str] = None) -> Optional[Dict]:
    """Return a single run record or None."""
    initialise_db(db_path)
    with _get_conn(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM test_runs WHERE id=?", (run_id,)
        ).fetchone()
        return dict(row) if row else None


# ---------------------------------------------------------------------------
# Public API — Results
# ---------------------------------------------------------------------------

def save_result(
    run_id: int,
    result: Dict,
    defect_report: Optional[Dict] = None,
    db_path: Optional[str] = None,
) -> int:
    """
    Insert a single test result record.

    Parameters
    ----------
    run_id : int
    result : dict from ExecutionResult.to_dict()
    defect_report : dict, optional — from ai_service.analyse_failure()

    Returns
    -------
    int — new result row ID
    """
    initialise_db(db_path)
    with _get_conn(db_path) as conn:
        cursor = conn.execute(
            """INSERT INTO test_results
               (run_id, test_case_id, test_scenario, status, expected_result,
                actual_result, error_message, screenshot_path, logs,
                duration_seconds, executed_at, defect_report)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run_id,
                result.get("test_case_id", ""),
                result.get("test_scenario", ""),
                result.get("status", "ERROR"),
                result.get("expected_result", ""),
                result.get("actual_result", ""),
                result.get("error_message", ""),
                result.get("screenshot_path", ""),
                result.get("logs", ""),
                result.get("duration_seconds", 0.0),
                result.get("executed_at", ""),
                json.dumps(defect_report) if defect_report else None,
            ),
        )
        return cursor.lastrowid


def get_results_for_run(run_id: int, db_path: Optional[str] = None) -> List[Dict]:
    """Return all test results for a given run."""
    initialise_db(db_path)
    with _get_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM test_results WHERE run_id=? ORDER BY id ASC",
            (run_id,),
        ).fetchall()
        results = []
        for row in rows:
            d = dict(row)
            if d.get("defect_report"):
                try:
                    d["defect_report"] = json.loads(d["defect_report"])
                except Exception:
                    pass
            results.append(d)
        return results


def get_aggregate_stats(db_path: Optional[str] = None) -> Dict:
    """
    Return aggregate statistics across all runs.

    Returns
    -------
    dict with keys: total_runs, total_tests, passed, failed, blocked, skipped, error_count
    """
    initialise_db(db_path)
    with _get_conn(db_path) as conn:
        row = conn.execute(
            """SELECT
               COUNT(*) as total_runs,
               SUM(total) as total_tests,
               SUM(passed) as passed,
               SUM(failed) as failed,
               SUM(blocked) as blocked,
               SUM(skipped) as skipped,
               SUM(error_count) as error_count
               FROM test_runs"""
        ).fetchone()
        if row:
            return {k: (v or 0) for k, v in dict(row).items()}
        return {k: 0 for k in ["total_runs", "total_tests", "passed", "failed", "blocked", "skipped", "error_count"]}

