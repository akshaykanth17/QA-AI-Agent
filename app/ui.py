"""
ui.py
-----
Streamlit user interface for the AI-Assisted Software Testing Agent.

Includes 7 feature sections:
- 📊 Dashboard
- 📋 Requirement Analysis
- 🧪 Test Case Generator
- 🚀 Test Execution
- 🐛 Bug Reports
- 📜 Execution History
- ⚙️ Settings
"""

from __future__ import annotations

import io
import os
import threading
import time
import traceback
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st

from app.ai_service import (
    analyse_failure,
    check_connection,
    generate_test_cases,
    get_api_key,
    get_model,
)
from app.browser.runner import ExecutionResult, execute_test_case
from app.browser.safety import (
    check_action_allowed,
    get_allowed_domains,
    is_safe_mode,
    is_url_allowed,
    sanitise_log,
)
from app.database.db import (
    complete_run,
    create_run,
    get_aggregate_stats,
    get_all_runs,
    get_results_for_run,
    save_result,
)
from app.excel_export import build_excel
from app.reports.pdf_report import build_pdf_report
from app.requirement_analysis import AnalysisResult, analyse_requirements, extract_text_from_file
from app.test_case_generator import (
    VALID_AUTOMATION_FEASIBILITY,
    VALID_PRIORITIES,
    VALID_TEST_TYPES,
    TestCase,
    filter_test_cases,
    parse_ai_response,
    test_cases_to_dataframe,
)


# ---------------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------------

def configure_page() -> None:
    st.set_page_config(
        page_title="AI-Assisted Software Testing Agent",
        page_icon="🧪",
        layout="wide",
        initial_sidebar_state="expanded",
    )


# ---------------------------------------------------------------------------
# Custom CSS
# ---------------------------------------------------------------------------

_CSS = """
<style>
/* Main Header */
.main-header {
    background: linear-gradient(135deg, #1F4E79 0%, #2E75B6 100%);
    padding: 1.25rem 2rem;
    border-radius: 10px;
    margin-bottom: 1.25rem;
    color: white;
}
.main-header h1 { color: white; margin: 0; font-size: 1.85rem; }
.main-header p  { color: #BDD7EE; margin: 0.25rem 0 0; font-size: 0.95rem; }

/* Status Badges */
.badge-pass    { background:#D4EDDA; color:#155724; padding:3px 10px; border-radius:4px; font-weight:700; font-size:0.85rem; display:inline-block; }
.badge-fail    { background:#F8D7DA; color:#721C24; padding:3px 10px; border-radius:4px; font-weight:700; font-size:0.85rem; display:inline-block; }
.badge-blocked { background:#FFF3CD; color:#856404; padding:3px 10px; border-radius:4px; font-weight:700; font-size:0.85rem; display:inline-block; }

/* AI vs Observed tags */
.tag-observed   { background:#E2E8F0; color:#1E293B; padding:2px 8px; border-radius:4px; font-size:0.75rem; font-weight:700; }
.tag-hypothesis { background:#FEF3C7; color:#92400E; padding:2px 8px; border-radius:4px; font-size:0.75rem; font-weight:700; }

/* Buttons */
.stButton > button {
    border-radius: 6px;
    font-weight: 600;
}
</style>
"""


# ---------------------------------------------------------------------------
# State initialisation
# ---------------------------------------------------------------------------

def _init_state() -> None:
    defaults = {
        "project_name": "Demo E-Commerce / Login Testing",
        "target_url": "http://localhost:5000/login",
        "testing_env": "Local Test (Demo)",
        "requirements_text": "",
        "analysis": None,
        "test_cases": [],
        "approved_tc_ids": set(),
        "execution_results": [],
        "defect_reports": {},
        "raw_ai_response": "",
        "generation_error": "",
        "current_tab": "📊 Dashboard",
        "demo_server_started": False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


# ---------------------------------------------------------------------------
# Demo App Helper (Threaded runner for local test server)
# ---------------------------------------------------------------------------

def _ensure_demo_server() -> bool:
    """Ensure the local demo server is running on port 5000."""
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    is_running = sock.connect_ex(("127.0.0.1", 5000)) == 0
    sock.close()
    if is_running:
        st.session_state["demo_server_started"] = True
        return True

    def _run_server():
        try:
            from app.demo.app import app
            app.run(port=5000, debug=False, use_reloader=False)
        except Exception:
            pass

    t = threading.Thread(target=_run_server, daemon=True)
    t.start()
    time.sleep(1)
    st.session_state["demo_server_started"] = True
    return True


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

def _render_sidebar() -> str:
    with st.sidebar:
        st.title("🧪 AI QA Agent")
        st.caption("AI-Assisted Software Testing")

        menu_items = [
            "📊 Dashboard",
            "📋 Requirement Analysis",
            "🧪 Test Case Generator",
            "🚀 Test Execution",
            "🐛 Bug Reports",
            "📜 Execution History",
            "⚙️ Settings",
        ]
        selected = st.radio("Navigation", menu_items, index=menu_items.index(st.session_state.get("current_tab", "📊 Dashboard")))
        st.session_state["current_tab"] = selected

        st.divider()

        # API key status & configuration in sidebar for quick access
        st.markdown("### 🔑 API Key")
        has_key = False
        try:
            curr_key = get_api_key()
            has_key = True
        except EnvironmentError:
            curr_key = ""

        user_key = st.text_input(
            "OpenAI API Key:",
            value=curr_key if curr_key and not curr_key.startswith("sk-your") else "",
            type="password",
            placeholder="sk-...",
            help="Stored securely in memory during this session. Or configure in .env.",
            key="sidebar_api_key",
        )
        if user_key and user_key.strip():
            os.environ["OPENAI_API_KEY"] = user_key.strip()
            st.success("✅ API key set")
        elif has_key:
            st.success("✅ Key loaded from environment")
        else:
            st.warning("⚠️ OpenAI key not set")

        st.divider()

        # Quick summary badge
        tc_count = len(st.session_state.get("test_cases", []))
        exec_count = len(st.session_state.get("execution_results", []))
        st.markdown(f"**Generated Cases:** `{tc_count}`")
        st.markdown(f"**Executed Tests:** `{exec_count}`")

        # Quick Demo Server Controller
        st.divider()
        st.markdown("### 🖥️ Local Demo App")
        if st.button("Start Local Demo App (Port 5000)", use_container_width=True):
            with st.spinner("Launching demo login server..."):
                _ensure_demo_server()
                st.success("Demo app active at http://localhost:5000")

        return selected


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

def _render_header() -> None:
    st.markdown(
        """
        <div class="main-header">
            <h1>🧪 AI-Assisted Software Testing Agent</h1>
            <p>Autonomous test case design, deterministic Playwright browser execution & AI failure analysis.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Tab 1: Dashboard
# ---------------------------------------------------------------------------

def _render_dashboard() -> None:
    st.subheader("📊 QA Automation Dashboard")

    results = st.session_state.get("execution_results", [])
    total = len(results)
    passed = sum(1 for r in results if r.get("status") == "PASSED")
    failed = sum(1 for r in results if r.get("status") in ("FAILED", "ERROR"))
    blocked = sum(1 for r in results if r.get("status") == "BLOCKED")
    skipped = sum(1 for r in results if r.get("status") == "SKIPPED")

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Total Tests Executed", total)
    col2.metric("✅ Passed", passed)
    col3.metric("❌ Failed / Error", failed)
    col4.metric("⚠️ Blocked", blocked)
    col5.metric("⏭️ Skipped", skipped)

    if total > 0:
        pass_rate = (passed / total) * 100
        st.progress(pass_rate / 100, text=f"Pass Rate: {pass_rate:.1f}% ({passed}/{total} passed)")
    else:
        st.info("ℹ️ No tests executed in the current session yet. Go to **Requirement Analysis** or **Test Execution** to get started.")

    st.markdown("---")

    col_left, col_right = st.columns([3, 2])

    with col_left:
        st.markdown("### 🎯 Quick Target Setup")
        c_proj, c_env = st.columns(2)
        with c_proj:
            st.session_state["project_name"] = st.text_input(
                "Project / App Name",
                value=st.session_state.get("project_name", "Demo E-Commerce / Login"),
            )
        with c_env:
            st.session_state["testing_env"] = st.selectbox(
                "Environment",
                ["Local Test (Demo)", "Staging / QA", "UAT", "Production (Restricted)"],
                index=0,
            )

        preset_sites = {
            "🖥️ Local Demo App (Port 5000)": "http://localhost:5000/login",
            "🛍️ SauceDemo / Swag Labs": "https://www.saucedemo.com/",
            "🌐 The Internet (Herokuapp)": "https://the-internet.herokuapp.com/login",
            "🎓 Practice Test Automation": "https://practicetestautomation.com/practice-test-login/",
            "✏️ Custom URL": "",
        }
        sel_preset = st.selectbox("Preset Test Applications", list(preset_sites.keys()), index=0)
        default_url = preset_sites[sel_preset] if preset_sites[sel_preset] else st.session_state.get("target_url", "http://localhost:5000/login")

        target_url = st.text_input(
            "Target Website URL",
            value=default_url,
            help="Target URL for automated testing. Must be approved in domain allowlist.",
        )
        st.session_state["target_url"] = target_url

        if is_url_allowed(target_url):
            st.success(f"✅ Target URL approved for automation: `{target_url}`")
        else:
            st.error(f"⛔ Target URL is NOT on the approved domain allowlist. Configure in Settings or enter an approved URL.")

    with col_right:
        st.markdown("### 📈 Historical Execution Metrics")
        stats = get_aggregate_stats()
        h_col1, h_col2 = st.columns(2)
        h_col1.metric("All-Time Runs", stats.get("total_runs", 0))
        h_col1.metric("All-Time Tests", stats.get("total_tests", 0))
        h_col2.metric("All-Time Passes", stats.get("passed", 0))
        h_col2.metric("All-Time Failures", stats.get("failed", 0))


# ---------------------------------------------------------------------------
# Tab 2: Requirement Analysis
# ---------------------------------------------------------------------------

def _render_requirement_analysis() -> None:
    st.subheader("📋 Requirement Analysis & Ingestion")
    st.markdown("Enter software requirements or upload a specification document (.txt, .pdf) to extract rules and detect ambiguities.")

    input_tab, upload_tab, demo_tab = st.tabs(["✏️ Type / Paste", "📁 Upload File", "💡 Load Sample Demo Requirements"])

    requirements_text: str = st.session_state.get("requirements_text", "")

    with input_tab:
        typed = st.text_area(
            "Software Requirements / User Stories:",
            value=requirements_text,
            height=200,
            placeholder="Example:\n- The system shall allow users to log in with a valid email and password.\n- Password must be at least 8 characters.\n- The login page shall display an error message for invalid credentials.",
            key="req_text_area",
        )
        if typed:
            requirements_text = typed

    with upload_tab:
        uploaded = st.file_uploader("Upload specification (.txt or .pdf):", type=["txt", "pdf"])
        if uploaded is not None:
            try:
                extracted = extract_text_from_file(uploaded.read(), uploaded.name)
                requirements_text = extracted
                st.success(f"✅ Extracted text from {uploaded.name} ({len(extracted):,} characters)")
            except Exception as e:
                st.error(f"Failed to read file: {e}")

    with demo_tab:
        if st.button("Load Demo Login App Requirements"):
            requirements_text = (
                "The system shall provide a secure user login interface at /login.\n"
                "Users must enter a valid email address and password to sign in.\n"
                "Valid credentials: email 'demo@example.com' with password 'DemoPass@123'.\n"
                "If email is blank, the system must display 'Email address is required.'.\n"
                "If password is blank, the system must display 'Password is required.'.\n"
                "If email format is invalid, the system must display 'Email address format is invalid.'.\n"
                "If credentials do not match, the system must display 'Invalid email or password. Please try again.'.\n"
                "Upon successful authentication, the user is redirected to the dashboard."
            )
            st.session_state["requirements_text"] = requirements_text
            st.success("Loaded demo login requirements!")
            st.rerun()

    st.session_state["requirements_text"] = requirements_text

    col_btn, _ = st.columns([2, 5])
    with col_btn:
        if st.button("🔍 Analyze Requirements", type="primary", use_container_width=True, disabled=not bool(requirements_text.strip())):
            analysis = analyse_requirements(requirements_text)
            st.session_state["analysis"] = analysis
            st.success(f"Analysis complete: {len(analysis.requirements)} requirements identified.")

    analysis: Optional[AnalysisResult] = st.session_state.get("analysis")
    if analysis and analysis.requirements:
        st.markdown("---")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Requirements", len(analysis.requirements))
        c2.metric("Validation Rules", len(analysis.validation_rules))
        c3.metric("⚠️ Ambiguities", len(analysis.ambiguities))
        c4.metric("❓ Missing Details", len(analysis.missing_details))

        with st.expander("📜 Extracted Requirements", expanded=True):
            req_data = [
                {"Req ID": r.req_id, "Description": r.description, "Category": r.category.replace("_", " ").title()}
                for r in analysis.requirements
            ]
            st.dataframe(pd.DataFrame(req_data), use_container_width=True, hide_index=True)

        with st.expander("✅ Validation Rules"):
            for r in analysis.validation_rules:
                st.markdown(f"- {r}")

        if analysis.ambiguities or analysis.missing_details:
            with st.expander("⚠️ Ambiguities & Missing Details", expanded=True):
                for a in analysis.ambiguities:
                    st.warning(a)
                for m in analysis.missing_details:
                    st.info(m)


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Reusable Playwright Execution Runner
# ---------------------------------------------------------------------------

def _execute_playwright_suite(
    approved_cases: List[TestCase],
    target_url: str,
    headless: bool = False,
    slow_mo: float = 0.6,
    timeout: int = 10,
) -> List[Dict[str, Any]]:
    """Execute approved test cases via Playwright with live feedback, snapshot capture, and DB persistence."""
    if not is_url_allowed(target_url):
        st.error(f"⛔ Cannot execute: `{target_url}` is not in the approved domain allowlist.")
        return []

    if "localhost" in target_url or "127.0.0.1" in target_url:
        _ensure_demo_server()

    run_id = create_run(
        target_url=target_url,
        project_name=st.session_state.get("project_name", "AI Testing Agent"),
        environment=st.session_state.get("testing_env", "Local"),
    )

    progress_bar = st.progress(0, text="Initializing Playwright browser runner...")
    results: List[Dict[str, Any]] = []

    live_status = st.empty()
    live_preview = st.empty()

    for idx, tc in enumerate(approved_cases):
        progress_bar.progress(
            int((idx / len(approved_cases)) * 100),
            text=f"⏳ Running [{idx + 1}/{len(approved_cases)}]: {tc.test_case_id} — {tc.test_scenario}",
        )
        live_status.info(f"🌐 **Automating ({idx + 1}/{len(approved_cases)}):** `{tc.test_case_id}` — {tc.test_scenario} on `{target_url}`")

        exec_res = execute_test_case(
            test_case=tc,
            target_url=target_url,
            headless=headless,
            timeout_ms=timeout * 1000,
            slow_mo_ms=int(slow_mo * 1000),
        )
        res_dict = exec_res.to_dict()
        results.append(res_dict)

        save_result(run_id=run_id, result=res_dict)

        # Update live preview on screen immediately with the captured browser snapshot
        shot = res_dict.get("screenshot_path")
        if shot and os.path.exists(shot):
            with live_preview.container():
                st.markdown(f"**⚡ Live Browser Snapshot:** `{tc.test_case_id}` ({res_dict.get('status')})")
                st.image(shot, caption=f"Captured from Chromium for {tc.test_case_id}", use_container_width=True)

    complete_run(run_id=run_id, results=results)
    st.session_state["execution_results"] = results
    progress_bar.progress(100, text="Execution complete!")
    time.sleep(0.4)
    progress_bar.empty()
    live_status.empty()
    live_preview.empty()
    return results


# ---------------------------------------------------------------------------
# Tab 3: Test Case Generator
# ---------------------------------------------------------------------------

def _render_test_case_generator() -> None:
    from app.test_case_generator import (
        TestCase,
        generate_heuristic_test_cases,
        test_cases_to_dataframe,
        filter_test_cases,
        VALID_PRIORITIES,
        VALID_TEST_TYPES,
        VALID_AUTOMATION_FEASIBILITY,
    )

    st.subheader("🧪 Test Case Generator & Suite Manager")
    st.markdown("Create test cases manually, generate them using offline rules (no API key needed), load verified presets, or generate with OpenAI.")

    req_text = st.session_state.get("requirements_text", "")
    analysis: Optional[AnalysisResult] = st.session_state.get("analysis")
    test_cases: List[TestCase] = st.session_state.get("test_cases", [])

    # 4 distinct tabs for creation & generation
    gen_tab1, gen_tab2, gen_tab3, gen_tab4 = st.tabs([
        "✍️ Add Manually (Form)",
        "⚡ Rule-Based Generator (Offline / No Key)",
        "📦 Load Preset Test Suites",
        "🤖 AI Generator (OpenAI)",
    ])

    # ── Tab 1: Manual Test Case Form ──
    with gen_tab1:
        st.markdown("#### ✍️ Add a Custom Test Case Manually")
        st.caption("Type in your own scenario, credentials, test steps, and expected result:")
        next_num = len(test_cases) + 1

        with st.form("manual_tc_form_tab", clear_on_submit=True):
            f_col1, f_col2, f_col3 = st.columns([1, 1, 3])
            with f_col1:
                tc_id = st.text_input("Test Case ID", value=f"TC-{next_num:03d}")
            with f_col2:
                req_id = st.text_input("Requirement ID", value="REQ-001")
            with f_col3:
                scen = st.text_input("Test Scenario", placeholder="e.g. Valid login with standard user credentials")

            f_col4, f_col5 = st.columns(2)
            with f_col4:
                precond = st.text_input("Preconditions", value="User is on the target login page")
            with f_col5:
                data_in = st.text_input(
                    "Test Data (Credentials / Inputs)",
                    placeholder="Username: standard_user, Password: secret_sauce",
                    help="Tip: Format as 'Username: x, Password: y' or 'Email: x, Password: y' for automated execution.",
                )

            steps_in = st.text_area(
                "Test Steps",
                value="1. Navigate to target URL\n2. Enter username / email\n3. Enter password\n4. Click 'Sign In' or 'Login'",
                height=90,
            )
            expected_in = st.text_input(
                "Expected Result",
                placeholder="e.g. Login successful. Dashboard is displayed.",
                value="Login successful. Dashboard / landing page is displayed.",
            )

            f_p, f_t, f_f = st.columns(3)
            with f_p:
                p_val = st.selectbox("Priority", ["High", "Medium", "Low"], index=0, key="manual_p")
            with f_t:
                t_val = st.selectbox("Test Type", ["Positive", "Negative", "Validation", "Boundary", "Edge Case", "Error Handling"], index=0, key="manual_t")
            with f_f:
                f_val = st.selectbox("Automation Feasibility", ["High", "Medium", "Low"], index=0, key="manual_f")

            add_btn = st.form_submit_button("➕ Add Test Case to Suite", type="primary", use_container_width=True)

            if add_btn:
                if not scen.strip():
                    st.error("Please enter a Test Scenario description.")
                else:
                    new_case = TestCase(
                        test_case_id=tc_id.strip() or f"TC-{next_num:03d}",
                        requirement_id=req_id.strip() or "REQ-001",
                        test_scenario=scen.strip(),
                        preconditions=precond.strip(),
                        test_steps=steps_in.strip(),
                        test_data=data_in.strip() or "N/A",
                        expected_result=expected_in.strip() or "Success",
                        priority=p_val,
                        test_type=t_val,
                        automation_feasibility=f_val,
                    )
                    curr_list = list(st.session_state.get("test_cases", []))
                    curr_list.append(new_case)
                    st.session_state["test_cases"] = curr_list

                    approved = set(st.session_state.get("approved_tc_ids", set()))
                    approved.add(new_case.test_case_id)
                    st.session_state["approved_tc_ids"] = approved

                    st.success(f"✅ Added test case `{new_case.test_case_id}` to test suite! (Auto-approved for execution)")
                    st.rerun()

    # ── Tab 2: Rule-Based Generator (Offline / No Key) ──
    with gen_tab2:
        st.markdown("#### ⚡ Generate Test Cases from Requirements (Offline Mode)")
        st.caption("Extracts positive, negative, validation, and boundary test cases directly from requirements without requiring OpenAI.")

        sample_prompt = req_text.strip() or "User authentication requirement: Users must enter a valid email and password (minimum 8 characters). Empty fields or invalid credentials should trigger validation errors."
        offline_input = st.text_area("Requirements / Specifications to analyze:", value=sample_prompt, height=110, key="offline_req_input")

        if st.button("⚡ Generate Offline Test Cases", type="primary", use_container_width=True):
            with st.spinner("Synthesizing positive, negative, and validation test cases..."):
                generated = generate_heuristic_test_cases(offline_input, analysis)
                st.session_state["test_cases"] = generated
                st.session_state["approved_tc_ids"] = {c.test_case_id for c in generated}
                st.success(f"✅ Successfully generated {len(generated)} structured test cases!")
                st.rerun()

    # ── Tab 3: Preset Test Suites ──
    with gen_tab3:
        st.markdown("#### 📦 Load Ready-to-Run Verified Presets")
        st.caption("Click any preset below to instantly load verified test cases and configure the target URL:")

        col_p1, col_p2 = st.columns(2)
        with col_p1:
            st.markdown("##### 🖥️ Local Demo App (Port 5000)")
            st.caption("5 tests: Valid login, invalid password, empty email, empty password, invalid format.")
            if st.button("💡 Load Local Demo Suite", use_container_width=True):
                demo_cases = [
                    TestCase(
                        test_case_id="TC-001",
                        requirement_id="REQ-003",
                        test_scenario="User logs in successfully with valid credentials",
                        preconditions="Demo application is running at http://localhost:5000",
                        test_steps="1. Navigate to /login\n2. Enter valid email 'demo@example.com'\n3. Enter valid password 'DemoPass@123'\n4. Click 'Sign In'",
                        test_data="Email: demo@example.com, Password: DemoPass@123",
                        expected_result="Login successful. Dashboard/welcome page is displayed.",
                        priority="High",
                        test_type="Positive",
                        automation_feasibility="High",
                    ),
                    TestCase(
                        test_case_id="TC-002",
                        requirement_id="REQ-004",
                        test_scenario="User enters invalid password",
                        preconditions="User is on login page",
                        test_steps="1. Enter email 'demo@example.com'\n2. Enter invalid password 'WrongPass999!'\n3. Click 'Sign In'",
                        test_data="Email: demo@example.com, Password: WrongPass999!",
                        expected_result="Login failed. Error message displayed: 'Invalid email or password. Please try again.'",
                        priority="High",
                        test_type="Negative",
                        automation_feasibility="High",
                    ),
                    TestCase(
                        test_case_id="TC-003",
                        requirement_id="REQ-005",
                        test_scenario="User attempts to submit empty email field",
                        preconditions="User is on login page",
                        test_steps="1. Leave email field empty\n2. Enter password 'DemoPass@123'\n3. Click 'Sign In'",
                        test_data="Email: , Password: DemoPass@123",
                        expected_result="Login failed. Error message displayed: 'Email address is required.'",
                        priority="Medium",
                        test_type="Validation",
                        automation_feasibility="High",
                    ),
                    TestCase(
                        test_case_id="TC-004",
                        requirement_id="REQ-006",
                        test_scenario="User attempts to submit empty password field",
                        preconditions="User is on login page",
                        test_steps="1. Enter email 'demo@example.com'\n2. Leave password field empty\n3. Click 'Sign In'",
                        test_data="Email: demo@example.com, Password: ",
                        expected_result="Login failed. Error message displayed: 'Password is required.'",
                        priority="Medium",
                        test_type="Validation",
                        automation_feasibility="High",
                    ),
                    TestCase(
                        test_case_id="TC-005",
                        requirement_id="REQ-007",
                        test_scenario="User enters invalid email format",
                        preconditions="User is on login page",
                        test_steps="1. Enter invalid email 'user-at-domain'\n2. Enter password 'DemoPass@123'\n3. Click 'Sign In'",
                        test_data="Email: user-at-domain, Password: DemoPass@123",
                        expected_result="Login failed. Error message displayed: 'Email address format is invalid.'",
                        priority="Medium",
                        test_type="Negative",
                        automation_feasibility="High",
                    ),
                ]
                st.session_state["target_url"] = "http://localhost:5000/login"
                st.session_state["project_name"] = "Demo Login App"
                st.session_state["test_cases"] = demo_cases
                st.session_state["approved_tc_ids"] = {c.test_case_id for c in demo_cases}
                st.success("Loaded 5 verified demo test cases! Target URL set to http://localhost:5000/login.")
                st.rerun()

            st.markdown("##### 🌐 The Internet (Herokuapp)")
            st.caption("3 tests: tomsmith / SuperSecretPassword!, invalid password, empty credentials.")
            if st.button("🌐 Load Herokuapp Suite", use_container_width=True):
                hk_cases = [
                    TestCase(
                        test_case_id="TC-HK-01",
                        requirement_id="REQ-HK-01",
                        test_scenario="User logs in to Herokuapp with valid credentials",
                        preconditions="Navigate to https://the-internet.herokuapp.com/login",
                        test_steps="1. Enter username 'tomsmith'\n2. Enter password 'SuperSecretPassword!'\n3. Click 'Login'",
                        test_data="Username: tomsmith, Password: SuperSecretPassword!",
                        expected_result="Login successful. Secure Area page is displayed.",
                        priority="High",
                        test_type="Positive",
                        automation_feasibility="High",
                    ),
                    TestCase(
                        test_case_id="TC-HK-02",
                        requirement_id="REQ-HK-02",
                        test_scenario="User enters invalid password on Herokuapp",
                        preconditions="Navigate to https://the-internet.herokuapp.com/login",
                        test_steps="1. Enter username 'tomsmith'\n2. Enter password 'WrongPassword!'\n3. Click 'Login'",
                        test_data="Username: tomsmith, Password: WrongPassword!",
                        expected_result="Login failed. Error banner displayed: 'Your password is invalid!'",
                        priority="High",
                        test_type="Negative",
                        automation_feasibility="High",
                    ),
                    TestCase(
                        test_case_id="TC-HK-03",
                        requirement_id="REQ-HK-03",
                        test_scenario="User submits empty credentials on Herokuapp",
                        preconditions="Navigate to https://the-internet.herokuapp.com/login",
                        test_steps="1. Leave username and password blank\n2. Click 'Login'",
                        test_data="Username: , Password: ",
                        expected_result="Login failed. Error banner displayed.",
                        priority="Medium",
                        test_type="Validation",
                        automation_feasibility="High",
                    ),
                ]
                st.session_state["target_url"] = "https://the-internet.herokuapp.com/login"
                st.session_state["project_name"] = "The Internet Herokuapp"
                st.session_state["test_cases"] = hk_cases
                st.session_state["approved_tc_ids"] = {c.test_case_id for c in hk_cases}
                st.success("Loaded Herokuapp test cases! Target URL set to https://the-internet.herokuapp.com/login.")
                st.rerun()

        with col_p2:
            st.markdown("##### 🛍️ SauceDemo / Swag Labs")
            st.caption("3 tests: standard_user / secret_sauce, wrong_password, locked_out_user.")
            if st.button("🛍️ Load SauceDemo Suite", use_container_width=True):
                sauce_cases = [
                    TestCase(
                        test_case_id="TC-SAUCE-01",
                        requirement_id="REQ-SD-01",
                        test_scenario="User logs in to SauceDemo with standard_user",
                        preconditions="Navigate to https://www.saucedemo.com/",
                        test_steps="1. Enter username 'standard_user'\n2. Enter password 'secret_sauce'\n3. Click 'Login'",
                        test_data="Username: standard_user, Password: secret_sauce",
                        expected_result="Login successful. Products dashboard is displayed.",
                        priority="High",
                        test_type="Positive",
                        automation_feasibility="High",
                    ),
                    TestCase(
                        test_case_id="TC-SAUCE-02",
                        requirement_id="REQ-SD-02",
                        test_scenario="User enters invalid password on SauceDemo",
                        preconditions="User is on https://www.saucedemo.com/",
                        test_steps="1. Enter username 'standard_user'\n2. Enter password 'wrong_password'\n3. Click 'Login'",
                        test_data="Username: standard_user, Password: wrong_password",
                        expected_result="Login failed. Error message displayed: 'Username and password do not match'",
                        priority="High",
                        test_type="Negative",
                        automation_feasibility="High",
                    ),
                    TestCase(
                        test_case_id="TC-SAUCE-03",
                        requirement_id="REQ-SD-03",
                        test_scenario="Locked out user attempts to sign in",
                        preconditions="User is on https://www.saucedemo.com/",
                        test_steps="1. Enter username 'locked_out_user'\n2. Enter password 'secret_sauce'\n3. Click 'Login'",
                        test_data="Username: locked_out_user, Password: secret_sauce",
                        expected_result="Login failed. Error message displayed: 'Sorry, this user has been locked out.'",
                        priority="Medium",
                        test_type="Negative",
                        automation_feasibility="High",
                    ),
                ]
                st.session_state["target_url"] = "https://www.saucedemo.com/"
                st.session_state["project_name"] = "SauceDemo (Swag Labs)"
                st.session_state["test_cases"] = sauce_cases
                st.session_state["approved_tc_ids"] = {c.test_case_id for c in sauce_cases}
                st.success("Loaded SauceDemo test cases! Target URL set to https://www.saucedemo.com/.")
                st.rerun()

            st.markdown("##### 🎓 Practice Test Automation")
            st.caption("3 tests: student / Password123, invalid username, invalid password.")
            if st.button("🎓 Load Practice Test Suite", use_container_width=True):
                pta_cases = [
                    TestCase(
                        test_case_id="TC-PTA-01",
                        requirement_id="REQ-PTA-01",
                        test_scenario="User logs in with valid credentials on Practice Test Automation",
                        preconditions="Navigate to https://practicetestautomation.com/practice-test-login/",
                        test_steps="1. Enter username 'student'\n2. Enter password 'Password123'\n3. Click 'Submit'",
                        test_data="Username: student, Password: Password123",
                        expected_result="Login successful. 'Logged In Successfully' page is displayed.",
                        priority="High",
                        test_type="Positive",
                        automation_feasibility="High",
                    ),
                    TestCase(
                        test_case_id="TC-PTA-02",
                        requirement_id="REQ-PTA-02",
                        test_scenario="User enters invalid username on Practice Test Automation",
                        preconditions="Navigate to https://practicetestautomation.com/practice-test-login/",
                        test_steps="1. Enter username 'incorrectUser'\n2. Enter password 'Password123'\n3. Click 'Submit'",
                        test_data="Username: incorrectUser, Password: Password123",
                        expected_result="Login failed. Error message displayed: 'Your username is invalid!'",
                        priority="High",
                        test_type="Negative",
                        automation_feasibility="High",
                    ),
                    TestCase(
                        test_case_id="TC-PTA-03",
                        requirement_id="REQ-PTA-03",
                        test_scenario="User enters invalid password on Practice Test Automation",
                        preconditions="Navigate to https://practicetestautomation.com/practice-test-login/",
                        test_steps="1. Enter username 'student'\n2. Enter password 'incorrectPassword'\n3. Click 'Submit'",
                        test_data="Username: student, Password: incorrectPassword",
                        expected_result="Login failed. Error message displayed: 'Your password is invalid!'",
                        priority="High",
                        test_type="Negative",
                        automation_feasibility="High",
                    ),
                ]
                st.session_state["target_url"] = "https://practicetestautomation.com/practice-test-login/"
                st.session_state["project_name"] = "Practice Test Automation"
                st.session_state["test_cases"] = pta_cases
                st.session_state["approved_tc_ids"] = {c.test_case_id for c in pta_cases}
                st.success("Loaded Practice Test Automation suite! Target URL set to https://practicetestautomation.com/practice-test-login/.")
                st.rerun()

    # ── Tab 4: AI Generator (OpenAI) ──
    with gen_tab4:
        st.markdown("#### 🤖 Generate Test Cases with OpenAI")
        has_api_key = False
        try:
            get_api_key()
            has_api_key = True
        except EnvironmentError:
            pass

        if not has_api_key:
            st.warning("🔑 **OpenAI API Key Not Found** — enter your key below or in the sidebar to generate with OpenAI.")
            c_k1, c_k2 = st.columns([3, 1])
            with c_k1:
                inline_key = st.text_input(
                    "Enter OpenAI API Key:",
                    type="password",
                    placeholder="sk-proj-...",
                    key="inline_api_key_tab",
                )
            with c_k2:
                st.write("")
                st.write("")
                if st.button("Save API Key", key="save_api_inline_btn") and inline_key.strip():
                    os.environ["OPENAI_API_KEY"] = inline_key.strip()
                    st.success("API key saved!")
                    st.rerun()
        else:
            st.success("✅ OpenAI API Key is configured and ready.")

        gen_clicked = st.button(
            "🚀 Generate with OpenAI",
            type="primary",
            use_container_width=True,
            disabled=not bool(req_text.strip()),
            key="openai_gen_btn",
        )
        if gen_clicked:
            if not analysis:
                analysis = analyse_requirements(req_text)
                st.session_state["analysis"] = analysis

            progress = st.progress(0, text="Sending requirements to AI QA generator...")
            try:
                progress.progress(30, text="Waiting for OpenAI response...")
                raw = generate_test_cases(req_text, analysis)
                progress.progress(70, text="Parsing test case objects...")
                cases = parse_ai_response(raw)
                st.session_state["test_cases"] = cases
                st.session_state["approved_tc_ids"] = {c.test_case_id for c in cases}
                progress.progress(100, text="Done!")
                st.success(f"Generated {len(cases)} test cases!")
                st.rerun()
            except Exception as e:
                st.error(f"Generation error: {e}")
            finally:
                progress.empty()

    # ── Test Suite Spreadsheet & Manager (Always Visible) ──
    st.markdown("---")
    st.markdown(f"### 📋 Current Test Suite ({len(test_cases)} Test Cases, {len(st.session_state.get('approved_tc_ids', set()))} Approved)")

    if not test_cases:
        st.info("ℹ️ No test cases in the suite yet. Use **✍️ Add Manually (Form)** above to add your own, **⚡ Rule-Based Generator** to auto-generate from text, or **📦 Load Preset Test Suites** to test immediately!")
    else:
        df_full = test_cases_to_dataframe(test_cases)

        col_f1, col_f2, col_f3 = st.columns([3, 2, 2])
        with col_f1:
            q = st.text_input("Filter test cases:", placeholder="Search scenario, steps...")
        with col_f2:
            p_sel = st.multiselect("Priority:", sorted(VALID_PRIORITIES))
        with col_f3:
            t_sel = st.multiselect("Test Type:", sorted(VALID_TEST_TYPES))

        df_filtered = filter_test_cases(df_full, search_query=q, priority_filter=p_sel, type_filter=t_sel)

        c_cnt, c_clr = st.columns([4, 1])
        with c_cnt:
            st.caption(f"Showing **{len(df_filtered)}** of **{len(df_full)}** test cases. Double-click any cell below to edit or click '+' to add rows:")
        with c_clr:
            if st.button("🗑️ Clear All Cases", help="Removes all test cases so you can start fresh"):
                st.session_state["test_cases"] = []
                st.session_state["approved_tc_ids"] = set()
                st.rerun()

        edited_df = st.data_editor(
            df_filtered.reset_index(drop=True),
            use_container_width=True,
            num_rows="dynamic",
            column_config={
                "Test Case ID": st.column_config.TextColumn("Test ID", width="small"),
                "Requirement ID": st.column_config.TextColumn("Req ID", width="small"),
                "Test Scenario": st.column_config.TextColumn("Scenario", width="large"),
                "Preconditions": st.column_config.TextColumn("Preconditions", width="medium"),
                "Test Steps": st.column_config.TextColumn("Steps", width="large"),
                "Test Data": st.column_config.TextColumn("Test Data", width="medium"),
                "Expected Result": st.column_config.TextColumn("Expected Result", width="large"),
                "Priority": st.column_config.SelectboxColumn("Priority", options=sorted(VALID_PRIORITIES), width="small"),
                "Test Type": st.column_config.SelectboxColumn("Type", options=sorted(VALID_TEST_TYPES), width="medium"),
                "Automation Feasibility": st.column_config.SelectboxColumn("Feasibility", options=sorted(VALID_AUTOMATION_FEASIBILITY), width="small"),
            },
            hide_index=True,
            key="tc_data_editor",
        )
        st.session_state["edited_df"] = edited_df

        # Auto-sync any added or modified rows in edited_df to session state
        parsed_cases = _dataframe_to_test_cases(edited_df)
        if parsed_cases:
            curr_cases = st.session_state.get("test_cases", [])
            curr_tuples = [(c.test_case_id, c.test_scenario, c.test_data, c.test_steps, c.expected_result) for c in curr_cases]
            new_tuples = [(c.test_case_id, c.test_scenario, c.test_data, c.test_steps, c.expected_result) for c in parsed_cases]

            if curr_tuples != new_tuples:
                st.session_state["test_cases"] = parsed_cases
                # Ensure newly added IDs are approved by default
                curr_appr = set(st.session_state.get("approved_tc_ids", set()))
                for c in parsed_cases:
                    if c.test_case_id and c.test_case_id not in [old.test_case_id for old in curr_cases]:
                        curr_appr.add(c.test_case_id)
                st.session_state["approved_tc_ids"] = curr_appr
                test_cases = parsed_cases
                st.rerun()

        # Approval Selector
        st.markdown("### ✅ Approve Test Cases for Automation")
        st.caption("Only approved test cases are executed in the browser automation runner.")

        all_ids = [c.test_case_id for c in test_cases if c.test_case_id]
        
        c_sel_all, c_desel = st.columns([1, 5])
        with c_sel_all:
            if st.button("Select All", use_container_width=True, key="appr_sel_all"):
                st.session_state["approved_tc_ids"] = set(all_ids)
                st.rerun()

        approved = st.multiselect(
            "Select test cases approved for browser execution:",
            options=all_ids,
            default=[tid for tid in all_ids if tid in st.session_state.get("approved_tc_ids", set(all_ids))],
            key="approved_tc_selector",
        )
        st.session_state["approved_tc_ids"] = set(approved)

        # ── Direct Execution Controls on Test Case Generator tab ──
        st.markdown("---")
        st.markdown("### 🚀 Execute Test Suite")
        target_url = st.session_state.get("target_url", "http://localhost:5000/login")
        approved_cases = [c for c in test_cases if c.test_case_id in st.session_state.get("approved_tc_ids", set())]

        col_tgt, col_stat = st.columns([3, 2])
        with col_tgt:
            st.markdown(f"**Target Application URL:** `{target_url}`")
        with col_stat:
            st.markdown(f"**Approved for Run:** `{len(approved_cases)}` of `{len(test_cases)}` cases")

        c_run1, c_run2, c_run3 = st.columns([3, 2, 2])
        with c_run1:
            if st.button("▶️ Execute Approved Tests Now", type="primary", use_container_width=True, key="exec_from_generator_tab"):
                if not approved_cases:
                    st.error("No test cases selected for execution. Please select at least one test case above.")
                else:
                    results = _execute_playwright_suite(
                        approved_cases=approved_cases,
                        target_url=target_url,
                        headless=False,
                        slow_mo=0.6,
                        timeout=10,
                    )
                    st.success(f"Executed {len(results)} test cases successfully!")
                    st.rerun()

        with c_run2:
            if st.button("🎛️ Advanced Execution Controls", use_container_width=True, key="goto_exec_controls"):
                st.session_state["current_tab"] = "🚀 Test Execution"
                if "nav_radio" in st.session_state:
                    st.session_state["nav_radio"] = "🚀 Test Execution"
                st.rerun()

        with c_run3:
            excel_bytes = build_excel(test_cases, analysis, project_name=st.session_state.get("project_name", "QA Project"))
            st.download_button(
                "📥 Export to Excel",
                data=excel_bytes,
                file_name=f"test_cases_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )


def _dataframe_to_test_cases(df: pd.DataFrame) -> List[TestCase]:
    """Convert an edited DataFrame back into structured TestCase objects."""
    from app.test_case_generator import TestCase
    cases = []
    for _, row in df.iterrows():
        tid = str(row.get("Test Case ID", "") or "").strip()
        scen = str(row.get("Test Scenario", "") or "").strip()
        # Skip completely empty rows
        if not tid and not scen:
            continue
        cases.append(
            TestCase(
                test_case_id=tid or f"TC-{len(cases)+1:03d}",
                requirement_id=str(row.get("Requirement ID", "REQ-001") or "REQ-001"),
                test_scenario=scen or "Custom scenario",
                preconditions=str(row.get("Preconditions", "User is on login page") or "User is on login page"),
                test_steps=str(row.get("Test Steps", "") or ""),
                test_data=str(row.get("Test Data", "N/A") or "N/A"),
                expected_result=str(row.get("Expected Result", "Success") or "Success"),
                priority=str(row.get("Priority", "Medium") or "Medium"),
                test_type=str(row.get("Test Type", "Positive") or "Positive"),
                automation_feasibility=str(row.get("Automation Feasibility", "High") or "High"),
            )
        )
    return cases


# ---------------------------------------------------------------------------
# Tab 4: Test Execution
# ---------------------------------------------------------------------------

def _render_test_execution() -> None:
    st.subheader("🚀 Playwright Browser Automation Execution")

    st.info("💡 **How it works:** When you execute tests with **Visible Window** selected, Playwright launches its **own dedicated browser window** on your screen. You will see it navigate, type into each input field, and submit. *(Note: It will not type into your existing manual browser tabs — it runs in its own automated browser window).*")

    target_url = st.session_state.get("target_url", "http://localhost:5000/login")
    approved_ids = st.session_state.get("approved_tc_ids", set())
    test_cases: List[TestCase] = st.session_state.get("test_cases", [])

    col_cfg1, col_cfg2 = st.columns(2)
    with col_cfg1:
        st.text_input("Active Target URL", value=target_url, disabled=True)
        browser_mode = st.radio(
            "Browser Execution Mode:",
            ["🖥️ Visible Window (Watch live on desktop)", "👻 Headless (Run in background)"],
            index=0,
            help="Select 'Visible Window' to watch Chromium pop up and type live.",
        )
        headless = (browser_mode == "👻 Headless (Run in background)")
        if not headless:
            slow_mo = st.slider("Visual Delay / Slow Motion (seconds per action)", min_value=0.2, max_value=2.0, value=0.6, step=0.1, help="Slows down typing so you can easily watch each keystroke.")
        else:
            slow_mo = 0.0
    with col_cfg2:
        timeout = st.slider("Playwright Timeout (seconds)", min_value=3, max_value=30, value=10)
        safe_mode = is_safe_mode()
        st.checkbox("Safe Mode Active", value=safe_mode, disabled=True, help="Destructive actions (delete, purchase) are prevented.")

    approved_cases = [c for c in test_cases if c.test_case_id in approved_ids]

    st.markdown(f"**Approved Test Cases Ready:** `{len(approved_cases)}` of `{len(test_cases)}`")

    if not is_url_allowed(target_url):
        st.error(f"⛔ Cannot execute: `{target_url}` is not in the approved domain allowlist.")
        return

    if not approved_cases:
        st.warning("⚠️ No test cases have been approved for execution. Go to **Test Case Generator** to approve or add test cases.")
        return

    col_run, _ = st.columns([2, 5])
    with col_run:
        start_exec = st.button("▶️ Execute Approved Tests", type="primary", use_container_width=True)

    if start_exec:
        results = _execute_playwright_suite(
            approved_cases=approved_cases,
            target_url=target_url,
            headless=headless,
            slow_mo=slow_mo,
            timeout=timeout,
        )
        st.success(f"Executed {len(results)} test cases successfully!")
        st.rerun()

    # Display execution results
    exec_results = st.session_state.get("execution_results", [])
    if exec_results:
        st.markdown("---")
        st.markdown("### 📋 Execution Results & Visual Evidence")

        # Visual screenshot highlights
        screenshots_with_labels = [
            (r.get("test_case_id"), r.get("test_scenario"), r.get("screenshot_path"), r.get("status"))
            for r in exec_results
            if r.get("screenshot_path") and os.path.exists(r.get("screenshot_path"))
        ]
        if screenshots_with_labels:
            with st.expander("📸 View Captured Browser Screenshots (Visual Proof)", expanded=True):
                cols = st.columns(min(len(screenshots_with_labels), 3))
                for idx, (tc_id, scen, path, st_val) in enumerate(screenshots_with_labels):
                    col = cols[idx % len(cols)]
                    with col:
                        col.image(path, caption=f"[{st_val}] {tc_id}", use_container_width=True)

        for r in exec_results:
            status = r.get("status", "UNKNOWN")
            tc_id = r.get("test_case_id", "")
            scen = r.get("test_scenario", "")
            badge = "badge-pass" if status == "PASSED" else "badge-fail" if status in ("FAILED", "ERROR") else "badge-blocked"

            with st.expander(f"{tc_id} — {scen} — {status}", expanded=True):
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown(f"**Status:** <span class='{badge}'>{status}</span>", unsafe_allow_html=True)
                    st.markdown(f"**Expected:** {r.get('expected_result')}")
                    st.markdown(f"**Actual:** {r.get('actual_result')}")
                    if r.get("error_message"):
                        st.markdown(f"**Error:** `{r.get('error_message')}`")
                with c2:
                    st.markdown(f"**Duration:** {r.get('duration_seconds', 0.0):.2f}s")
                    screenshot = r.get("screenshot_path")
                    if screenshot and os.path.exists(screenshot):
                        st.image(screenshot, caption=f"Browser Snapshot: {tc_id}", use_container_width=True)
                    elif screenshot:
                        st.caption(f"Screenshot recorded at `{screenshot}`")

                with st.expander("📜 Full Execution Logs"):
                    st.code(r.get("logs", "No logs recorded."), language="text")

        # Download Reports
        st.markdown("---")
        st.markdown("### 📥 Download Reports")
        c_rep1, c_rep2 = st.columns(2)
        with c_rep1:
            excel_bytes = build_excel(
                test_cases=test_cases,
                analysis=st.session_state.get("analysis"),
                execution_results=exec_results,
                project_name=st.session_state.get("project_name", "AI Testing Agent"),
            )
            st.download_button(
                "📥 Download Detailed Excel Report",
                data=excel_bytes,
                file_name=f"test_run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
        with c_rep2:
            try:
                defects = list(st.session_state.get("defect_reports", {}).values())
                pdf_bytes = build_pdf_report(
                    project_name=st.session_state.get("project_name", "AI Testing Agent"),
                    target_url=target_url,
                    environment=st.session_state.get("testing_env", "Local"),
                    test_results=exec_results,
                    run_stats={
                        "total": len(exec_results),
                        "passed": sum(1 for x in exec_results if x.get("status") == "PASSED"),
                        "failed": sum(1 for x in exec_results if x.get("status") in ("FAILED", "ERROR")),
                        "blocked": sum(1 for x in exec_results if x.get("status") == "BLOCKED"),
                        "skipped": sum(1 for x in exec_results if x.get("status") == "SKIPPED"),
                    },
                    defect_reports=defects,
                )
                st.download_button(
                    "📄 Download Formal PDF Report",
                    data=pdf_bytes,
                    file_name=f"test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                )
            except Exception as e:
                st.info(f"PDF generator notice: {e}")


# ---------------------------------------------------------------------------
# Tab 5: Bug Reports (AI Failure Analysis)
# ---------------------------------------------------------------------------

def _render_bug_reports() -> None:
    st.subheader("🐛 AI-Assisted Defect & Failure Analysis")
    st.markdown("Analyze failed test runs with AI to extract root causes, steps to reproduce, and draft defect reports.")

    exec_results = st.session_state.get("execution_results", [])
    failed_results = [r for r in exec_results if r.get("status") in ("FAILED", "ERROR")]

    if not failed_results:
        st.success("🎉 No failed tests in the current execution run!")
        return

    st.warning(f"Found **{len(failed_results)}** failed test case(s) requiring analysis.")

    defect_reports = st.session_state.get("defect_reports", {})

    for r in failed_results:
        tc_id = r.get("test_case_id")
        scenario = r.get("test_scenario")
        actual = r.get("actual_result")
        expected = r.get("expected_result")
        err = r.get("error_message")
        logs = r.get("logs", "")

        with st.expander(f"❌ {tc_id} — {scenario}", expanded=True):
            st.markdown(f"**Observed Actual Result:** `{actual}`")
            if err:
                st.markdown(f"**Observed Error:** `{err}`")

            if tc_id not in defect_reports:
                if st.button(f"🤖 Analyze Failure with AI ({tc_id})", key=f"btn_ai_{tc_id}"):
                    with st.spinner("AI is analyzing execution evidence..."):
                        try:
                            defect = analyse_failure(
                                test_case_id=tc_id,
                                test_scenario=scenario,
                                expected_result=expected,
                                actual_result=actual,
                                error_message=err,
                                log_snippet=logs[-1500:],
                            )
                            defect_reports[tc_id] = defect
                            st.session_state["defect_reports"] = defect_reports
                            st.rerun()
                        except Exception as e:
                            st.error(f"AI Failure Analysis error: {e}")
            else:
                defect = defect_reports[tc_id]
                st.markdown(f"### 📋 Defect Report: {defect.get('defect_title', 'Defect')}")

                c_sev, c_conf = st.columns(2)
                c_sev.markdown(f"**Severity:** `{defect.get('severity', 'Medium')}`")
                c_conf.markdown(f"**AI Confidence:** `{defect.get('ai_confidence', 'Medium')}`")

                st.markdown("#### 🔍 Failure Summary")
                st.info(f"<span class='tag-observed'>[Observed]</span> {defect.get('failure_summary')}", unsafe_allow_html=True)

                st.markdown("#### 💡 Hypothesized Root Causes")
                for rc in defect.get("root_causes", []):
                    st.markdown(f"- <span class='tag-hypothesis'>[AI Hypothesis]</span> {rc}", unsafe_allow_html=True)

                st.markdown("#### 🔄 Steps to Reproduce")
                st.text(defect.get("steps_to_reproduce", ""))


# ---------------------------------------------------------------------------
# Tab 6: Execution History
# ---------------------------------------------------------------------------

def _render_execution_history() -> None:
    st.subheader("📜 Test Execution History")
    st.markdown("Complete record of previous test execution runs stored in SQLite (`test_history.db`).")

    runs = get_all_runs()
    if not runs:
        st.info("No execution history recorded yet.")
        return

    df_runs = pd.DataFrame(runs)
    st.dataframe(
        df_runs[["id", "project_name", "target_url", "environment", "started_at", "total", "passed", "failed", "blocked"]],
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("### 🔎 Drilldown into Past Run")
    run_ids = [r["id"] for r in runs]
    selected_run_id = st.selectbox("Select Run ID to view details:", run_ids)

    if selected_run_id:
        details = get_results_for_run(selected_run_id)
        if details:
            df_details = pd.DataFrame(details)
            display_cols = ["test_case_id", "test_scenario", "status", "expected_result", "actual_result", "duration_seconds"]
            valid_cols = [c for c in display_cols if c in df_details.columns]
            st.dataframe(df_details[valid_cols], use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Tab 7: Settings
# ---------------------------------------------------------------------------

def _render_settings() -> None:
    st.subheader("⚙️ Settings & Security Guardrails")

    st.markdown("### 🔑 OpenAI API Configuration")
    has_key = False
    try:
        curr_key = get_api_key()
        has_key = True
    except EnvironmentError:
        curr_key = ""

    user_key = st.text_input(
        "OpenAI API Key:",
        value=curr_key if curr_key and not curr_key.startswith("sk-your") else "",
        type="password",
        help="Stored in process memory only. Set OPENAI_API_KEY in .env for persistence.",
    )
    if user_key:
        os.environ["OPENAI_API_KEY"] = user_key.strip()
        st.success("✅ OpenAI API Key loaded.")

    model_options = ["gpt-4o-mini", "gpt-4o", "gpt-4-turbo"]
    current_model = get_model()
    idx = model_options.index(current_model) if current_model in model_options else 0
    sel_model = st.selectbox("OpenAI Model", model_options, index=idx)
    os.environ["OPENAI_MODEL"] = sel_model

    st.markdown("---")
    st.markdown("### 🛡️ Browser Automation Allowlist")
    st.caption("Only websites listed here can be targeted by Playwright browser automation.")

    allowed_domains = sorted(list(get_allowed_domains()))
    st.write(f"Currently approved domains: `{', '.join(allowed_domains)}`")

    new_domain = st.text_input("Add new allowed domain (e.g., staging.example.com):")
    if st.button("Add to Domain Allowlist") and new_domain.strip():
        existing = os.environ.get("ALLOWED_DOMAINS", "")
        updated = f"{existing},{new_domain.strip()}".strip(",")
        os.environ["ALLOWED_DOMAINS"] = updated
        st.success(f"Added `{new_domain.strip()}` to allowlist!")
        st.rerun()

    st.markdown("---")
    st.markdown("### 🔒 Safety Controls")
    st.markdown("- **Safe Mode:** Destructive actions (`delete`, `checkout`, `change_password`) are blocked by default.")
    st.markdown("- **Credential Sanitization:** Passwords and tokens are automatically redacted from logs and reports.")
    st.markdown("- **Private Network Guard:** Private IP subnets are blocked unless explicitly registered.")


# ---------------------------------------------------------------------------
# Main App Router
# ---------------------------------------------------------------------------

def run_app() -> None:
    configure_page()
    st.markdown(_CSS, unsafe_allow_html=True)
    _init_state()
    selected_tab = _render_sidebar()
    _render_header()

    if selected_tab == "📊 Dashboard":
        _render_dashboard()
    elif selected_tab == "📋 Requirement Analysis":
        _render_requirement_analysis()
    elif selected_tab == "🧪 Test Case Generator":
        _render_test_case_generator()
    elif selected_tab == "🚀 Test Execution":
        _render_test_execution()
    elif selected_tab == "🐛 Bug Reports":
        _render_bug_reports()
    elif selected_tab == "📜 Execution History":
        _render_execution_history()
    elif selected_tab == "⚙️ Settings":
        _render_settings()

