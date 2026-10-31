# 🧪 AI-Assisted Software Testing Agent

An intelligent QA test automation platform built with **Python**, **Streamlit**, **Playwright**, **OpenAI API**, **ReportLab**, and **SQLite**.

The agent transforms software requirements into test cases, executes deterministic browser automation tests, analyzes failures using AI, and generates formal Excel and PDF reports.

---

## 🌟 Key Features

1. **Website Testing Configuration**
   - Configure target URLs, testing environments (Local, Staging, UAT), and browser options.
   - Domain Allowlist security prevents testing unauthorized or production domains.
   - Private network guard blocks unauthorized RFC-1918 traffic.

2. **AI Test Case Generation**
   - Automatically parses functional requirements, validation rules, ambiguities, and missing details.
   - Generates structured test cases with **Automation Feasibility** (High/Medium/Low), priority, preconditions, steps, test data, and expected results.
   - Interactive review, inline editing, and selective approval before execution.

3. **Browser Automation via Playwright**
   - Deterministic test execution engine with reliable locators (`data-testid`, semantic fallbacks).
   - Headless or headed execution with explicit waits and timeouts.
   - Automatic full-page screenshot capture and log collection on failure.
   - Safe mode prohibits destructive operations (purchases, data deletion, password changes).

4. **AI-Assisted Failure Analysis**
   - Collects actual results, error messages, screenshots, and logs upon failure.
   - Clearly distinguishes **[Observed]** execution facts from **[AI Hypothesis]** root causes.
   - Drafts structured defect reports with severity ratings and reproduction steps.

5. **Unified 7-Tab Dashboard**
   - 📊 **Dashboard:** Real-time metrics (Total, Passed, Failed, Blocked, Skipped), pass-rate progress bar.
   - 📋 **Requirement Analysis:** Ambiguity identification and validation rule extraction.
   - 🧪 **Test Case Generator:** AI generation with filtering and inline editing.
   - 🚀 **Test Execution:** Playwright runner with live status.
   - 🐛 **Bug Reports:** Root cause analysis and defect summaries.
   - 📜 **Execution History:** Persistent SQLite history table with past run drill-down.
   - ⚙️ **Settings:** API keys, domain allowlist, model switching, and safe mode controls.

6. **Professional Reporting**
   - 📊 **Excel Workbook:** Priority color-coding, requirement analysis, and execution results sheets.
   - 📄 **PDF Reports:** Styled executive summary, results tables, and AI defect disclosures via ReportLab.

7. **Local Demo Testing App**
   - Built-in Flask application (`http://localhost:5000`) for repeatable, deterministic testing.
   - Test scenarios: Valid login, invalid password, empty email, empty password, invalid email format.

---

## 🚀 Windows Installation & Quick Start

### 1. Prerequisites
- **Python 3.10+** installed on Windows.
- Ensure Python and pip are added to your system `PATH`.

### 2. Setup Virtual Environment
Open PowerShell or Command Prompt in the project folder:
```powershell
cd "c:\Users\aksha\Downloads\ai agent 2"
python -m venv venv
.\venv\Scripts\Activate.ps1
```
*(If execution policy restricts scripts, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` or activate with `venv\Scripts\activate.bat`)*

### 3. Install Dependencies
```powershell
pip install -r requirements.txt
playwright install chromium
```

### 4. Configure Environment
Copy `.env.example` to `.env`:
```powershell
copy .env.example .env
```
Open `.env` in any text editor and supply your OpenAI API key:
```env
OPENAI_API_KEY=sk-your-openai-key-here
OPENAI_MODEL=gpt-4o-mini
ALLOWED_DOMAINS=localhost,127.0.0.1
SAFE_MODE=true
```

---

## 🏃 Running the Application

### Option A: Automatic Windows Batch Launcher
Double-click `run.bat` or run:
```cmd
run.bat
```

### Option B: Manual Launch
1. **(Optional) Start the local Demo Login Server** in one terminal:
   ```powershell
   python -m app.demo.app
   ```
   *(Or click "Start Local Demo App" directly in the Streamlit UI sidebar)*

2. **Start the Streamlit Application**:
   ```powershell
   streamlit run main.py
   ```
3. Open your browser at: **`http://localhost:8501`**

---

## 🧪 Running the Verification Test Suite

Run all unit and integration tests using pytest:
```powershell
pytest -v
```

This verifies:
- `test_demo_login.py`: 5 deterministic test cases against the demo login app (Valid login, Invalid password, Empty email, Empty password, Invalid email format).
- `test_browser_safety.py`: Domain allowlist, private IP protection, and secret log redaction.
- `test_database.py`: SQLite run tracking, result persistence, and metric aggregation.
- `test_requirement_analysis.py`: Requirement extraction, ambiguity detection.
- `test_test_case_generator.py`: Parsing, filtering, and automation feasibility tagging.
- `test_excel_export.py`: Multi-sheet Excel workbook builder.
- `test_ai_service.py`: OpenAI integrations and failure analysis schemas.

