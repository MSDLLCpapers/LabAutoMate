"""
LabAutoMate — AI-Powered Lab Automation Code Generator
Main Streamlit application with two workflow tabs:
  Tab 1: Driver & Script Generation (new instrument drivers + automation scripts)
  Tab 2: Dash Web Application Generation (instrument control web interfaces)
"""

import io, os, zipfile, datetime, ast
import importlib.util
import streamlit as st
from pathlib import Path
from dotenv import load_dotenv

from labautomate.catalog import predefined_prompts, pump_file_catalog, SHOWCASE2_DRIVER
from labautomate.driver_loader import get_drivers_path, read_driver_source, get_driver_catalog
from labautomate.llm_providers import (
    LLMConfig, PROVIDERS,
    get_provider_names, get_models_for_provider, get_default_model, get_default_endpoint,
    merge_models, parse_model_import,
    API_KEY_HELP, ENDPOINT_HELP, MODEL_IMPORT_PLACEHOLDER,
    validate_config, complete, stream,
)
from labautomate.functions import (
    generate_function_map,
    build_final_prompt,
    build_verified_imports_block,
    generate_dash_code,
    stream_dash_code,
    generate_readme,
    generate_patch,
    generate_full_code,
    detect_drivers_for_automation,
    generate_flow_diagram,
    generate_ui_mockup,
    refine_design_plan,
)
from labautomate.pdf_utils import extract_pdf_text
from labautomate.prompt_templates import (
    get_template, get_system_prompt, validate_prompt_structure,
    build_enhanced_prompt, BRANDING_PROMPT, TEMPLATE_SECTIONS,
)
from labautomate.verification import (
    run_full_verification, verify_driver_with_ai, generate_test_code,
    VerificationResult,
)

load_dotenv()

PYSOFTCHECK_URL = (
    "https://www.huber-usa.com/fileadmin/user_upload/huber-online.com/"
    "Downloads/Software/pysoftcheck-3.0.0-py3-none-any.whl"
)

# ─────────────────────────────────────────────────────────────────────
# Page Configuration
# ─────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="LabAutoMate",
    page_icon="⚗️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────────────
# Custom CSS for app branding
# ─────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .stApp { background-color: #F7F7F7; }
    .main-header {
        color: #2563EB;
        font-size: 2rem;
        font-weight: 700;
        margin-bottom: 0.5rem;
    }
    .sub-header { color: #1E293B; font-size: 1.1rem; }
    div[data-testid="stSidebar"] { background-color: #1E293B; }
    div[data-testid="stSidebar"] label,
    div[data-testid="stSidebar"] .stMarkdown p,
    div[data-testid="stSidebar"] .stMarkdown h1,
    div[data-testid="stSidebar"] .stMarkdown h2,
    div[data-testid="stSidebar"] .stMarkdown h3 { color: #FFFFFF; }
    .stTabs [data-baseweb="tab"] {
        font-size: 1rem;
        font-weight: 600;
    }
    .stTabs [aria-selected="true"] {
        border-bottom-color: #2563EB;
        color: #2563EB;
    }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────────────────────────────
logo_path = Path(__file__).parent / "assets" / "Logo.png"
if logo_path.exists():
    col_logo, col_title = st.columns([1, 8])
    with col_logo:
        st.image(str(logo_path), width=80)
    with col_title:
        st.markdown('<p class="main-header">LabAutoMate</p>', unsafe_allow_html=True)
        st.markdown(
            '<p class="sub-header">AI-Powered Code Generation for Chemistry Lab Automation</p>',
            unsafe_allow_html=True,
        )
else:
    st.markdown('<p class="main-header">LabAutoMate</p>', unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────
# Sidebar — LLM Configuration
# ─────────────────────────────────────────────────────────────────────
def _add_imported_models(provider: str):
    """Import button callback: add the pasted model ids to this provider's dropdown."""
    valid, rejected = parse_model_import(st.session_state.get(f"import_text_{provider}", ""))
    if not valid:
        st.session_state[f"import_status_{provider}"] = ("error", "No valid model ids found.")
        return
    imported = st.session_state.setdefault("imported_models", {}).setdefault(provider, [])
    for model_id in valid:
        if model_id not in imported:
            imported.append(model_id)
    st.session_state[f"model_{provider}"] = valid[0]
    message = f"Added {len(valid)} model(s) to the list."
    if rejected:
        message += f" Skipped: {', '.join(rejected)}"
    st.session_state[f"import_status_{provider}"] = ("success", message)


def _clear_imported_models(provider: str):
    """Clear callback: remove this provider's imported models from the dropdown."""
    imported = st.session_state.get("imported_models", {}).pop(provider, [])
    if st.session_state.get(f"model_{provider}") in imported:
        st.session_state[f"model_{provider}"] = get_default_model(provider)
    st.session_state[f"import_status_{provider}"] = ("success", "Imported models cleared.")


with st.sidebar:
    st.markdown("### Model Configuration")

    provider = st.selectbox(
        "Provider",
        get_provider_names(),
        index=0,
    )

    imported_for_provider = st.session_state.get("imported_models", {}).get(provider, [])
    models = merge_models(get_models_for_provider(provider), imported_for_provider)
    default_model = get_default_model(provider)
    model_key = f"model_{provider}"
    if model_key not in st.session_state:
        st.session_state[model_key] = default_model if default_model in models else models[0]
    model = st.selectbox("Model", models, key=model_key)

    with st.expander("Import a model not listed"):
        st.text_area(
            "Model ID(s) or model list JSON",
            key=f"import_text_{provider}",
            height=100,
            placeholder=MODEL_IMPORT_PLACEHOLDER,
            help=(
                "Paste one or more model ids separated by commas, spaces or new lines, "
                "or the JSON returned by the provider's model list endpoint. The ids "
                "are sent to the provider exactly as typed."
            ),
        )
        st.button(
            "Add to model list",
            key=f"import_btn_{provider}",
            on_click=_add_imported_models,
            args=(provider,),
        )
        if imported_for_provider:
            st.button(
                "Clear imported models",
                key=f"clear_btn_{provider}",
                on_click=_clear_imported_models,
                args=(provider,),
            )
        status = st.session_state.pop(f"import_status_{provider}", None)
        if status:
            kind, message = status
            if kind == "success":
                st.success(message)
            else:
                st.error(message)

    st.markdown("---")

    api_key = st.text_input(
        "API Key",
        value=os.getenv("LABAUTOMATE_API_KEY", ""),
        type="password",
        help=API_KEY_HELP,
    )

    endpoint = st.text_input(
        "Endpoint URL",
        value=os.getenv("LABAUTOMATE_ENDPOINT", get_default_endpoint(provider)),
        key=f"endpoint_{provider}",
        help=ENDPOINT_HELP,
    )

    st.markdown("---")
    st.markdown(
        "<small style='color:#60A5FA'>PyLabDrivers v0.2.0 | "
        f"{len(pump_file_catalog)} drivers available</small>",
        unsafe_allow_html=True,
    )


def _get_config() -> LLMConfig:
    """Build LLMConfig from sidebar settings."""
    return LLMConfig(
        provider=provider,
        model=model,
        api_key=api_key,
        endpoint=endpoint,
    )


# Guard: require API key
if not api_key:
    st.warning("Please enter your API key in the sidebar to continue.")
    st.stop()

# ─────────────────────────────────────────────────────────────────────
# Helper utilities
# ─────────────────────────────────────────────────────────────────────

def _fetch_url_text(url: str, max_chars: int = 20000) -> str:
    """Fetch a URL and return its text content with HTML tags stripped."""
    import urllib.request, urllib.error, html, re as _re
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        # Strip <script> and <style> blocks
        raw = _re.sub(r"<(script|style)[^>]*>.*?</(script|style)>", " ", raw, flags=_re.S | _re.I)
        # Strip remaining HTML tags
        raw = _re.sub(r"<[^>]+>", " ", raw)
        # Decode HTML entities and collapse whitespace
        raw = html.unescape(raw)
        raw = _re.sub(r"[ \t]+", " ", raw)
        raw = _re.sub(r"\n{3,}", "\n\n", raw)
        return raw.strip()[:max_chars]
    except Exception as e:
        return f"[ERROR fetching {url}: {e}]"


def _load_reference_files(directory: str, label: str) -> list:
    """Load .py files from a directory, return list of (name, content)."""
    files = []
    dir_path = Path(__file__).parent / directory
    if dir_path.exists():
        for f in sorted(dir_path.glob("*.py")):
            files.append((f.name, f.read_text(encoding="utf-8")))
    return files


def _pdf_context(pdf_files) -> str:
    """Return the text of uploaded PDFs as prompt sections (empty string if none)."""
    parts = [
        f"## Additional Documentation: {f.name}\n\n{extract_pdf_text(f.getvalue())}"
        for f in pdf_files or []
    ]
    return "\n\n" + "\n\n".join(parts) if parts else ""


def _syntax_check(code: str) -> tuple:
    """Return (is_valid, error_message)."""
    try:
        ast.parse(code)
        return True, ""
    except SyntaxError as e:
        return False, str(e)


def _make_zip(files: dict) -> bytes:
    """Create a ZIP from {filename: content} dict."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


def _extract_pip_packages(app_code: str) -> tuple:
    """
    Parse generated Dash app code and return:
      (pip_packages: list[str], vendor_warnings: list[str])
    pip_packages    -- third-party packages installable via pip
    vendor_warnings -- notes for packages requiring manual placement
    """
    import ast as _ast

    _STDLIB = {
        "os","sys","re","json","time","math","threading","subprocess","collections",
        "functools","itertools","pathlib","io","struct","typing","abc","copy",
        "datetime","random","string","textwrap","logging","warnings","contextlib",
        "dataclasses","enum","inspect","traceback","signal","queue","uuid","hashlib",
        "base64","urllib","http","socket","ssl","csv","sqlite3","tempfile","shutil",
        "platform","gc","weakref","array","bisect","heapq","decimal","fractions",
        "statistics","calendar","locale","gettext","argparse","configparser",
    }
    _PIP_MAP = {
        "cv2": "opencv-python",
        "PIL": "Pillow",
        "sklearn": "scikit-learn",
        "bs4": "beautifulsoup4",
        "serial": "pyserial",
        "yaml": "pyyaml",
        "dotenv": "python-dotenv",
        "dash_bootstrap_components": "dash-bootstrap-components",
        "opcua": "opcua",
        "asyncua": "asyncua",
    }
    # Vendor SDKs / local files that cannot be pip-installed
    _VENDOR = {
        "oceandirect": (
            "oceandirect (Ocean Optics OceanDirect SDK) -- NOT pip-installable.\n"
            "  Place the 'oceandirect' SDK folder next to dash_app.py.\n"
            "  Obtain from Ocean Optics with your instrument (purchased SDK)."
        ),
        "rseriesopc": (
            "rseriesopc (Vapourtec Python API) -- Make sure to install the\n"
            "  rseriesopc Python API package from Vapourtec before launching."
        ),
        "softcheck": (
            "softcheck (pySoftcheck for Huber chiller) -- NOT on PyPI.\n"
            "  Download the pySoftcheck wheel from Huber:\n"
            "  https://www.huber-usa.com/fileadmin/user_upload/huber-online.com/Downloads/Software/pysoftcheck-3.0.0-py3-none-any.whl\n"
            "  Place the .whl file next to dash_app.py."
        ),
        "oceanoptics": (
            "oceanoptics -- local driver file, NOT on PyPI.\n"
            "  Place oceanoptics.py next to dash_app.py."
        ),
        "OceanDirectAPI": (
            "OceanDirectAPI -- part of the OceanDirect SDK.\n"
            "  Place the 'oceandirect' SDK folder next to dash_app.py."
        ),
    }

    try:
        tree = _ast.parse(app_code)
    except SyntaxError:
        return (["dash", "dash-bootstrap-components", "plotly", "pandas", "numpy", "python-dotenv"], [])

    roots = set()
    for node in _ast.walk(tree):
        if isinstance(node, _ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, _ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])

    # pylabdrivers is a local package installed via editable install in Step 4 of launch.bat
    _LOCAL_PKGS = {"pylabdrivers"}

    baseline = ["dash", "dash-bootstrap-components", "plotly", "pandas", "numpy", "python-dotenv"]
    seen = set(baseline)
    pip_pkgs = list(baseline)
    vendor_notes = []

    for root in sorted(roots):
        if root in _STDLIB or root in seen or root in _LOCAL_PKGS:
            continue
        if root in _VENDOR:
            vendor_notes.append(_VENDOR[root])
            seen.add(root)
            continue
        pkg = _PIP_MAP.get(root, root)
        if pkg not in seen:
            pip_pkgs.append(pkg)
            seen.add(pkg)

    return pip_pkgs, vendor_notes


def _make_dash_batch(app_filename: str = "dash_app.py", app_code: str = "") -> bytes:
    """
    Build a uv-based launch.bat for a generated Dash app.
    Scans app_code imports to install all pip-installable packages automatically.
    Returns raw bytes (CRLF, ASCII) -- safe to embed in a ZIP and download.
    """
    pip_packages, vendor_warnings = _extract_pip_packages(app_code)
    pkg_list = " ".join(pip_packages)

    vendor_echo = []
    if vendor_warnings:
        vendor_echo += [
            "echo.",
            "echo  ============================================",
            "echo   MANUAL SETUP REQUIRED -- read carefully",
            "echo  ============================================",
            "echo.",
        ]
        for note in vendor_warnings:
            for note_line in note.split("\n"):
                vendor_echo.append(f"echo   {note_line}")
        vendor_echo += [
            "echo.",
            "echo  Place the required files/folders next to dash_app.py,",
            "echo  then press any key to continue launching the app.",
            "echo.",
            "pause",
        ]

    lines = [
        "@echo off",
        "title Dash App Launcher",
        'cd /d "%~dp0"',
        "echo.",
        "echo  ============================================",
        "echo   Dash Lab Application Launcher",
        "echo  ============================================",
        "echo.",
        "",
        "rem == Step 1: ensure uv is available ========================",
        "where uv >nul 2>&1",
        "if %errorlevel% neq 0 (",
        "    echo [SETUP] uv not found. Installing via PowerShell...",
        '    powershell -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"',
        "    if %errorlevel% neq 0 (",
        "        echo [ERROR] uv installation failed.",
        "        echo [ERROR] Install manually: https://github.com/astral-sh/uv",
        "        pause",
        "        exit /b 1",
        "    )",
        '    set "PATH=%USERPROFILE%\\.local\\bin;%PATH%"',
        "    where uv >nul 2>&1",
        "    if %errorlevel% neq 0 (",
        "        echo [INFO] uv installed. Close this window and run launch.bat again.",
        "        pause",
        "        exit /b 0",
        "    )",
        "    echo [OK] uv installed successfully.",
        ") else (",
        '    for /f "tokens=*" %%v in (\'uv --version\') do echo [OK] %%v found.',
        ")",
        "echo.",
        "",
        "rem == Step 2: create .venv if needed ========================",
        'if not exist ".venv\\Scripts\\python.exe" (',
        "    echo [SETUP] Creating virtual environment with uv...",
        "    uv venv .venv",
        "    if %errorlevel% neq 0 (",
        "        echo [ERROR] Failed to create virtual environment.",
        "        pause",
        "        exit /b 1",
        "    )",
        "    echo [OK] Virtual environment created.",
        ") else (",
        "    echo [OK] Virtual environment already exists.",
        ")",
        "echo.",
        "",
        "rem == Step 3: install all detected app dependencies =========",
        f"echo [SETUP] Installing: {pkg_list}",
        f'uv pip install -q --python ".venv\\Scripts\\python.exe" {pkg_list}',
        "if %errorlevel% neq 0 (",
        "    echo [ERROR] Failed to install dependencies.",
        "    pause",
        "    exit /b 1",
        ")",
        "echo [OK] Dependencies ready.",
        "echo.",
    ] + vendor_echo + [
        "",
        "rem == Step 4: install PyLabDrivers if not already installed =",
        'uv pip show --python ".venv\\Scripts\\python.exe" pylabdrivers >nul 2>&1',
        "if %errorlevel% equ 0 (",
        "    echo [OK] PyLabDrivers already installed.",
        "    goto :softcheck",
        ")",
        "",
        "rem Try sibling folder automatically first",
        'set "PLD_PATH=%~dp0..\\PyLabDrivers"',
        'if exist "%PLD_PATH%\\setup.py" goto :install_pld',
        "",
        "echo.",
        "echo [SETUP] PyLabDrivers is required to run this application.",
        "echo [SETUP] Please enter the full path to your PyLabDrivers folder.",
        "echo [SETUP] Example: C:\\Users\\YourName\\Documents\\PyLabDrivers",
        "echo [SETUP] Leave blank and press Enter to skip (may cause import errors).",
        "echo.",
        'set "PLD_PATH="',
        "set /p PLD_PATH=Path to PyLabDrivers: ",
        'if "%PLD_PATH%"=="" (',
        "    echo [WARN] Skipping PyLabDrivers installation.",
        "    goto :launch",
        ")",
        'if not exist "%PLD_PATH%\\setup.py" (',
        "    echo [ERROR] setup.py not found at: %PLD_PATH%",
        "    echo [ERROR] Check the path and run launch.bat again.",
        "    pause",
        "    exit /b 1",
        ")",
        "",
        ":install_pld",
        "rem Final check - skip if already installed by any previous means",
        'uv pip show --python ".venv\\Scripts\\python.exe" pylabdrivers >nul 2>&1',
        "if %errorlevel% equ 0 (",
        "    echo [OK] PyLabDrivers already installed, skipping reinstall.",
        "    goto :softcheck",
        ")",
        "echo [SETUP] Installing PyLabDrivers from: %PLD_PATH%",
        'uv pip install -q --python ".venv\\Scripts\\python.exe" -e "%PLD_PATH%"',
        "if %errorlevel% neq 0 (",
        "    echo [ERROR] Failed to install PyLabDrivers.",
        "    pause",
        "    exit /b 1",
        ")",
        "echo [OK] PyLabDrivers installed.",
        "echo.",
        "",
        ":softcheck",
        "rem == Step 5: install pySoftcheck (required by Huber driver) =",
        '".venv\\Scripts\\python.exe" -c "import softcheck" >nul 2>&1',
        "if %errorlevel% equ 0 (",
        "    echo [OK] pySoftcheck already installed.",
        "    goto :launch",
        ")",
        'set "SC_WHEEL="',
        'for %%F in ("%~dp0pysoftcheck-*.whl") do set "SC_WHEEL=%%~fF"',
        "if not defined SC_WHEEL (",
        "    echo [INFO] Optional: pySoftcheck not found. It is only needed for the Huber chiller driver.",
        "    echo [INFO] To enable it, download the pySoftcheck wheel from Huber:",
        "    echo [INFO]   https://www.huber-usa.com/fileadmin/user_upload/huber-online.com/Downloads/Software/pysoftcheck-3.0.0-py3-none-any.whl",
        "    echo [INFO] Place the .whl file next to this launch.bat and run it again.",
        "    goto :launch",
        ")",
        "echo [SETUP] Installing pySoftcheck from: %SC_WHEEL%",
        'uv pip install -q --python ".venv\\Scripts\\python.exe" "%SC_WHEEL%"',
        "if %errorlevel% neq 0 (",
        "    echo [WARN] pySoftcheck installation failed. Huber driver will be unavailable.",
        ") else (",
        "    echo [OK] pySoftcheck installed.",
        ")",
        "echo.",
        "",
        ":launch",
        "echo.",
        "echo [INFO] All dependencies ready.",
        f"echo [INFO] Starting {app_filename}...",
        "echo [INFO] Open http://localhost:8050 in your browser.",
        "echo [INFO] Press Ctrl+C in this window to stop.",
        "echo.",
        f'".venv\\Scripts\\python.exe" {app_filename}',
        "echo.",
        "pause",
    ]
    content = "\r\n".join(lines) + "\r\n"
    return content.encode("ascii", errors="replace")


TAB1_KEYS = [
    "tab1_code", "tab1_generated", "tab1_review", "tab1_tests",
    "pdf_text", "pdf_text_edit",
    "tab1_detected_drivers", "tab1_confirmed_drivers",
    "tab1_flow", "tab1_prompt", "tab1_last_mode",
    "tab1_url_content", "tab1_url_label",
]
TAB2_KEYS = [
    "tab2_code", "tab2_readme", "tab2_fmap", "tab2_drivers",
    "tab2_design", "tab2_custom_src", "tab2_dot", "tab2_final_prompt",
    "tab2_mockup", "tab2_prompt",
    "tab2_url_content", "tab2_url_label",
]


def _clear_tab(keys):
    for k in keys:
        st.session_state.pop(k, None)
    chk_keys = [k for k in list(st.session_state.keys()) if k.startswith("tab1_chk_")]
    for k in chk_keys:
        st.session_state.pop(k, None)
    st.rerun()


# ─────────────────────────────────────────────────────────────────────
# Main Tabs
# ─────────────────────────────────────────────────────────────────────
tab1, tab2 = st.tabs([
    "Driver & Script Generation",
    "Dash Web Application Generation",
])

# ═══════════════════════════════════════════════════════════════════════
# TAB 1: Driver & Script Generation
# ═══════════════════════════════════════════════════════════════════════
with tab1:
    col_title1, col_clear1 = st.columns([6, 1])
    with col_title1:
        st.markdown("### Generate New Instrument Drivers or Automation Scripts")
    with col_clear1:
        if st.button("Clear", key="tab1_clear", help="Clear all results and start fresh"):
            _clear_tab(TAB1_KEYS)

    st.markdown(
        "Upload a PDF manual to generate a new PyLabDrivers-compatible driver, "
        "or write a structured prompt to generate automation scripts that leverage "
        "existing drivers."
    )

    mode = st.radio(
        "Mode",
        ["New Driver from PDF Manual", "Automation Script"],
        horizontal=True,
        key="tab1_mode",
    )

    st.markdown("---")

    # ─── PDF Upload & Text Extraction ───────────────────────────────
    if mode == "New Driver from PDF Manual":
        col_pdf, col_preview = st.columns([1, 1])

        with col_pdf:
            st.markdown("#### Upload Communication Manual (PDF)")
            pdf_file = st.file_uploader(
                "Upload the instrument's communication/serial manual",
                type="pdf",
                key="pdf_manual",
            )

            page_range = st.text_input(
                "Page range (optional)",
                placeholder="e.g., 33-40 (leave empty for all pages)",
                help="Specify pages containing serial/communication protocol details.",
            )

            if pdf_file:
                with st.spinner("Extracting text from PDF..."):
                    pdf_bytes = pdf_file.read()
                    start_page = None
                    end_page = None
                    if page_range.strip():
                        parts = page_range.strip().split("-")
                        start_page = int(parts[0]) - 1
                        end_page = int(parts[-1]) if len(parts) > 1 else int(parts[0])

                    extracted_text = extract_pdf_text(pdf_bytes, start_page, end_page)
                    st.session_state["pdf_text"] = extracted_text
                    st.success(f"Extracted {len(extracted_text):,} characters from PDF.")

        with col_preview:
            if "pdf_text" in st.session_state:
                st.markdown("#### Extracted Text Preview")
                st.text_area(
                    "PDF content (editable — remove irrelevant sections if needed)",
                    st.session_state["pdf_text"],
                    height=300,
                    key="pdf_text_edit",
                )

        st.markdown("---")
        st.markdown("#### Reference Driver (from PyLabDrivers)")
        ref_driver = st.selectbox(
            "Select an existing driver as a style/structure reference",
            list(pump_file_catalog.keys()),
            index=list(pump_file_catalog.keys()).index("teledynereaxus.py")
            if "teledynereaxus.py" in pump_file_catalog else 0,
            key="ref_driver_select",
        )

        with st.expander("View reference driver source", expanded=False):
            ref_source = read_driver_source(ref_driver)
            st.code(ref_source, language="python")

    # ─── Structured Prompt Input ────────────────────────────────────
    st.markdown("---")
    st.markdown("#### Structured Prompt Statement")
    st.markdown(
        "*Follow the 5-section template: "
        "**1)** Project Overview, **2)** UI Design, **3)** Functionality & Logic, "
        "**4)** Technical Implementation, **5)** Documentation & References.*"
    )
    st.info(
        "The structured prompt strategy constrains the AI to generate code "
        "based only on your specifications — reducing hallucination by leaving "
        "no room for the model to invent methods, protocols, or formulas."
    )

    # When the mode changes, push the correct default into session state so
    # Streamlit actually refreshes the text area (value= is ignored once key exists)
    if st.session_state.get("tab1_last_mode") != mode:
        st.session_state["tab1_last_mode"] = mode
        if mode == "New Driver from PDF Manual":
            st.session_state["tab1_prompt"] = SHOWCASE2_DRIVER
        else:
            st.session_state["tab1_prompt"] = get_template("Automation Script")  # uses AUTOMATION_SCRIPT_TEMPLATE
    elif "tab1_prompt" not in st.session_state:
        st.session_state["tab1_prompt"] = SHOWCASE2_DRIVER

    prompt_text = st.text_area(
        "Enter your structured prompt",
        height=350,
        key="tab1_prompt",
    )

    # Validate prompt structure
    missing = validate_prompt_structure(prompt_text)
    if missing:
        st.warning(
            f"Missing sections: {', '.join(missing)}. "
            "All 5 sections are recommended for best results."
        )

    # ─── Auto-Detect Instruments (Automation Script only) ───────────
    if mode == "Automation Script":
        st.markdown("---")
        st.markdown("#### Instrument Auto-Detection")
        st.markdown(
            "Click **Detect Instruments** and the AI will identify which "
            "PyLabDrivers drivers your prompt needs. Review and adjust, then "
            "the driver source code will be injected before generation."
        )

        col_detect, _ = st.columns([2, 5])
        with col_detect:
            detect_clicked = st.button(
                "Detect Instruments", key="tab1_detect",
                help="Analyze your prompt and find matching PyLabDrivers drivers",
            )

        if detect_clicked:
            config_detect = _get_config()
            err = validate_config(config_detect)
            if err:
                st.error(err)
            elif not prompt_text.strip():
                st.warning("Please enter a prompt before detecting instruments.")
            else:
                try:
                    driver_catalog = get_driver_catalog()
                    with st.spinner("Detecting instruments from your prompt..."):
                        detected = detect_drivers_for_automation(
                            config_detect, prompt_text, driver_catalog
                        )
                    st.session_state["tab1_detected_drivers"] = detected
                    # Pre-set confirmed = detected (user can uncheck)
                    st.session_state["tab1_confirmed_drivers"] = list(detected)
                except Exception as e:
                    st.error(f"Detection failed: {e}")

        # Show checkboxes for any previously detected drivers
        if st.session_state.get("tab1_detected_drivers") is not None:
            detected = st.session_state["tab1_detected_drivers"]
            if detected:
                st.markdown("**Detected instruments — uncheck any you don't need:**")
                try:
                    driver_catalog = get_driver_catalog()
                except Exception:
                    driver_catalog = {}
                confirmed = []
                for fn in detected:
                    desc = driver_catalog.get(fn, fn)
                    checked = st.checkbox(
                        f"{fn}  —  {desc}",
                        value=True,
                        key=f"tab1_chk_{fn}",
                    )
                    if checked:
                        confirmed.append(fn)
                st.session_state["tab1_confirmed_drivers"] = confirmed
                if confirmed:
                    with st.expander("Preview selected driver sources", expanded=False):
                        for fn in confirmed:
                            try:
                                src = read_driver_source(fn)
                                st.markdown(f"**{fn}**")
                                st.code(
                                    src[:2000] + ("\n..." if len(src) > 2000 else ""),
                                    language="python",
                                )
                            except Exception:
                                pass
            else:
                st.info(
                    "No matching drivers detected. Check that PyLabDrivers is installed "
                    "and that the instrument names in your prompt are recognizable."
                )

        # ─── Flow Diagram (Automation Script only) ───────────────────
        st.markdown("---")
        st.markdown("#### Automation Flow Diagram")
        st.markdown(
            "Generate an interactive diagram showing the step-by-step automation logic "
            "from your prompt — instrument sequence, decisions, and data capture points."
        )
        col_flow_btn, _ = st.columns([2, 5])
        with col_flow_btn:
            tab1_flow_clicked = st.button(
                "Generate Flow Diagram", key="tab1_gen_flow",
                help="Visualize the automation logic from your prompt using Vis.js",
            )
        if tab1_flow_clicked:
            config_flow = _get_config()
            err = validate_config(config_flow)
            if err:
                st.error(err)
            elif not prompt_text.strip():
                st.warning("Please enter a prompt before generating the diagram.")
            else:
                confirmed_drivers = st.session_state.get("tab1_confirmed_drivers", [])
                fmap_for_flow = prompt_text  # use the full prompt as workflow description
                with st.spinner("Generating automation flow diagram..."):
                    try:
                        flow_json = generate_flow_diagram(
                            config_flow,
                            fmap_for_flow,
                            confirmed_drivers or ["automation script"],
                            "",
                        )
                        st.session_state["tab1_flow"] = flow_json
                    except Exception as _fe:
                        st.error(f"Flow diagram generation failed: {_fe}")

        if "tab1_flow" in st.session_state:
            tab1_vis_json = st.session_state["tab1_flow"]
            tab1_vis_html = f"""<!DOCTYPE html>
<html>
<head>
<script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
<style>
  body {{ margin: 0; background: #F7F7F7; font-family: Helvetica Neue, Arial, sans-serif; }}
  #diagram {{ width: 100%; height: 520px; border: 1px solid #D9D9D9; border-radius: 6px; background: #FFFFFF; }}
  .legend {{ display: flex; flex-wrap: wrap; gap: 10px; padding: 8px 16px 12px; font-size: 12px; color: #1E293B; }}
  .legend-item {{ display: flex; align-items: center; gap: 5px; }}
  .legend-box {{ width: 14px; height: 14px; border-radius: 3px; border: 1px solid #1E293B; }}
</style>
</head>
<body>
<div id="diagram"></div>
<div class="legend">
  <strong style="margin-right:6px">Legend:</strong>
  <div class="legend-item"><div class="legend-box" style="background:#60A5FA"></div> User action</div>
  <div class="legend-item"><div class="legend-box" style="background:#1E293B"></div> Instrument</div>
  <div class="legend-item"><div class="legend-box" style="background:#F7F7F7;border:1px solid #1E293B"></div> Outcome</div>
  <div class="legend-item"><div class="legend-box" style="background:#2563EB"></div> Decision</div>
  <div class="legend-item"><div class="legend-box" style="background:#5450E4"></div> Data saved</div>
</div>
<script>
var raw = {tab1_vis_json};
var nodeStyles = {{
  user:       {{shape:"box",         color:{{background:"#60A5FA",border:"#2563EB",highlight:{{background:"#60A5FA",border:"#2563EB"}}}}, font:{{color:"#1E293B",size:13}}, borderWidth:2}},
  instrument: {{shape:"box",         color:{{background:"#1E293B",border:"#2563EB",highlight:{{background:"#334155",border:"#60A5FA"}}}}, font:{{color:"#FFFFFF",size:13,bold:true}}, borderWidth:2}},
  decision:   {{shape:"diamond",     color:{{background:"#2563EB",border:"#1E293B",highlight:{{background:"#2563EB",border:"#60A5FA"}}}}, font:{{color:"#FFFFFF",size:12}}, borderWidth:2}},
  outcome:    {{shape:"box",         color:{{background:"#FFFFFF",border:"#1E293B",highlight:{{background:"#F7F7F7",border:"#2563EB"}}}}, font:{{color:"#1E293B",size:12}}, borderWidth:1}},
  data:       {{shape:"cylinder",    color:{{background:"#5450E4",border:"#1E293B",highlight:{{background:"#5450E4",border:"#60A5FA"}}}}, font:{{color:"#FFFFFF",size:12}}, borderWidth:2}},
}};
var styledNodes = raw.nodes.map(function(n) {{
  return Object.assign({{}}, nodeStyles[n.group] || nodeStyles.outcome, n);
}});
var container = document.getElementById("diagram");
var data = {{ nodes: new vis.DataSet(styledNodes), edges: new vis.DataSet(raw.edges) }};
var options = {{
  layout: {{ hierarchical: {{ direction: "UD", sortMethod: "directed", levelSeparation: 90, nodeSpacing: 160 }} }},
  edges: {{ arrows: {{ to: {{ enabled: true, scaleFactor: 0.8 }} }}, color: {{ color: "#1E293B" }}, font: {{ size: 11, color: "#1E293B" }}, smooth: {{ type: "cubicBezier" }} }},
  physics: {{ enabled: false }},
  interaction: {{ tooltipDelay: 200, navigationButtons: true, keyboard: true }},
}};
new vis.Network(container, data, options);
</script>
</body>
</html>"""
            st.components.v1.html(tab1_vis_html, height=600, scrolling=True)
            with st.expander("View / edit diagram JSON", expanded=False):
                st.text_area(
                    "Vis.js JSON source",
                    st.session_state["tab1_flow"],
                    height=220,
                    key="tab1_flow_edit",
                    label_visibility="collapsed",
                )

    # ─── Additional uploads ─────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### Additional Resources (optional)")
    col_up1, col_up2 = st.columns(2)
    with col_up1:
        extra_drivers = st.file_uploader(
            "Upload additional Python drivers/helper files",
            type="py",
            accept_multiple_files=True,
            key="tab1_extra_drivers",
        )
    with col_up2:
        extra_pdfs = st.file_uploader(
            "Upload additional PDF documentation",
            type="pdf",
            accept_multiple_files=True,
            key="tab1_extra_pdfs",
        )

    # ─── URL fetch ──────────────────────────────────────────────────
    st.markdown("**Fetch content from a URL (documentation, API reference, etc.):**")
    col_url1, col_url2 = st.columns([5, 1])
    with col_url1:
        tab1_url = st.text_input(
            "URL",
            placeholder="e.g. https://pylablib.readthedocs.io/en/latest/",
            key="tab1_url_input",
            label_visibility="collapsed",
        )
    with col_url2:
        tab1_fetch_clicked = st.button("Fetch", key="tab1_url_fetch")
    if tab1_fetch_clicked:
        if not tab1_url.strip():
            st.warning("Please enter a URL.")
        else:
            with st.spinner(f"Fetching {tab1_url}..."):
                fetched = _fetch_url_text(tab1_url.strip())
            if fetched.startswith("[ERROR"):
                st.error(fetched)
            else:
                st.session_state["tab1_url_content"] = fetched
                st.session_state["tab1_url_label"] = tab1_url.strip()
                st.success(f"Fetched {len(fetched):,} characters.")
    if st.session_state.get("tab1_url_content"):
        tab1_use_url = st.checkbox(
            f"Include fetched content in prompt — {st.session_state.get('tab1_url_label', 'URL')}",
            value=True,
            key="tab1_url_use",
        )
        with st.expander("Preview fetched content", expanded=False):
            st.text(st.session_state["tab1_url_content"][:2000] + "...")

    # ─── Generate Button ────────────────────────────────────────────
    st.markdown("---")

    # Hallucination guard — New Driver mode with no documentation
    # Show warning + confirmation checkbox persistently; block only when Generate is clicked.
    _show_no_doc_warning = False
    if mode == "New Driver from PDF Manual":
        _has_manual = bool(
            st.session_state.get("pdf_text_edit") or st.session_state.get("pdf_text")
        )
        _has_url = bool(
            st.session_state.get("tab1_url_use") and st.session_state.get("tab1_url_content")
        )
        _has_extra_pdfs = bool(extra_pdfs)
        if not (_has_manual or _has_url or _has_extra_pdfs):
            _show_no_doc_warning = True
            st.warning(
                "**No instrument manual or documentation detected.** "
                "Generating a driver without a communication manual will likely produce "
                "hallucinated (incorrect) commands. Upload a PDF manual or provide a URL "
                "before generating, or check the box below to proceed anyway."
            )
            st.checkbox(
                "I understand — generate without documentation", key="tab1_no_doc_confirm"
            )

    if st.button("Generate Code", type="primary", key="tab1_generate"):
        # Block generation if no-doc warning is active and user hasn't confirmed
        if _show_no_doc_warning and not st.session_state.get("tab1_no_doc_confirm"):
            st.error("Please check the confirmation box above before generating without documentation.")
            st.stop()

        config = _get_config()
        err = validate_config(config)
        if err:
            st.error(err)
            st.stop()

        # Assemble context for the LLM
        context_parts = []

        # PDF manual text
        pdf_content = st.session_state.get("pdf_text_edit") or st.session_state.get("pdf_text", "")
        if pdf_content:
            context_parts.append(f"## Instrument Communication Manual\n\n{pdf_content}")

        # Reference driver source (for new driver generation)
        if mode == "New Driver from PDF Manual":
            ref_src = read_driver_source(ref_driver)
            context_parts.append(
                f"## Reference Driver ({ref_driver})\n\n```python\n{ref_src}\n```"
            )

        # Inject selected driver sources (for automation scripts)
        if mode == "Automation Script":
            drivers_for_script = st.session_state.get("tab1_confirmed_drivers", [])
            if drivers_for_script:
                context_parts.append(
                    "## PyLabDrivers — Available Driver Source Code\n\n"
                    "Use ONLY the classes and methods shown below. Do not invent any others.\n"
                )
                for fn in drivers_for_script:
                    try:
                        src = read_driver_source(fn)
                        context_parts.append(f"### {fn}\n```python\n{src}\n```")
                    except Exception:
                        pass
            else:
                # No PyLabDrivers driver was confirmed — check whether extra documentation covers it
                _has_extra_doc = bool(
                    extra_drivers
                    or extra_pdfs
                    or (st.session_state.get("tab1_url_use") and st.session_state.get("tab1_url_content"))
                )
                if not _has_extra_doc:
                    st.warning(
                        "**No driver source or documentation found for the instruments in your prompt.** "
                        "Click **Detect Instruments** to find matching PyLabDrivers drivers, or upload a "
                        "Python driver / PDF manual / URL for any instrument not covered by PyLabDrivers. "
                        "Generating without documentation will likely produce hallucinated instrument commands."
                    )
                    st.stop()

        # Extra uploaded drivers
        extra_sources = {}
        if extra_drivers:
            for f in extra_drivers:
                content = f.read().decode("utf-8")
                extra_sources[f.name] = content
                context_parts.append(
                    f"## Additional Driver: {f.name}\n\n```python\n{content}\n```"
                )

        # Extra PDFs
        if extra_pdfs:
            for f in extra_pdfs:
                pdf_text = extract_pdf_text(f.read())
                context_parts.append(
                    f"## Additional Documentation: {f.name}\n\n{pdf_text}"
                )

        # Fetched URL content
        if st.session_state.get("tab1_url_use") and st.session_state.get("tab1_url_content"):
            url_label = st.session_state.get("tab1_url_label", "Web Reference")
            context_parts.append(
                f"## Web Reference: {url_label}\n\n{st.session_state['tab1_url_content']}"
            )

        # System prompt from structured template (enforces anti-hallucination rules)
        system_prompt = get_system_prompt(mode)

        # Inject a VERIFIED IMPORTS block so the LLM always uses the exact class names
        # from whatever Python sources are in the context (PyLabDrivers + uploaded drivers)
        _pylabdriver_files = st.session_state.get("tab1_confirmed_drivers", []) if mode == "Automation Script" else []
        _custom_srcs = extra_sources if extra_sources else None
        _verified_imports = build_verified_imports_block(
            pylabdriver_files=_pylabdriver_files,
            custom_sources=_custom_srcs,
        )

        full_prompt = prompt_text
        if context_parts:
            full_prompt = "\n\n".join(context_parts) + _verified_imports + "\n\n---\n\n" + prompt_text
        elif _verified_imports:
            full_prompt = _verified_imports + "\n\n---\n\n" + prompt_text

        # Generate with streaming
        st.markdown("---")
        st.markdown("#### Generation Progress")
        response_container = st.empty()
        full_response = ""

        with st.spinner("Generating code..."):
            for chunk in stream(config, full_prompt, system_prompt):
                full_response += chunk
                response_container.markdown(f"```\n{full_response[-500:]}\n```")

        st.session_state["tab1_generated"] = full_response

        # Extract code block
        import re
        code_match = re.search(r"```python(.*?)```", full_response, re.S | re.I)
        if code_match:
            generated_code = code_match.group(1).strip()
            st.session_state["tab1_code"] = generated_code
        else:
            st.session_state["tab1_code"] = full_response
            st.warning("Could not find a fenced Python code block — showing raw response.")

    # ─── Display Generated Code ─────────────────────────────────────
    if "tab1_code" in st.session_state:
        st.markdown("---")
        st.markdown("### Generated Code")

        code = st.session_state["tab1_code"]

        # Run verification
        verify_mode = "driver" if mode == "New Driver from PDF Manual" else "script"
        result = run_full_verification(code, verify_mode)

        if result.passed:
            st.success("Verification passed — code structure looks correct")
        else:
            st.error("Verification found issues:")
            for issue in result.issues:
                st.markdown(f"- {issue}")

        if result.warnings:
            with st.expander("Warnings", expanded=False):
                for w in result.warnings:
                    st.markdown(f"- {w}")

        if result.suggestions:
            with st.expander("Suggestions", expanded=False):
                for s in result.suggestions:
                    st.markdown(f"- {s}")

        st.code(code, language="python")

        # Download and AI verification buttons
        col_dl, col_verify = st.columns([1, 1])
        with col_dl:
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            st.download_button(
                "Download Code (.py)",
                code,
                file_name=f"generated_driver_{ts}.py",
                mime="text/x-python",
            )
        with col_verify:
            if st.button("AI Code Review", key="tab1_ai_verify"):
                config = _get_config()
                with st.spinner("AI is reviewing the code..."):
                    review = verify_driver_with_ai(config, code)
                st.session_state["tab1_review"] = review

            if st.button("Generate Test Code", key="tab1_gen_tests"):
                config = _get_config()
                with st.spinner("Generating test code..."):
                    test_code = generate_test_code(config, code)
                st.session_state["tab1_tests"] = test_code

        # Show AI review results
        if "tab1_review" in st.session_state:
            review = st.session_state["tab1_review"]
            with st.expander(f"AI Review (Score: {review.get('score', '?')}/10)", expanded=True):
                st.markdown(f"**Summary:** {review.get('summary', 'N/A')}")
                if review.get("issues"):
                    st.markdown("**Issues:**")
                    for i in review["issues"]:
                        st.markdown(f"- {i}")
                if review.get("warnings"):
                    st.markdown("**Warnings:**")
                    for w in review["warnings"]:
                        st.markdown(f"- {w}")

        # Show generated tests
        if "tab1_tests" in st.session_state:
            with st.expander("Generated Test Code", expanded=False):
                st.code(st.session_state["tab1_tests"], language="python")
                st.download_button(
                    "Download Tests (.py)",
                    st.session_state["tab1_tests"],
                    file_name=f"test_generated_driver_{ts}.py",
                    mime="text/x-python",
                    key="tab1_test_dl",
                )

        # ─── Iterative Fix Loop ────────────────────────────────────
        st.markdown("---")
        st.markdown("### Iterative Refinement")
        st.markdown("If the code has issues, paste the error below and the AI will fix it.")

        fix_input = st.text_area(
            "Paste error message or describe the issue",
            height=150,
            key="tab1_fix_input",
        )

        if st.button("Fix Code", key="tab1_fix_btn"):
            if not fix_input.strip():
                st.warning("Please describe the issue or paste an error.")
            else:
                config = _get_config()
                fix_prompt = (
                    f"## Current Code\n```python\n{st.session_state['tab1_code']}\n```\n\n"
                    f"## Issue\n{fix_input}\n\n"
                    "Fix the code and output the complete corrected version in a single ```python block."
                )
                system_fix = (
                    "You are an expert Python developer. Fix the code based on the error report. "
                    "Output the COMPLETE fixed code in a single ```python block."
                )
                with st.spinner("Fixing code..."):
                    response = complete(config, fix_prompt, system_fix)

                import re
                match = re.search(r"```python(.*?)```", response, re.S | re.I)
                if match:
                    st.session_state["tab1_code"] = match.group(1).strip()
                    st.success("Code updated! Review above.")
                    st.rerun()
                else:
                    st.error("Could not extract fixed code from response.")
                    st.text(response)


# ═══════════════════════════════════════════════════════════════════════
with tab2:
    col_title2, col_clear2 = st.columns([6, 1])
    with col_title2:
        st.markdown("### Generate Dash/Plotly Web Applications for Instrument Control")
    with col_clear2:
        if st.button("Clear", key="tab2_clear", help="Clear all results and start fresh"):
            _clear_tab(TAB2_KEYS)

    st.markdown(
        "Create web interfaces for real-time laboratory instrument monitoring and control. "
        "Follow the four-step workflow below."
    )

    # ─── Four-step sub-tabs ─────────────────────────────────────────
    t2_spec, t2_review, t2_code, t2_export = st.tabs([
        "1. Specification",
        "2. Review & Design",
        "3. Generate & Fix",
        "4. Export",
    ])

    # ═══════════════════════════════════════════════════
    # Sub-tab 1: Specification
    # ═══════════════════════════════════════════════════
    with t2_spec:
        st.markdown("#### Structured Prompt")
        st.markdown(
            "*Follow the 5-section template: "
            "**1)** Project Overview, **2)** UI Design, **3)** Functionality & Logic, "
            "**4)** Technical Implementation, **5)** Documentation & References.*"
        )
        st.info(
            "A structured prompt with specific button labels, method names, formulas, "
            "and operational sequences constrains the AI — leaving no room for hallucination."
        )

        prompt_options = ["Custom prompt"] + list(predefined_prompts.keys())
        prompt_choice = st.selectbox(
            "Load an example prompt (or write your own below)",
            prompt_options,
            key="tab2_prompt_choice",
        )

        # When a showcase is selected, push its text into the textarea's session key
        if prompt_choice != "Custom prompt":
            st.session_state["tab2_prompt"] = predefined_prompts[prompt_choice]
        elif "tab2_prompt" not in st.session_state:
            st.session_state["tab2_prompt"] = get_template("Dash App")

        dash_prompt = st.text_area(
            "Enter your structured prompt",
            height=420,
            key="tab2_prompt",
        )

        missing_sections = validate_prompt_structure(dash_prompt)
        if missing_sections:
            st.warning(
                f"Missing sections: {', '.join(missing_sections)}. "
                "All 5 sections are recommended for best results."
            )

        st.markdown("---")
        st.markdown("#### Reference Code & Additional Resources")

        vapourtec_examples = _load_reference_files("reference_examples/vapourtec", "Vapourtec")
        _vendor_notes = []
        if not vapourtec_examples:
            _vendor_notes.append(
                "- **Vapourtec R-Series examples** give more accurate code for Vapourtec systems. "
                "Obtain them from [Vapourtec Ltd](https://www.vapourtec.com), copy the `.py` files into "
                "`reference_examples/vapourtec/`, and restart LabAutoMate."
            )
        if importlib.util.find_spec("softcheck") is None:
            _vendor_notes.append(
                "- **Huber pySoftcheck** is needed only to run generated apps that control a Huber chiller. "
                f"Download the [pySoftcheck wheel]({PYSOFTCHECK_URL}) from Huber and place it next to `launch.bat`."
            )
        if _vendor_notes:
            st.info(
                "**Optional vendor files not found.** LabAutoMate works without them, but:\n"
                + "\n".join(_vendor_notes)
            )

        col_ref1, col_ref2 = st.columns(2)
        with col_ref1:
            use_vapourtec = st.checkbox(
                f"Include Vapourtec SDK examples ({len(vapourtec_examples)} files)",
                value=False, key="tab2_vapourtec",
                disabled=not vapourtec_examples,
            )
            dash_examples = _load_reference_files("reference_examples/dash", "Dash")
            use_dash_examples = st.checkbox(
                f"Include Dash reference apps ({len(dash_examples)} files)",
                value=False, key="tab2_dash_ex",
            )
            ocean_files = _load_reference_files("reference_examples/oceanoptics", "Ocean Optics")
            use_ocean = st.checkbox(
                f"Include Ocean Optics driver & examples ({len(ocean_files)} files)",
                value=False, key="tab2_ocean",
            )
            if use_ocean:
                st.info(
                    "**Ocean Optics requires the OceanDirect SDK** (purchased separately from Ocean Optics). "
                    "To run the generated app:\n"
                    "1. Place `oceanoptics.py` next to `dash_app.py`\n"
                    "2. Place the `oceandirect` SDK folder next to `dash_app.py`\n\n"
                    "The SDK is **not pip-installable** — obtain it from Ocean Optics with your instrument. "
                    "The launch.bat will remind you of this automatically."
                )
        with col_ref2:
            st.markdown("**Upload additional resources:**")
            custom_drivers = st.file_uploader(
                "Python drivers/examples", type="py",
                accept_multiple_files=True, key="tab2_custom_py",
            )
            custom_pdfs = st.file_uploader(
                "PDF documentation", type="pdf",
                accept_multiple_files=True, key="tab2_custom_pdf",
            )

        st.markdown("**Fetch content from a URL (documentation, API reference, etc.):**")
        col_url2a, col_url2b = st.columns([5, 1])
        with col_url2a:
            tab2_url = st.text_input(
                "URL",
                placeholder="e.g. https://pylablib.readthedocs.io/en/latest/",
                key="tab2_url_input",
                label_visibility="collapsed",
            )
        with col_url2b:
            tab2_fetch_clicked = st.button("Fetch", key="tab2_url_fetch")
        if tab2_fetch_clicked:
            if not tab2_url.strip():
                st.warning("Please enter a URL.")
            else:
                with st.spinner(f"Fetching {tab2_url}..."):
                    fetched2 = _fetch_url_text(tab2_url.strip())
                if fetched2.startswith("[ERROR"):
                    st.error(fetched2)
                else:
                    st.session_state["tab2_url_content"] = fetched2
                    st.session_state["tab2_url_label"] = tab2_url.strip()
                    st.success(f"Fetched {len(fetched2):,} characters.")
        if st.session_state.get("tab2_url_content"):
            tab2_use_url = st.checkbox(
                f"Include fetched content in prompt — {st.session_state.get('tab2_url_label', 'URL')}",
                value=True,
                key="tab2_url_use",
            )
            with st.expander("Preview fetched content", expanded=False):
                st.text(st.session_state["tab2_url_content"][:2000] + "...")

        st.markdown("---")
        if st.button("Discover Required Drivers", type="primary", key="tab2_discover"):
            config = _get_config()
            err = validate_config(config)
            if err:
                st.error(err)
                st.stop()

            extra_names = [f.name for f in custom_drivers] if custom_drivers else []

            # Append URL content and uploaded PDF text to the discovery prompt
            discovery_prompt = dash_prompt
            if st.session_state.get("tab2_url_use") and st.session_state.get("tab2_url_content"):
                url_label = st.session_state.get("tab2_url_label", "Web Reference")
                discovery_prompt = (
                    dash_prompt
                    + f"\n\n## Web Reference: {url_label}\n\n"
                    + st.session_state["tab2_url_content"]
                )
            discovery_prompt += _pdf_context(custom_pdfs)

            with st.spinner("AI is analyzing your prompt and selecting drivers..."):
                fmap_yaml, drivers, app_design = generate_function_map(
                    config, discovery_prompt, extra_driver_names=extra_names or None,
                )

            st.session_state["tab2_fmap"] = fmap_yaml
            st.session_state["tab2_drivers"] = drivers
            st.session_state["tab2_design"] = app_design
            st.session_state["tab2_custom_src"] = (
                {f.name: f.read().decode("utf-8") for f in custom_drivers}
                if custom_drivers else {}
            )

            # Hallucination guard — warn if any instruments may lack documentation
            _tab2_has_supplemental = bool(
                custom_drivers
                or custom_pdfs
                or st.session_state.get("tab2_vapourtec")
                or st.session_state.get("tab2_ocean")
                or st.session_state.get("tab2_dash_ex")
                or (st.session_state.get("tab2_url_use") and st.session_state.get("tab2_url_content"))
            )
            if not drivers and not _tab2_has_supplemental:
                st.warning(
                    "**No matching drivers found for the instruments in your prompt.** "
                    "The AI does not have documentation for these instruments and may hallucinate "
                    "incorrect commands or driver interfaces. "
                    "Upload a custom Python driver or PDF manual, check reference examples, "
                    "or fetch a URL with the instrument's API documentation before generating."
                )
            elif drivers:
                st.success(
                    f"Discovery complete — {len(drivers)} driver(s) identified. "
                    "Switch to the **Review & Design** tab to inspect and edit."
                )
            else:
                st.success(
                    "Discovery complete. Switch to the **Review & Design** tab to inspect and edit."
                )

    # ═══════════════════════════════════════════════════
    # Sub-tab 2: Review & Design
    # ═══════════════════════════════════════════════════
    with t2_review:
        if "tab2_fmap" not in st.session_state:
            st.info("Run **Discover Required Drivers** in the Specification tab first.")
        else:
            st.markdown("#### Review & Refine Your App Design")
            st.markdown(
                "The AI has produced an **Automation Workflow** and a **Dashboard Layout Plan** "
                "for your app. Review the visualizations below, then use the refinement box "
                "at the bottom to request any changes in plain English."
            )

            # ── Drivers used ─────────────────────────────────────────
            st.markdown("**PyLabDrivers selected:**")
            n = min(len(st.session_state["tab2_drivers"]), 4)
            col_drv = st.columns(n if n > 0 else 1)
            for i, d in enumerate(st.session_state["tab2_drivers"]):
                desc = pump_file_catalog.get(d, "uploaded driver")
                col_drv[i % len(col_drv)].markdown(f"`{d}`  \n{desc}")

            st.markdown("---")

            # ── Editable documents ────────────────────────────────────
            col_map, col_design = st.columns(2)
            with col_map:
                st.markdown(
                    "**Automation Workflow**  \n"
                    "<small>Step-by-step logic connecting each button action to an instrument command</small>",
                    unsafe_allow_html=True,
                )
                fmap_edit = st.text_area(
                    "Automation Workflow",
                    st.session_state["tab2_fmap"],
                    height=280,
                    key="tab2_fmap_edit",
                    label_visibility="collapsed",
                )

            with col_design:
                st.markdown(
                    "**Dashboard Layout Plan**  \n"
                    "<small>Visual and structural specification for the user interface</small>",
                    unsafe_allow_html=True,
                )
                design_edit = st.text_area(
                    "Dashboard Layout Plan",
                    st.session_state["tab2_design"],
                    height=280,
                    key="tab2_design_edit",
                    label_visibility="collapsed",
                )

            # ── Driver source preview ─────────────────────────────────
            with st.expander("View PyLabDrivers source code included", expanded=False):
                for fn in st.session_state["tab2_drivers"]:
                    if fn in st.session_state.get("tab2_custom_src", {}):
                        src = st.session_state["tab2_custom_src"][fn]
                    else:
                        try:
                            src = read_driver_source(fn)
                        except FileNotFoundError:
                            src = "# source not available"
                    st.markdown(f"**{fn}**")
                    st.code(src[:3000] + ("\n..." if len(src) > 3000 else ""), language="python")

            # ── Visualizations ────────────────────────────────────────
            st.markdown("---")
            st.markdown("#### Visualizations")

            col_viz1, col_viz2 = st.columns(2)
            with col_viz1:
                if st.button("Generate Flow Diagram", key="tab2_gen_dot"):
                    config = _get_config()
                    with st.spinner("Generating architecture diagram..."):
                        dot_src = generate_flow_diagram(
                            config,
                            st.session_state.get("tab2_fmap_edit") or st.session_state["tab2_fmap"],
                            st.session_state["tab2_drivers"],
                            st.session_state.get("tab2_design_edit") or st.session_state["tab2_design"],
                        )
                    st.session_state["tab2_dot"] = dot_src
                    st.session_state.pop("tab2_dot_edit", None)

            with col_viz2:
                if st.button("Generate UI Mockup", key="tab2_gen_mockup"):
                    config = _get_config()
                    with st.spinner("Generating UI mockup..."):
                        html_mockup = generate_ui_mockup(
                            config,
                            st.session_state.get("tab2_design_edit") or st.session_state["tab2_design"],
                            st.session_state.get("tab2_fmap_edit") or st.session_state["tab2_fmap"],
                        )
                    st.session_state["tab2_mockup"] = html_mockup

            if "tab2_dot" in st.session_state:
                st.markdown("**Automation Flow Diagram** — plain-English overview of the experiment logic")

                # Render with Vis.js Network (single-bundle CDN, hierarchical layout)
                vis_json = st.session_state.get("tab2_dot_edit") or st.session_state["tab2_dot"]
                vis_html = f"""<!DOCTYPE html>
<html>
<head>
<script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
<style>
  body {{ margin: 0; background: #F7F7F7; font-family: Helvetica Neue, Arial, sans-serif; }}
  #diagram {{ width: 100%; height: 560px; border: 1px solid #D9D9D9; border-radius: 6px; background: #FFFFFF; }}
  .legend {{ display: flex; flex-wrap: wrap; gap: 10px; padding: 8px 16px 12px; font-size: 12px; color: #1E293B; }}
  .legend-item {{ display: flex; align-items: center; gap: 5px; }}
  .legend-box {{ width: 14px; height: 14px; border-radius: 3px; border: 1px solid #1E293B; }}
</style>
</head>
<body>
<div id="diagram"></div>
<div class="legend">
  <strong style="margin-right:6px">Legend:</strong>
  <div class="legend-item"><div class="legend-box" style="background:#60A5FA"></div> User action</div>
  <div class="legend-item"><div class="legend-box" style="background:#1E293B"></div> Instrument</div>
  <div class="legend-item"><div class="legend-box" style="background:#F7F7F7;border:1px solid #1E293B"></div> Outcome</div>
  <div class="legend-item"><div class="legend-box" style="background:#2563EB"></div> Decision</div>
  <div class="legend-item"><div class="legend-box" style="background:#5450E4"></div> Data saved</div>
</div>
<script>
var raw = {vis_json};
var nodeStyles = {{
  user:       {{shape:"box",         color:{{background:"#60A5FA",border:"#2563EB",highlight:{{background:"#60A5FA",border:"#2563EB"}}}}, font:{{color:"#1E293B",size:13}}, borderWidth:2}},
  instrument: {{shape:"box",         color:{{background:"#1E293B",border:"#2563EB",highlight:{{background:"#334155",border:"#60A5FA"}}}}, font:{{color:"#FFFFFF",size:13,bold:true}}, borderWidth:2}},
  decision:   {{shape:"diamond",     color:{{background:"#2563EB",border:"#1E293B",highlight:{{background:"#2563EB",border:"#60A5FA"}}}}, font:{{color:"#FFFFFF",size:12}}, borderWidth:2}},
  outcome:    {{shape:"box",         color:{{background:"#FFFFFF",border:"#1E293B",highlight:{{background:"#F7F7F7",border:"#2563EB"}}}}, font:{{color:"#1E293B",size:12}}, borderWidth:1}},
  data:       {{shape:"cylinder",    color:{{background:"#5450E4",border:"#1E293B",highlight:{{background:"#5450E4",border:"#60A5FA"}}}}, font:{{color:"#FFFFFF",size:12}}, borderWidth:2}},
}};
var styledNodes = raw.nodes.map(function(n) {{
  return Object.assign({{}}, nodeStyles[n.group] || nodeStyles.outcome, n);
}});
var container = document.getElementById("diagram");
var data = {{ nodes: new vis.DataSet(styledNodes), edges: new vis.DataSet(raw.edges) }};
var options = {{
  layout: {{ hierarchical: {{ direction: "UD", sortMethod: "directed", levelSeparation: 90, nodeSpacing: 160 }} }},
  edges: {{ arrows: {{ to: {{ enabled: true, scaleFactor: 0.8 }} }}, color: {{ color: "#1E293B" }}, font: {{ size: 11, color: "#1E293B" }}, smooth: {{ type: "cubicBezier" }} }},
  physics: {{ enabled: false }},
  interaction: {{ tooltipDelay: 200, navigationButtons: true, keyboard: true }},
}};
new vis.Network(container, data, options);
</script>
</body>
</html>"""
                st.components.v1.html(vis_html, height=640, scrolling=True)

                with st.expander("View / edit diagram JSON", expanded=False):
                    edited_dot = st.text_area(
                        "Vis.js JSON source",
                        st.session_state["tab2_dot"],
                        height=250,
                        key="tab2_dot_edit",
                        label_visibility="collapsed",
                    )

            if "tab2_mockup" in st.session_state:
                st.markdown("**UI Layout Mockup** — visual preview of buttons, inputs, and panels")
                st.components.v1.html(
                    st.session_state["tab2_mockup"],
                    height=700,
                    scrolling=True,
                )
                with st.expander("View HTML source", expanded=False):
                    st.code(st.session_state["tab2_mockup"], language="html")

            # ── Refinement chat box ───────────────────────────────────
            st.markdown("---")
            st.markdown("#### Refine with AI")
            st.markdown(
                "Not satisfied with the Automation Workflow or Dashboard Layout Plan? "
                "Describe your changes in plain English below — the AI will update both "
                "documents and you can regenerate the visualizations to verify."
            )

            refine_input = st.text_area(
                "Describe what you want to change",
                placeholder=(
                    "e.g. 'Add a Stop button to the ISCO section' or "
                    "'Remove the Harvard pump entirely' or "
                    "'Add a real-time pressure plot below the Equilibar card'"
                ),
                height=120,
                key="tab2_refine_input",
            )

            col_ref_btn, col_ref_hint = st.columns([2, 5])
            with col_ref_btn:
                refine_clicked = st.button(
                    "Apply Refinement", type="primary", key="tab2_refine_btn"
                )
            with col_ref_hint:
                st.markdown(
                    "<small style='color:#60A5FA'>After applying, regenerate the Flow Diagram "
                    "and UI Mockup above to see the updated design.</small>",
                    unsafe_allow_html=True,
                )

            if refine_clicked:
                if not refine_input.strip():
                    st.warning("Please describe what you want to change.")
                else:
                    config = _get_config()
                    current_workflow = st.session_state.get("tab2_fmap_edit") or st.session_state["tab2_fmap"]
                    current_layout = st.session_state.get("tab2_design_edit") or st.session_state["tab2_design"]
                    with st.spinner("AI is refining your design..."):
                        try:
                            new_workflow, new_layout = refine_design_plan(
                                config,
                                current_workflow,
                                current_layout,
                                refine_input,
                                st.session_state["tab2_drivers"],
                            )
                            # Push updated text into session state so the text areas refresh
                            st.session_state["tab2_fmap"] = new_workflow
                            st.session_state["tab2_design"] = new_layout
                            # Clear edits and old visualizations so next render is fresh
                            st.session_state.pop("tab2_fmap_edit", None)
                            st.session_state.pop("tab2_design_edit", None)
                            st.session_state.pop("tab2_dot", None)
                            st.session_state.pop("tab2_dot_edit", None)
                            st.session_state.pop("tab2_mockup", None)
                            st.success(
                                "Design updated. Regenerate the Flow Diagram and UI Mockup "
                                "above to see the changes."
                            )
                            st.rerun()
                        except Exception as _e:
                            st.error(f"Refinement failed: {_e}")

            st.markdown("---")
            st.info(
                "When you are satisfied with the Automation Workflow, Dashboard Layout Plan, "
                "and visualizations, switch to **Generate & Fix** to produce the final code."
            )

    # ═══════════════════════════════════════════════════
    # Sub-tab 3: Generate & Fix
    # ═══════════════════════════════════════════════════
    with t2_code:
        if "tab2_fmap" not in st.session_state:
            st.info("Complete the Specification and Review steps first.")
        else:
            # Read current edits (may have been changed in review tab)
            fmap_edit = st.session_state.get("tab2_fmap_edit") or st.session_state["tab2_fmap"]
            design_edit = st.session_state.get("tab2_design_edit") or st.session_state["tab2_design"]
            dash_prompt = st.session_state.get("tab2_prompt", "")

            if st.button("Generate Dash Application", type="primary", key="tab2_generate"):
                config = _get_config()

                templates = []
                if st.session_state.get("tab2_vapourtec"):
                    templates.extend(_load_reference_files("reference_examples/vapourtec", "Vapourtec"))
                if st.session_state.get("tab2_dash_ex"):
                    templates.extend(_load_reference_files("reference_examples/dash", "Dash"))
                if st.session_state.get("tab2_ocean"):
                    templates.extend(_load_reference_files("reference_examples/oceanoptics", "Ocean Optics"))

                # Append fetched URL content to the generation prompt if checked
                extra_context = ""
                if st.session_state.get("tab2_url_use") and st.session_state.get("tab2_url_content"):
                    url_label = st.session_state.get("tab2_url_label", "Web Reference")
                    extra_context = (
                        f"\n\n## Web Reference: {url_label}\n\n"
                        + st.session_state["tab2_url_content"]
                    )
                extra_context += _pdf_context(st.session_state.get("tab2_custom_pdf"))
                enhanced_prompt = build_enhanced_prompt(dash_prompt + extra_context, "Dash App")
                combined_design = design_edit

                final_prompt = build_final_prompt(
                    enhanced_prompt,
                    fmap_edit,
                    st.session_state["tab2_drivers"],
                    template_codes=templates or None,
                    design_notes=combined_design,
                    custom_driver_sources=st.session_state.get("tab2_custom_src"),
                )
                st.session_state["tab2_final_prompt"] = final_prompt

                dash_system_prompt = get_system_prompt("Dash App")

                with st.spinner("Generating Dash application code..."):
                    dash_code = generate_dash_code(config, final_prompt, dash_system_prompt)

                st.session_state["tab2_code"] = dash_code

                with st.spinner("Generating README..."):
                    readme = generate_readme(config, dash_code, dash_prompt)
                st.session_state["tab2_readme"] = readme
                st.success("Dash application generated! See results below.")

            if "tab2_code" in st.session_state:
                code = st.session_state["tab2_code"]

                result = run_full_verification(code, "dash")
                if result.passed:
                    st.success("Verification passed — Dash app structure looks correct")
                else:
                    st.error("Verification found issues:")
                    for issue in result.issues:
                        st.markdown(f"- {issue}")

                if result.warnings:
                    with st.expander("Warnings", expanded=False):
                        for w in result.warnings:
                            st.markdown(f"- {w}")

                if result.suggestions:
                    with st.expander("App Details", expanded=False):
                        for s in result.suggestions:
                            st.markdown(f"- {s}")

                st.code(code, language="python")

                # ── Iterative Fix Loop ────────────────────────────────
                st.markdown("---")
                st.markdown("### Iterative Refinement")
                st.markdown(
                    "Paste a Python error message or describe what needs to change. "
                    "The AI will fix the code and the updated version will appear above."
                )

                fix_input = st.text_area(
                    "Paste error message or describe the issue",
                    height=150,
                    key="tab2_fix_input",
                )

                col_fix1, col_fix2 = st.columns([3, 2])
                with col_fix1:
                    fix_mode = st.radio(
                        "Fix strategy",
                        ["Quick Fix", "Full Rewrite"],
                        horizontal=True,
                        key="tab2_fix_mode",
                        help=(
                            "**Quick Fix** — AI makes the smallest targeted change to resolve the "
                            "specific error. Fast (seconds), preserves the rest of the code. "
                            "Best for: single error messages, typos, a missing import, one wrong method name.\n\n"
                            "**Full Rewrite** — AI regenerates the entire application from scratch, "
                            "incorporating the fix and re-applying all design rules. Slower (30–60s), "
                            "but produces a cleaner result. Best for: structural problems, multiple "
                            "errors at once, or adding a significant new feature."
                        ),
                    )
                with col_fix2:
                    fix_btn = st.button("Apply Fix", type="primary", key="tab2_fix_btn")

                # Explanation shown below the radio
                if fix_mode == "Quick Fix":
                    st.caption(
                        "Quick Fix: surgically edits only the broken part. "
                        "Use for single errors or small changes."
                    )
                else:
                    st.caption(
                        "Full Rewrite: rebuilds the entire app with the correction applied. "
                        "Use when the code has multiple issues or needs a structural change."
                    )

                if fix_btn:
                    if not fix_input.strip():
                        st.warning("Please describe the issue or paste an error.")
                    else:
                        config = _get_config()
                        current_code = st.session_state["tab2_code"]

                        if fix_mode == "Quick Fix":
                            import json as _json, re as _re
                            patch_prompt = (
                                f"You are an expert Dash developer.\n\n"
                                f"## Current Dash app\n```python\n{current_code}\n```\n\n"
                                f"## Issue\n{fix_input}\n\n"
                                "Return the minimal text replacements as VALID JSON:\n"
                                '{"patch": [{"pattern": "regex", "replacement": "new text"}], '
                                '"why": "brief explanation"}'
                            )
                            with st.spinner("Applying quick fix..."):
                                raw = generate_patch(config, patch_prompt)
                            try:
                                patch_obj = _json.loads(raw)
                                patched = current_code
                                for p in patch_obj["patch"]:
                                    patched = _re.sub(p["pattern"], p["replacement"], patched, flags=_re.S)
                                st.session_state["tab2_code"] = patched
                                st.success("Quick fix applied!")
                                if patch_obj.get("why"):
                                    st.info(patch_obj["why"])
                                st.rerun()
                            except Exception:
                                st.warning("Quick fix failed — switching to Full Rewrite.")
                                fix_mode = "Full Rewrite"

                        if fix_mode == "Full Rewrite":
                            # Resend the full generation context (drivers, verified imports, design)
                            # and the 26-rule system prompt so the rewrite follows the same rules.
                            base_prompt = st.session_state.get("tab2_final_prompt", dash_prompt)
                            regen_prompt = (
                                f"{base_prompt}\n\n"
                                f"### Current Dash code\n```python\n{current_code}\n```\n\n"
                                f"### Issue / change\n{fix_input}\n\n"
                                "Output the entire updated Dash 2.x app in ONE ```python block."
                            )
                            with st.spinner("Rewriting full application..."):
                                new_code = generate_full_code(
                                    config, regen_prompt, get_system_prompt("Dash App")
                                )
                            st.session_state["tab2_code"] = new_code
                            st.success("Full rewrite complete!")
                            st.rerun()

    # ═══════════════════════════════════════════════════
    # Sub-tab 4: Export
    # ═══════════════════════════════════════════════════
    with t2_export:
        if "tab2_code" not in st.session_state:
            st.info("Generate the Dash application in the **Generate & Fix** tab first.")
        else:
            code = st.session_state["tab2_code"]
            readme = st.session_state.get("tab2_readme", "")
            # Rebuilt from the current code so imports added by Quick Fix / Full Rewrite are installed.
            # Bytes (CRLF ASCII); decode only for display.
            batch_bytes = _make_dash_batch("dash_app.py", app_code=code)
            batch_text = batch_bytes.decode("ascii", errors="replace") if batch_bytes else ""
            dot = st.session_state.get("tab2_dot", "")
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

            # ── Download buttons — top of page ────────────────────────
            st.markdown("#### Download")

            # Build ZIP with raw bytes for launch.bat to preserve CRLF
            import io as _io, zipfile as _zf
            zip_buf = _io.BytesIO()
            with _zf.ZipFile(zip_buf, "w", _zf.ZIP_DEFLATED) as zf:
                zf.writestr("dash_app.py", code)
                if readme:
                    zf.writestr("README.md", readme)
                if batch_bytes:
                    zf.writestr("launch.bat", batch_bytes)
                if dot:
                    zf.writestr("architecture_diagram.json", dot)
            zip_data = zip_buf.getvalue()

            st.download_button(
                "⬇ Download all files as ZIP",
                zip_data,
                file_name=f"dash_app_{ts}.zip",
                mime="application/zip",
                key="tab2_dl_zip",
            )

            col_dl1, col_dl2, col_dl3 = st.columns(3)
            with col_dl1:
                st.download_button(
                    "Download dash_app.py",
                    code,
                    file_name="dash_app.py",
                    mime="text/x-python",
                    key="tab2_dl_py",
                )
            with col_dl2:
                if readme:
                    st.download_button(
                        "Download README.md",
                        readme,
                        file_name="README.md",
                        mime="text/markdown",
                        key="tab2_dl_readme",
                    )
            with col_dl3:
                if batch_bytes:
                    st.download_button(
                        "Download launch.bat",
                        batch_bytes,
                        file_name="launch.bat",
                        mime="application/octet-stream",
                        key="tab2_dl_bat",
                    )

            # ── Architecture diagram ──────────────────────────────────
            if dot:
                st.markdown("---")
                st.markdown("#### Architecture Diagram")
                vis_json_export = dot
                vis_html_export = f"""<!DOCTYPE html>
<html><head>
<script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
<style>
  body{{margin:0;background:#F7F7F7;font-family:Helvetica Neue,Arial,sans-serif;}}
  #diagram{{width:100%;height:460px;border:1px solid #D9D9D9;border-radius:6px;background:#FFFFFF;}}
</style>
</head><body>
<div id="diagram"></div>
<script>
var raw={vis_json_export};
var nodeStyles={{
  user:      {{shape:"box",color:{{background:"#60A5FA",border:"#2563EB"}},font:{{color:"#1E293B",size:13}},borderWidth:2}},
  instrument:{{shape:"box",color:{{background:"#1E293B",border:"#2563EB"}},font:{{color:"#FFFFFF",size:13,bold:true}},borderWidth:2}},
  decision:  {{shape:"diamond",color:{{background:"#2563EB",border:"#1E293B"}},font:{{color:"#FFFFFF",size:12}},borderWidth:2}},
  outcome:   {{shape:"box",color:{{background:"#FFFFFF",border:"#1E293B"}},font:{{color:"#1E293B",size:12}},borderWidth:1}},
  data:      {{shape:"cylinder",color:{{background:"#5450E4",border:"#1E293B"}},font:{{color:"#FFFFFF",size:12}},borderWidth:2}},
}};
var styledNodes=raw.nodes.map(function(n){{return Object.assign({{}},nodeStyles[n.group]||nodeStyles.outcome,n);}});
var container=document.getElementById("diagram");
var data={{nodes:new vis.DataSet(styledNodes),edges:new vis.DataSet(raw.edges)}};
var options={{layout:{{hierarchical:{{direction:"UD",sortMethod:"directed",levelSeparation:90,nodeSpacing:160}}}},edges:{{arrows:{{to:{{enabled:true,scaleFactor:0.8}}}},color:{{color:"#1E293B"}},smooth:{{type:"cubicBezier"}}}},physics:{{enabled:false}},interaction:{{navigationButtons:true}}}};
new vis.Network(container,data,options);
</script></body></html>"""
                st.components.v1.html(vis_html_export, height=500, scrolling=True)

            # ── README ────────────────────────────────────────────────
            st.markdown("---")
            st.markdown("#### README")
            with st.expander("View README", expanded=False):
                st.markdown(readme)

            if batch_text:
                st.markdown("---")
                st.markdown("#### Launch Script (launch.bat)")
                st.markdown(
                    "Double-click to install all dependencies with **uv** and launch the Dash app. "
                    "Works on any Windows machine — installs uv automatically if not present."
                )
                st.code(batch_text, language="bat")

            # ── Generated code — at the bottom ───────────────────────
            st.markdown("---")
            st.markdown("#### Generated Code")
            st.code(code, language="python")
