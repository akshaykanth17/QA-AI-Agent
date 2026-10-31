"""
requirement_analysis.py
-----------------------
Parses raw requirement text and extracts structured information:
- Functional requirements
- Validation rules
- Ambiguities / missing details

This module is pure Python (no AI calls) and is fully unit-testable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class RequirementItem:
    """A single extracted requirement."""
    req_id: str
    description: str
    category: str  # functional | validation | business_rule | non_functional


@dataclass
class AnalysisResult:
    """Full result returned by analyse_requirements()."""
    requirements: List[RequirementItem] = field(default_factory=list)
    validation_rules: List[str] = field(default_factory=list)
    ambiguities: List[str] = field(default_factory=list)
    missing_details: List[str] = field(default_factory=list)
    raw_text: str = ""


# ---------------------------------------------------------------------------
# Keywords used for heuristic classification
# ---------------------------------------------------------------------------

_VALIDATION_KEYWORDS = [
    "must", "shall", "required", "mandatory", "validate", "validation",
    "only", "cannot", "not allowed", "minimum", "maximum", "min", "max",
    "between", "range", "format", "pattern", "unique", "at least", "at most",
    "greater than", "less than", "equal to",
]

_AMBIGUITY_PATTERNS = [
    (r"\bsoon\b", "Vague timing: 'soon' — specify a concrete duration."),
    (r"\bfast\b", "Vague performance: 'fast' — specify a measurable threshold."),
    (r"\beasy\b", "Subjective usability: 'easy' — define acceptance criteria."),
    (r"\buser[- ]friendly\b", "Subjective: 'user-friendly' — define measurable UX criteria."),
    (r"\bapproximately\b", "Vague quantity: 'approximately' — use exact values."),
    (r"\bsome\b", "Vague quantity: 'some' — specify a count or range."),
    (r"\betc\.?\b", "Incomplete list: 'etc.' — enumerate all items explicitly."),
    (r"\bappropriate\b", "Subjective: 'appropriate' — define what is acceptable."),
    (r"\bsufficient\b", "Vague: 'sufficient' — provide a measurable threshold."),
    (r"\bshould\b", "Ambiguous obligation: 'should' — clarify if this is mandatory."),
    (r"\bmight\b", "Uncertain behaviour: 'might' — confirm if this is required."),
    (r"\bmaybe\b", "Uncertain behaviour: 'maybe' — confirm if this is required."),
    (r"\bpossibly\b", "Uncertain behaviour: 'possibly' — confirm if this is required."),
    (r"\bTBD\b", "Requirement not yet defined: 'TBD'."),
    (r"\bTBC\b", "Requirement not yet confirmed: 'TBC'."),
]

_MISSING_PATTERNS = [
    (r"\berror\b(?!.*message)", "Error scenario mentioned but no error message specified."),
    (r"\bnotif", "Notification mentioned — specify channel, content, and timing."),
    (r"\bsend\b(?!.*format)", "Sending action mentioned — specify format and recipient."),
    (r"\breport\b(?!.*format)", "Report mentioned — specify format, fields, and frequency."),
    (r"\bexport\b(?!.*format)", "Export mentioned — specify file format and fields."),
    (r"\bpermission|role|access\b", "Role/access mentioned — specify full RBAC rules."),
    (r"\bpayment\b", "Payment mentioned — specify gateway, currencies, and failure handling."),
    (r"\bpassword\b(?!.*policy)", "Password mentioned — define complexity and expiry policy."),
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyse_requirements(text: str) -> AnalysisResult:
    """
    Parse *text* and return a structured :class:`AnalysisResult`.

    Parameters
    ----------
    text:
        Raw requirement text (plain English sentences or numbered list).

    Returns
    -------
    AnalysisResult
    """
    if not text or not text.strip():
        return AnalysisResult(raw_text=text or "")

    result = AnalysisResult(raw_text=text)
    sentences = _split_into_sentences(text)

    for idx, sentence in enumerate(sentences, start=1):
        stripped = sentence.strip()
        if not stripped:
            continue

        req_id = f"REQ-{idx:03d}"
        category = _classify_sentence(stripped)

        result.requirements.append(
            RequirementItem(
                req_id=req_id,
                description=stripped,
                category=category,
            )
        )

        # Collect validation rules
        if category == "validation" or _is_validation(stripped):
            result.validation_rules.append(f"[{req_id}] {stripped}")

        # Detect ambiguities
        for pattern, message in _AMBIGUITY_PATTERNS:
            if re.search(pattern, stripped, re.IGNORECASE):
                entry = f"[{req_id}] {message}"
                if entry not in result.ambiguities:
                    result.ambiguities.append(entry)

        # Detect missing details
        for pattern, message in _MISSING_PATTERNS:
            if re.search(pattern, stripped, re.IGNORECASE):
                entry = f"[{req_id}] {message}"
                if entry not in result.missing_details:
                    result.missing_details.append(entry)

    return result


def extract_text_from_file(file_bytes: bytes, filename: str) -> str:
    """
    Extract plain text from an uploaded TXT or PDF file.

    Parameters
    ----------
    file_bytes:
        Raw bytes of the uploaded file.
    filename:
        Original filename (used to decide parser).

    Returns
    -------
    Extracted text string.

    Raises
    ------
    ValueError
        If the file extension is not supported.
    """
    ext = filename.lower().rsplit(".", 1)[-1]

    if ext == "txt":
        return file_bytes.decode("utf-8", errors="replace")

    if ext == "pdf":
        return _extract_pdf_text(file_bytes)

    raise ValueError(
        f"Unsupported file type: '.{ext}'. Please upload a .txt or .pdf file."
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _split_into_sentences(text: str) -> List[str]:
    """Split text into individual requirement sentences / bullet points."""
    # Normalise line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    sentences: List[str] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Remove common bullet prefixes
        line = re.sub(r"^[\-\*\•\>\#]+\s*", "", line)
        line = re.sub(r"^\d+[\.\)]\s*", "", line)
        if line:
            sentences.append(line)
    return sentences


def _is_validation(text: str) -> bool:
    lower = text.lower()
    return any(kw in lower for kw in _VALIDATION_KEYWORDS)


def _classify_sentence(text: str) -> str:
    lower = text.lower()
    if any(kw in lower for kw in ["validate", "must be", "shall be", "required", "mandatory"]):
        return "validation"
    if any(kw in lower for kw in ["login", "register", "search", "filter", "display", "show",
                                    "create", "update", "delete", "submit", "upload", "download",
                                    "send", "receive", "calculate", "generate", "export", "import"]):
        return "functional"
    if any(kw in lower for kw in ["performance", "security", "scalability", "availability",
                                    "response time", "uptime", "throughput"]):
        return "non_functional"
    return "business_rule"


def _extract_pdf_text(file_bytes: bytes) -> str:
    """Extract text from PDF bytes using PyPDF2."""
    try:
        import io
        import PyPDF2  # type: ignore

        reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
        pages_text = []
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                pages_text.append(page_text)
        return "\n".join(pages_text)
    except ImportError as exc:
        raise ImportError(
            "PyPDF2 is required for PDF parsing. Run: pip install PyPDF2"
        ) from exc
    except Exception as exc:
        raise ValueError(f"Could not read PDF file: {exc}") from exc

