"""
reports/pdf_report.py
---------------------
Generates a professional PDF test report using ReportLab.

The report includes:
- Cover page (project, URL, date, summary stats)
- Test execution summary table
- Individual test case results with pass/fail status
- Defect summary section (AI-generated, clearly labelled)
- Execution statistics

Never invents test results — only writes data passed to it.
"""

from __future__ import annotations

import io
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        HRFlowable, PageBreak,
    )
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    _REPORTLAB_AVAILABLE = True

    _NAVY = colors.HexColor("#1F4E79")
    _BLUE = colors.HexColor("#2E75B6")
    _LIGHT_BLUE = colors.HexColor("#D6E4F0")
    _RED_BG = colors.HexColor("#FFD7D7")
    _RED_FG = colors.HexColor("#922B21")
    _GREEN_BG = colors.HexColor("#D4EDDA")
    _GREEN_FG = colors.HexColor("#1E8449")
    _AMBER_BG = colors.HexColor("#FFF3CD")
    _AMBER_FG = colors.HexColor("#7D6608")
    _GREY = colors.HexColor("#6C757D")
    _LIGHT_GREY = colors.HexColor("#F8F9FA")
except ImportError:
    _REPORTLAB_AVAILABLE = False
    _NAVY = _BLUE = _LIGHT_BLUE = _RED_BG = _RED_FG = _GREEN_BG = _GREEN_FG = _AMBER_BG = _AMBER_FG = _GREY = _LIGHT_GREY = None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_pdf_report(
    project_name: str,
    target_url: str,
    environment: str,
    test_results: List[Dict],
    run_stats: Optional[Dict] = None,
    defect_reports: Optional[List[Dict]] = None,
) -> bytes:
    """
    Build and return a PDF test report as raw bytes.

    Parameters
    ----------
    project_name : str
    target_url : str
    environment : str
    test_results : list of ExecutionResult.to_dict() dicts
    run_stats : dict with keys: total, passed, failed, blocked, skipped, error_count
    defect_reports : list of ai_service.analyse_failure() result dicts

    Returns
    -------
    bytes — the PDF file content

    Raises
    ------
    ImportError
        If ReportLab is not installed.
    """
    if not _REPORTLAB_AVAILABLE:
        raise ImportError(
            "ReportLab is required for PDF reports. Run: pip install reportlab"
        )

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
        title=f"Test Report — {project_name}",
    )

    styles = getSampleStyleSheet()
    story = []

    # ── Cover ────────────────────────────────────────────────────────────────
    story.extend(_build_cover(styles, project_name, target_url, environment, run_stats))
    story.append(PageBreak())

    # ── Execution Summary Table ───────────────────────────────────────────────
    story.extend(_build_summary_table(styles, test_results))
    story.append(Spacer(1, 0.5 * cm))

    # ── Individual Results ────────────────────────────────────────────────────
    story.extend(_build_results_section(styles, test_results))

    # ── Defect Reports ────────────────────────────────────────────────────────
    if defect_reports:
        story.append(PageBreak())
        story.extend(_build_defects_section(styles, defect_reports))

    doc.build(story)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def _build_cover(styles, project_name, target_url, environment, run_stats) -> list:
    elems = []
    title_style = ParagraphStyle(
        "CoverTitle",
        parent=styles["Title"],
        textColor=_NAVY,
        fontSize=24,
        spaceAfter=8,
    )
    sub_style = ParagraphStyle(
        "CoverSub",
        parent=styles["Normal"],
        textColor=_GREY,
        fontSize=11,
        spaceAfter=4,
    )

    elems.append(Spacer(1, 2 * cm))
    elems.append(Paragraph("🧪 AI-Assisted Software Testing", title_style))
    elems.append(Paragraph("Automated Test Execution Report", sub_style))
    elems.append(HRFlowable(width="100%", thickness=2, color=_BLUE))
    elems.append(Spacer(1, 1 * cm))

    meta = [
        ["Project:", project_name],
        ["Target URL:", target_url],
        ["Environment:", environment],
        ["Report Date:", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")],
    ]
    if run_stats:
        meta += [
            ["Total Tests:", str(run_stats.get("total", 0))],
            ["Passed:", str(run_stats.get("passed", 0))],
            ["Failed:", str(run_stats.get("failed", 0))],
            ["Blocked / Skipped:", f"{run_stats.get('blocked', 0)} / {run_stats.get('skipped', 0)}"],
        ]

    t = Table(meta, colWidths=[4 * cm, 12 * cm])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 11),
        ("TEXTCOLOR", (0, 0), (0, -1), _NAVY),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
    ]))
    elems.append(t)
    return elems


def _build_summary_table(styles, results: List[Dict]) -> list:
    elems = []
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], textColor=_NAVY)
    elems.append(Paragraph("Test Execution Summary", h2))
    elems.append(Spacer(1, 0.3 * cm))

    headers = ["#", "Test Case ID", "Scenario", "Status", "Duration (s)"]
    data = [headers]
    for i, r in enumerate(results, 1):
        status = r.get("status", "?")
        data.append([
            str(i),
            r.get("test_case_id", ""),
            _truncate(r.get("test_scenario", ""), 50),
            status,
            f"{r.get('duration_seconds', 0):.1f}",
        ])

    col_widths = [1 * cm, 3 * cm, 8 * cm, 2.5 * cm, 2.5 * cm]
    t = Table(data, colWidths=col_widths, repeatRows=1)

    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), _NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _LIGHT_GREY]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#DEE2E6")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]

    # Colour status cells
    for row_idx, r in enumerate(results, 1):
        status = r.get("status", "")
        col_idx = 3
        if status == "PASSED":
            style_cmds.append(("BACKGROUND", (col_idx, row_idx), (col_idx, row_idx), _GREEN_BG))
            style_cmds.append(("TEXTCOLOR", (col_idx, row_idx), (col_idx, row_idx), _GREEN_FG))
        elif status == "FAILED":
            style_cmds.append(("BACKGROUND", (col_idx, row_idx), (col_idx, row_idx), _RED_BG))
            style_cmds.append(("TEXTCOLOR", (col_idx, row_idx), (col_idx, row_idx), _RED_FG))
        elif status in ("BLOCKED", "SKIPPED"):
            style_cmds.append(("BACKGROUND", (col_idx, row_idx), (col_idx, row_idx), _AMBER_BG))
            style_cmds.append(("TEXTCOLOR", (col_idx, row_idx), (col_idx, row_idx), _AMBER_FG))

    t.setStyle(TableStyle(style_cmds))
    elems.append(t)
    return elems


def _build_results_section(styles, results: List[Dict]) -> list:
    elems = []
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], textColor=_NAVY)
    h3 = ParagraphStyle("H3", parent=styles["Heading3"], textColor=_BLUE, fontSize=10)
    normal = styles["Normal"]
    small = ParagraphStyle("Small", parent=styles["Normal"], fontSize=8, textColor=_GREY)

    elems.append(Paragraph("Detailed Test Results", h2))
    elems.append(Spacer(1, 0.3 * cm))

    for r in results:
        status = r.get("status", "?")
        tc_id = r.get("test_case_id", "")
        elems.append(Paragraph(f"{tc_id} — {r.get('test_scenario', '')}", h3))
        detail_data = [
            ["Status:", status],
            ["Expected:", _truncate(r.get("expected_result", ""), 120)],
            ["Actual:", _truncate(r.get("actual_result", ""), 120)],
        ]
        if r.get("error_message"):
            detail_data.append(["Error:", _truncate(r.get("error_message", ""), 120)])
        if r.get("screenshot_path"):
            detail_data.append(["Screenshot:", r.get("screenshot_path", "")])

        t = Table(detail_data, colWidths=[3 * cm, 13.5 * cm])
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("TEXTCOLOR", (0, 0), (0, -1), _NAVY),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BACKGROUND", (0, 0), (-1, -1), _LIGHT_GREY),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#DEE2E6")),
        ]))
        elems.append(t)
        elems.append(Spacer(1, 0.4 * cm))

    return elems


def _build_defects_section(styles, defects: List[Dict]) -> list:
    elems = []
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], textColor=_NAVY)
    h3 = ParagraphStyle("H3", parent=styles["Heading3"], textColor=_RED_FG, fontSize=10)
    ai_style = ParagraphStyle(
        "AINote", parent=styles["Normal"], fontSize=8,
        textColor=_GREY, leftIndent=10,
    )

    elems.append(Paragraph("Defect Reports (AI-Assisted Analysis)", h2))
    elems.append(Paragraph(
        "⚠ The following defect reports were generated with AI assistance. "
        "Root causes labelled [AI Hypothesis] are unverified suggestions. "
        "Observed facts are labelled [Observed].",
        ai_style,
    ))
    elems.append(Spacer(1, 0.4 * cm))

    for defect in defects:
        title = defect.get("defect_title", "Untitled Defect")
        elems.append(Paragraph(f"🐛 {title}", h3))

        rows = [
            ["Severity:", defect.get("severity", "?")],
            ["Summary:", _truncate(defect.get("failure_summary", ""), 200)],
            ["Expected:", _truncate(defect.get("expected_result", ""), 120)],
            ["Actual:", _truncate(defect.get("actual_result", ""), 120)],
            ["Steps:", _truncate(defect.get("steps_to_reproduce", ""), 200)],
            ["AI Confidence:", defect.get("ai_confidence", "?")],
        ]
        t = Table(rows, colWidths=[3 * cm, 13.5 * cm])
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("TEXTCOLOR", (0, 0), (0, -1), _NAVY),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BACKGROUND", (0, 0), (-1, -1), _LIGHT_GREY),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#DEE2E6")),
        ]))
        elems.append(t)

        # Root causes
        root_causes = defect.get("root_causes", [])
        if root_causes:
            elems.append(Spacer(1, 0.2 * cm))
            elems.append(Paragraph("Possible Root Causes:", ParagraphStyle(
                "RC", parent=styles["Normal"], fontSize=9, fontName="Helvetica-Bold",
            )))
            for cause in root_causes:
                elems.append(Paragraph(f"• {cause}", ai_style))

        elems.append(Spacer(1, 0.6 * cm))

    return elems


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _truncate(text: str, max_len: int) -> str:
    if not text:
        return ""
    text = str(text)
    return text if len(text) <= max_len else text[:max_len - 3] + "..."

