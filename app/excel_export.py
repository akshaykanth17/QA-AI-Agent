"""
excel_export.py
---------------
Builds a formatted Excel workbook with multiple worksheets:
  1. Test Cases           — all generated test cases as a styled table
  2. Requirement Analysis — requirements, validation rules, ambiguities
  3. Execution Results    — actual run results, pass/fail status, evidence references (optional)
"""

from __future__ import annotations

import io
from typing import Any, Dict, List, Optional

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import (
    Alignment,
    Border,
    Font,
    PatternFill,
    Side,
)
from openpyxl.utils import get_column_letter

from app.requirement_analysis import AnalysisResult
from app.test_case_generator import TestCase, test_cases_to_dataframe


# ---------------------------------------------------------------------------
# Colour palette
# ---------------------------------------------------------------------------

_HEADER_BG = "1F4E79"    # Dark navy
_HEADER_FG = "FFFFFF"    # White
_ROW_ALT_BG = "D6E4F0"   # Light blue
_HIGH_BG = "FFD7D7"      # Soft red for High-priority rows
_MED_BG = "FFF3CD"       # Soft amber for Medium-priority rows
_LOW_BG = "D4EDDA"       # Soft green for Low-priority rows
_SECTION_BG = "2E75B6"   # Medium blue for section headers

_PASS_BG = "D4EDDA"
_FAIL_BG = "FFD7D7"
_BLOCKED_BG = "FFF3CD"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_excel(
    test_cases: List[TestCase],
    analysis: Optional[AnalysisResult] = None,
    execution_results: Optional[List[Dict[str, Any]]] = None,
    project_name: str = "AI Software Testing Agent",
) -> bytes:
    """
    Build and return a formatted Excel workbook as raw bytes.

    Parameters
    ----------
    test_cases:
        List of generated test cases.
    analysis:
        Structured requirement analysis result (optional).
    execution_results:
        Optional list of execution result dictionaries.
    project_name:
        Project or application name for report metadata.

    Returns
    -------
    Bytes of the .xlsx workbook (ready to write to disk or stream).
    """
    wb = Workbook()

    # --- Sheet 1: Test Cases -------------------------------------------------
    ws_tc = wb.active
    ws_tc.title = "Test Cases"
    _write_test_cases_sheet(ws_tc, test_cases, project_name)

    # --- Sheet 2: Execution Results (if available) ---------------------------
    if execution_results:
        ws_exec = wb.create_sheet(title="Execution Results")
        _write_execution_results_sheet(ws_exec, execution_results, project_name)

    # --- Sheet 3: Requirement Analysis ---------------------------------------
    if analysis:
        ws_ra = wb.create_sheet(title="Requirement Analysis")
        _write_analysis_sheet(ws_ra, analysis)

    # Serialise
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Sheet builders
# ---------------------------------------------------------------------------

def _write_test_cases_sheet(ws, test_cases: List[TestCase], project_name: str) -> None:
    """Populate the Test Cases worksheet."""
    df = test_cases_to_dataframe(test_cases)
    columns = list(df.columns)

    if not columns:
        ws.cell(row=1, column=1, value="No test cases generated.")
        return

    # Title row
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(columns))
    title_cell = ws.cell(row=1, column=1, value=f"{project_name} — AI-Generated Test Cases")
    _style_title(title_cell)
    ws.row_dimensions[1].height = 30

    # Header row (row 2)
    for col_idx, col_name in enumerate(columns, start=1):
        cell = ws.cell(row=2, column=col_idx, value=col_name)
        _style_header(cell)
    ws.row_dimensions[2].height = 22

    # Data rows
    priority_fills = {
        "High": PatternFill("solid", fgColor=_HIGH_BG),
        "Medium": PatternFill("solid", fgColor=_MED_BG),
        "Low": PatternFill("solid", fgColor=_LOW_BG),
    }
    alt_fill = PatternFill("solid", fgColor=_ROW_ALT_BG)

    for row_idx, row in enumerate(df.itertuples(index=False), start=3):
        priority_val = getattr(row, "Priority", "Medium")
        row_fill = priority_fills.get(priority_val, alt_fill)

        for col_idx, value in enumerate(row, start=1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            cell.fill = row_fill
            cell.alignment = Alignment(wrap_text=True, vertical="top")
            cell.border = _thin_border()
            cell.font = Font(size=10)

    # Column widths
    col_widths = {
        "Test Case ID": 14,
        "Requirement ID": 16,
        "Test Scenario": 40,
        "Preconditions": 30,
        "Test Steps": 45,
        "Test Data": 25,
        "Expected Result": 40,
        "Priority": 12,
        "Test Type": 16,
        "Automation Feasibility": 20,
    }
    for col_idx, col_name in enumerate(columns, start=1):
        ws.column_dimensions[get_column_letter(col_idx)].width = col_widths.get(col_name, 20)

    ws.freeze_panes = ws.cell(row=3, column=1)
    ws.auto_filter.ref = f"A2:{get_column_letter(len(columns))}2"


def _write_execution_results_sheet(ws, results: List[Dict[str, Any]], project_name: str) -> None:
    """Populate the Execution Results worksheet."""
    headers = [
        "Test Case ID",
        "Test Scenario",
        "Status",
        "Expected Result",
        "Actual Result",
        "Error Message",
        "Screenshot Path",
        "Duration (s)",
        "Executed At",
    ]

    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
    title_cell = ws.cell(row=1, column=1, value=f"{project_name} — Browser Automation Results")
    _style_title(title_cell)
    ws.row_dimensions[1].height = 30

    for col_idx, h in enumerate(headers, start=1):
        cell = ws.cell(row=2, column=col_idx, value=h)
        _style_header(cell)
    ws.row_dimensions[2].height = 22

    status_fills = {
        "PASSED": PatternFill("solid", fgColor=_PASS_BG),
        "FAILED": PatternFill("solid", fgColor=_FAIL_BG),
        "BLOCKED": PatternFill("solid", fgColor=_BLOCKED_BG),
        "SKIPPED": PatternFill("solid", fgColor=_BLOCKED_BG),
        "ERROR": PatternFill("solid", fgColor=_FAIL_BG),
    }
    default_fill = PatternFill("solid", fgColor="FFFFFF")

    for row_idx, r in enumerate(results, start=3):
        status = str(r.get("status", "UNKNOWN")).upper()
        row_fill = status_fills.get(status, default_fill)

        vals = [
            r.get("test_case_id", ""),
            r.get("test_scenario", ""),
            status,
            r.get("expected_result", ""),
            r.get("actual_result", ""),
            r.get("error_message", ""),
            r.get("screenshot_path", ""),
            round(float(r.get("duration_seconds", 0.0)), 2),
            r.get("executed_at", ""),
        ]

        for col_idx, value in enumerate(vals, start=1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            cell.fill = row_fill
            cell.alignment = Alignment(wrap_text=True, vertical="top")
            cell.border = _thin_border()
            cell.font = Font(size=10)

    col_widths = [14, 35, 12, 35, 35, 30, 25, 14, 22]
    for col_idx, w in enumerate(col_widths, start=1):
        ws.column_dimensions[get_column_letter(col_idx)].width = w

    ws.freeze_panes = ws.cell(row=3, column=1)
    ws.auto_filter.ref = f"A2:{get_column_letter(len(headers))}2"


def _write_analysis_sheet(ws, analysis: AnalysisResult) -> None:
    """Populate the Requirement Analysis worksheet."""
    row = 1

    # ---- Requirements table ----
    row = _write_section_header(ws, row, "Extracted Requirements")
    headers = ["Req ID", "Description", "Category"]
    for col_idx, h in enumerate(headers, start=1):
        cell = ws.cell(row=row, column=col_idx, value=h)
        _style_header(cell)
    row += 1

    for req in analysis.requirements:
        ws.cell(row=row, column=1, value=req.req_id)
        ws.cell(row=row, column=2, value=req.description).alignment = Alignment(wrap_text=True)
        ws.cell(row=row, column=3, value=req.category.replace("_", " ").title())
        for col in range(1, 4):
            ws.cell(row=row, column=col).border = _thin_border()
        row += 1

    row += 1  # blank spacer

    # ---- Validation rules ----
    row = _write_section_header(ws, row, "Validation Rules")
    for rule in analysis.validation_rules:
        cell = ws.cell(row=row, column=1, value=rule)
        cell.alignment = Alignment(wrap_text=True)
        cell.border = _thin_border()
        row += 1

    row += 1

    # ---- Ambiguities ----
    row = _write_section_header(ws, row, "⚠ Ambiguities / Vague Language")
    for amb in analysis.ambiguities:
        cell = ws.cell(row=row, column=1, value=amb)
        cell.alignment = Alignment(wrap_text=True)
        cell.font = Font(color="C0392B", size=10)
        row += 1

    row += 1

    # ---- Missing details ----
    row = _write_section_header(ws, row, "⚠ Missing Details")
    for miss in analysis.missing_details:
        cell = ws.cell(row=row, column=1, value=miss)
        cell.alignment = Alignment(wrap_text=True)
        cell.font = Font(color="E67E22", size=10)
        row += 1

    # Column widths
    ws.column_dimensions["A"].width = 20
    ws.column_dimensions["B"].width = 60
    ws.column_dimensions["C"].width = 20


# ---------------------------------------------------------------------------
# Style helpers
# ---------------------------------------------------------------------------

def _style_title(cell) -> None:
    cell.font = Font(bold=True, size=14, color=_HEADER_FG)
    cell.fill = PatternFill("solid", fgColor=_HEADER_BG)
    cell.alignment = Alignment(horizontal="center", vertical="center")


def _style_header(cell) -> None:
    cell.font = Font(bold=True, size=11, color=_HEADER_FG)
    cell.fill = PatternFill("solid", fgColor=_HEADER_BG)
    cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    cell.border = _thin_border()


def _write_section_header(ws, row: int, title: str) -> int:
    """Write a coloured section heading and return the next row number."""
    cell = ws.cell(row=row, column=1, value=title)
    cell.font = Font(bold=True, size=12, color=_HEADER_FG)
    cell.fill = PatternFill("solid", fgColor=_SECTION_BG)
    cell.alignment = Alignment(vertical="center")
    ws.row_dimensions[row].height = 22
    return row + 1


def _thin_border() -> Border:
    thin = Side(style="thin")
    return Border(left=thin, right=thin, top=thin, bottom=thin)

