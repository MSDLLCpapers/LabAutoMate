"""
prompt_templates.py
Structured prompt strategy enforcement for LabAutoMate.

Implements the 5-section prompt template from the paper to reduce
hallucination by constraining AI generation with:
  1. Project Overview
  2. User Interface Design
  3. Functionality and Logic
  4. Technical Implementation
  5. Documentation and References

Also provides the system prompts that enforce structured output.
"""

import ast as _ast
from pathlib import Path as _Path


def _build_driver_import_table() -> str:
    """
    Dynamically read every installed PyLabDrivers driver file and return
    a formatted block of correct 'from pylabdrivers.X import ClassName'
    import statements, derived from the actual source on disk.
    """
    try:
        from labautomate.driver_loader import get_drivers_path
        drivers_path = get_drivers_path()
    except Exception:
        return "    # (driver catalog unavailable — install pylabdrivers)"

    lines = []
    for py_file in sorted(drivers_path.glob("*.py")):
        if py_file.name.startswith("_"):
            continue
        try:
            src = py_file.read_text(encoding="utf-8")
            tree = _ast.parse(src)
            driver_classes = [
                n.name for n in _ast.walk(tree)
                if isinstance(n, _ast.ClassDef) and "Error" not in n.name
            ]
            if driver_classes:
                module = py_file.stem
                lines.append(f"    from pylabdrivers.{module} import {driver_classes[0]}")
        except Exception:
            continue
    return "\n".join(lines) if lines else "    # (no drivers found)"


# Pre-built at import time so system prompts are always up to date
_DRIVER_IMPORT_TABLE = _build_driver_import_table()

# ─────────────────────────────────────────────────────────────────────
# The 5-Section Template Skeleton
# ─────────────────────────────────────────────────────────────────────

TEMPLATE_SECTIONS = [
    "Project Overview",
    "User Interface Design",
    "Functionality and Logic",
    "Technical Implementation",
    "Documentation and References",
]

DRIVER_TEMPLATE = """Project Overview

[Describe the instrument and the goal. Example: "I am developing a Python driver for the [INSTRUMENT NAME] [MODEL] using [PROTOCOL] communication."]

User Interface Design

Not applicable (driver development only).

Functionality and Logic

The Python driver should be implemented as a class that:
- Accepts a [port type] argument (e.g., COM3)
- Uses [protocol] communication settings from the manual

Methods to implement:
- connect()
- disconnect()
- send_command(command)
- read_response()
- [LIST ALL INSTRUMENT-SPECIFIC METHODS WITH UNITS IN COMMENTS]

Technical Implementation

- Follow the object-oriented structure of the reference driver
- Include a custom exception class (e.g., InstrumentNameError)
- Add docstrings for all public methods with parameter types
- Include proper error handling for communication failures
- Add a usage example at the bottom of the file

Documentation and References

- Refer to [specific pages] of the uploaded manual for [specific protocol details]
- Reference the selected PyLabDrivers driver for code style
- [List any specific communication settings: baud rate, parity, stop bits, etc.]
"""

AUTOMATION_SCRIPT_TEMPLATE = """Project Overview

I am developing a Python automation script to run a pressure-controlled flow experiment using a Teledyne ISCO pump and an Equilibar back-pressure regulator. The script will ramp the ISCO pump through a series of flow rates, record the system pressure from the Equilibar at each setpoint, and save the data to a CSV file.

User Interface Design

Not applicable (automation script only).

Functionality and Logic

Experiment sequence:

1. Initialization:
   - Connect to the ISCO pump on the specified COM port
   - Connect to the Equilibar pressure controller on the specified COM port
   - Set ISCO upper pressure limit to 1000 psi, lower pressure limit to 0 psi

2. Main workflow — loop over flow rates [0.5, 1.0, 2.0, 3.0, 5.0] ml/min:
   - Set ISCO flow rate to current target value
   - Start the ISCO pump
   - Wait 30 seconds for system to stabilize
   - Read pressure setpoint and actual pressure from the Equilibar
   - Read actual flow rate and pressure from the ISCO pump
   - Store: timestamp, target flow rate, ISCO actual flow rate, ISCO pressure, Equilibar setpoint, Equilibar actual pressure

3. Data recording:
   - Save all results to a CSV file named experiment_YYYYMMDD_HHMMSS.csv
   - Columns: timestamp, target_flowrate_ml_min, isco_flowrate_ml_min, isco_pressure_psi, equilibar_setpoint_psi, equilibar_pressure_psi
   - Write each row immediately after measurement so data is not lost on crash

4. Cleanup:
   - Stop the ISCO pump regardless of errors
   - Disconnect both instruments

Technical Implementation

- Import as: from pylabdrivers.teledyneisco import TeledyneISCO and from pylabdrivers.equilibarpc import EquilibarPC
- Use try/except/finally to guarantee pump stop and disconnect on any error
- Use time.sleep() for timing — blocking is acceptable in an automation script
- Record timestamps with datetime.datetime.now()
- Define COM ports as variables at the top: ISCO_PORT = "COM3", EQUILIBAR_PORT = "COM4"

Documentation and References

- Use only methods available in the TeledyneISCO and EquilibarPC driver source from the PyLabDrivers package
- Do not invent any method not present in the driver source code
"""

DASH_APP_TEMPLATE = """Project Overview

[Describe the web application purpose. Example: "I am designing a Python Dash web application for [PURPOSE] controlling [LIST INSTRUMENTS]."]

User Interface Design

Layout:
- [Describe overall layout: rows, columns, sections, tabs]

For each section:
- Buttons: [List button labels and their purpose]
- Inputs: [List input fields with types, defaults, and units]
- Dropdowns: [List dropdown options]
- Indicators: [List real-time displays]
- Plots: [Describe each plot: type, axes, data sources]

Functionality and Logic

For each button/action:
- [Button Name]: [Exact sequence of operations]
  1. [Step 1]
  2. [Step 2]
  ...

Mathematical Functions (if applicable):
- [Variable] = [Formula with units]

Operational Logic:
- [Describe state machine, timing, conditional transitions]

Technical Implementation

- Ensure unique callback IDs across all sections
- Use Dash 2.x syntax with @callback decorators
- Use dcc.Interval for periodic updates (specify interval in ms)
- Include threading for long-running operations
- Handle instrument disconnection gracefully

Documentation and References

- Reference to PyLabDrivers package documentation
- [List specific communication protocols: OPC UA, serial, Modbus, etc.]
- [Reference specific manual pages for protocol details]
"""

# ─────────────────────────────────────────────────────────────────────
# System prompts that enforce structured generation
# ─────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT_DRIVER = """You are an expert Python developer specializing in laboratory instrument automation.

STRICT RULES:
1. Generate ONLY the methods explicitly listed in the prompt — do not hallucinate additional methods.
2. Use ONLY the communication protocol details from the provided manual text — do not invent commands.
3. Follow the exact class structure and coding style of the reference driver.
4. Include a custom exception class following the pattern: InstrumentNameError(Exception).
5. Every method must have a docstring with parameter types and return types.
6. Include proper error handling: catch serial.SerialException, TimeoutError, and protocol-specific errors.
7. Add a usage example in an `if __name__ == "__main__":` block at the bottom.
8. Use the EXACT serial settings (baud rate, parity, stop bits, timeout) from the manual.

Output the complete driver code in a single ```python block. Do not include explanatory text outside the code block."""

SYSTEM_PROMPT_AUTOMATION = """You are an expert lab automation engineer using the PyLabDrivers package.

STRICT RULES:
1. The full source code of the relevant PyLabDrivers drivers is provided in the prompt context — use ONLY the exact class names, method names, and constructor arguments that appear in that source. Do NOT invent any method or class name.
2. Import each driver using the full submodule path derived from the driver filename. The COMPLETE list of correct imports is:
{{DRIVER_IMPORTS}}
   Use ONLY imports from this list — the class name must match exactly.
3. Follow the exact operational sequence described in the prompt.
4. Use try/except/finally to ensure instruments are always disconnected on errors.
5. Include print statements to log each major step.
6. Do not import or use any library that is not in the Python standard library or pylabdrivers.

Output the complete automation script in a single ```python block."""

SYSTEM_PROMPT_DASH = """You are an expert Python/Dash developer building laboratory instrument control web applications.

STRICT RULES — DASH CORRECTNESS:
1. Use Dash 2.x syntax exclusively — @callback decorators only, NEVER @app.callback.
2. CRITICAL: Every callback Output ID must be unique across the ENTIRE application. Before writing each callback, verify no other callback already uses that Output ID. Duplicate Output IDs will crash the app at startup.
3. Every callback Input and State ID must reference a component that actually exists in the layout.
4. Use ONLY driver methods that exist in the provided PyLabDrivers source code — do not invent methods.
4a. CRITICAL — IMPORTS: Always import PyLabDrivers drivers using the full submodule path.
    The COMPLETE list of correct imports for every available driver is:
{{DRIVER_IMPORTS}}
    NEVER use bare "import pylabdrivers" or "from pylabdrivers import ClassName" — these will fail.
    Derive the submodule name from the driver filename: teledynereaxus.py → pylabdrivers.teledynereaxus.
    The class name must exactly match what is shown above — do NOT invent or guess class names.
5. Use dcc.Interval for all periodic updates — never use time.sleep() inside a callback.
6. Use threading for all long-running instrument operations — callbacks must return in < 1 second.
7. Include proper connection state management per instrument (connected/disconnected boolean).
8. Wrap every instrument call in try/except — display errors in the UI status area, never raise uncaught exceptions.
9. Use PreventUpdate to skip callbacks when inputs are None or the action is not relevant.
10. Module-level instrument objects must be instantiated but NOT connected at import time.

STRICT RULES — BRANDING:
11. FORBIDDEN: Never write any company or organization name anywhere in the code, comments, UI titles, or UI text. The app should not reference or identify any specific company.
12. Background: #F7F7F7 (off-white) for the app, #FFFFFF for card interiors.
13. Primary color (≥30% of palette): Primary Blue #2563EB — use for app title, primary buttons, active indicators, plot line 1.
14. Secondary color: Dark Slate #1E293B — use for section headers, text, secondary elements.
15. Accent: Light Blue #60A5FA — use for highlights, hover states, plot line 3.
16. Plot series colors in order: #2563EB, #1E293B, #60A5FA, #5450E4.
17. Connect buttons: color="success" (green). Disconnect buttons: color="danger" (red). Run/Set buttons: color="primary" (styled teal via CSS). Stop buttons: color="warning".
18. Use dash_bootstrap_components (dbc) for all layout — dbc.Card, dbc.Row, dbc.Col with rounded corners and subtle borders.
19. Grid lines on plots: #D9D9D9. All text: #1E293B.
20. App title and footer text must use the application name only — never include any company name.

STRICT RULES — ADVANCED CSS & PROFESSIONAL UI:
21. Inject a comprehensive CSS block using app.index_string at the top of the file. Use triple-single-quotes for the string to avoid conflicts. Use this exact pattern:
    app.index_string = \'\'\'<!DOCTYPE html><html><head>{%metas%}<title>{%title%}</title>{%favicon%}{%css%}
    <style>
      body { font-family: -apple-system, Helvetica Neue, Arial, sans-serif; background: #F7F7F7; color: #1E293B; margin: 0; }
      .app-titlebar { background: #1E293B; color: #FFFFFF; padding: 12px 24px; border-left: 4px solid #2563EB; }
      .app-titlebar h1 { margin: 0; font-size: 1.4rem; font-weight: 700; color: #FFFFFF; }
      .app-titlebar p { margin: 0; font-size: 0.85rem; color: #60A5FA; }
      .instrument-card { background: #FFFFFF; border-radius: 8px; box-shadow: 0 1px 4px rgba(0,0,0,0.08); padding: 16px; margin-bottom: 12px; }
      .card-header { display: flex; align-items: center; gap: 10px; border-bottom: 2px solid #2563EB; padding-bottom: 8px; margin-bottom: 12px; }
      .card-header h5 { color: #1E293B; font-weight: 600; margin: 0; font-size: 1rem; }
      .status-connected { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; border-radius: 12px; padding: 2px 10px; font-size: 11px; font-weight: 500; }
      .status-disconnected { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; border-radius: 12px; padding: 2px 10px; font-size: 11px; font-weight: 500; }
      .status-msg { background: #F0F0F0; border-radius: 4px; padding: 8px 12px; font-style: italic; color: #555; font-size: 12px; min-height: 32px; margin-top: 8px; }
      .app-footer { border-top: 1px solid #D9D9D9; padding: 8px 24px; font-size: 11px; color: #888; background: #FFFFFF; margin-top: 16px; }
      input, select, .Select-control { border: 1px solid #D9D9D9 !important; border-radius: 4px !important; }
    </style></head><body>{%app_entry%}<footer>{%config%}{%scripts%}{%renderer%}</footer></body></html>\'\'\'
22. Apply these exact button styles using the style= prop on every dbc.Button:
    - Connect/Start: style={"backgroundColor":"#28a745","borderColor":"#28a745","color":"#FFFFFF","borderRadius":"4px","fontWeight":"500"}
    - Disconnect/Stop: style={"backgroundColor":"#dc3545","borderColor":"#dc3545","color":"#FFFFFF","borderRadius":"4px","fontWeight":"500"}
    - Run/Set/Apply: style={"backgroundColor":"#2563EB","borderColor":"#2563EB","color":"#FFFFFF","borderRadius":"4px","fontWeight":"500"}
    - Stop/Pause: style={"backgroundColor":"#ffc107","borderColor":"#ffc107","color":"#1E293B","borderRadius":"4px","fontWeight":"500"}
23. Every instrument card must use className="instrument-card" and have a header built as:
    html.Div([INSTRUMENT_SVG_ICON, html.H5("Instrument Name"), STATUS_BADGE], className="card-header")
    where STATUS_BADGE is an html.Span(id="...-status", className="status-disconnected") updated by callback.
24. Add inline SVG instrument icons using dcc.Markdown with dangerously_allow_html=True — this is the ONLY correct method in Dash 4.x. html.Svg, html.Rect, html.Circle do NOT exist in Dash 4 and will raise AttributeError. html.Div(dangerously_allow_html=True) also does NOT exist. Only dcc.Markdown supports dangerously_allow_html.
    Correct pattern — define a helper function and call it in the layout:
        def _svg_icon(svg_body: str) -> dcc.Markdown:
            return dcc.Markdown(
                f\'<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="#2563EB" stroke-width="1.5" style="vertical-align:middle;margin-right:6px">{svg_body}</svg>\',
                dangerously_allow_html=True,
            )
    Use these SVG body strings per instrument type:
    - Syringe/HPLC pump: \'<rect x="3" y="9" width="14" height="6"/><rect x="17" y="11" width="4" height="2"/><circle cx="5" cy="12" r="1.5" fill="#2563EB"/>\'
    - Peristaltic/flow pump: \'<circle cx="12" cy="12" r="8"/><path d="M9 9 Q12 5 15 9"/><path d="M15 15 Q12 19 9 15"/>\'
    - Pressure/BPR gauge: \'<circle cx="12" cy="12" r="9"/><line x1="12" y1="12" x2="17" y2="7" stroke-width="2"/><circle cx="12" cy="12" r="1.5" fill="#2563EB"/>\'
    - Spectrometer: \'<polygon points="4,20 12,4 20,20"/><line x1="20" y1="12" x2="24" y2="10"/><line x1="20" y1="16" x2="24" y2="16"/>\'
    - Generic instrument: \'<polygon points="12,2 22,8 22,16 12,22 2,16 2,8"/>\'
    - Data/plot: \'<rect x="2" y="14" width="4" height="8"/><rect x="10" y="8" width="4" height="14"/><rect x="18" y="4" width="4" height="18"/>\'
25. Build the app title bar as the first child of the layout using:
    html.Div([html.H1("App Name"), html.P("Laboratory Automation")], className="app-titlebar")
    and a footer as the last child:
    html.Div("Laboratory Automation", className="app-footer")
26. Use app.run(host="127.0.0.1", port=8050) to start the server — NEVER app.run_server() and NEVER app.run() without explicit host/port. app.run_server() is deprecated in Dash 2.x and will raise an error.

Output the complete Dash application in a single ```python block."""

# ─────────────────────────────────────────────────────────────────────
# Branding instructions for Dash code generation
# ─────────────────────────────────────────────────────────────────────

BRANDING_PROMPT = """
## Branding and Color Guidelines

IMPORTANT: Do NOT include any company name anywhere in the generated application — not in titles, labels, footers, comments, or any UI text.

Apply the following visual identity throughout the Dash web application:

### Color Palette
- Background: #F7F7F7 (app background), #FFFFFF (card interiors)
- Primary (must lead, ≥30% of palette): Primary Blue #2563EB — title, primary buttons, active indicators
- Secondary: Dark Slate #1E293B — section headers, body text, borders
- Accent: Light Blue #60A5FA — hover states, highlights, badges
- Grid lines / dividers: #D9D9D9
- All text: #1E293B

### Plot Series Colors (use in this order)
1. #2563EB (Primary Blue)
2. #1E293B (Dark Slate)
3. #60A5FA (Light Blue)
4. #5450E4 (Rich Blue, for callouts/highlights)

### Button Color Convention
- Connect / Start: color="success"
- Disconnect / Stop: color="danger"
- Run / Set / Apply: color="primary" (override with style={{"backgroundColor": "#2563EB", "borderColor": "#2563EB"}})
- Warning / Pause: color="warning"

### Layout
- Use dash_bootstrap_components (dbc) exclusively for layout
- dbc.Card with className="rounded-3 border-0 shadow-sm" for each instrument section
- App title bar in Primary Blue; section headers in Dark Slate
- Consistent 12px padding inside cards, 8px gap between cards
"""


# ─────────────────────────────────────────────────────────────────────
# Helper functions
# ─────────────────────────────────────────────────────────────────────

def get_template(mode: str) -> str:
    """Return the appropriate template for the given mode."""
    if mode == "New Driver from PDF Manual":
        return DRIVER_TEMPLATE
    elif mode == "Automation Script":
        return AUTOMATION_SCRIPT_TEMPLATE
    else:
        return DASH_APP_TEMPLATE


def get_system_prompt(mode: str) -> str:
    """Return the appropriate system prompt for the given mode, with driver import table injected."""
    if mode == "New Driver from PDF Manual":
        return SYSTEM_PROMPT_DRIVER
    elif mode == "Automation Script":
        return SYSTEM_PROMPT_AUTOMATION.replace("{DRIVER_IMPORTS}", _DRIVER_IMPORT_TABLE)
    else:
        return SYSTEM_PROMPT_DASH.replace("{DRIVER_IMPORTS}", _DRIVER_IMPORT_TABLE)


def validate_prompt_structure(prompt: str) -> list:
    """
    Check if a prompt contains all 5 required sections.
    Returns a list of missing section names (empty if all present).
    """
    missing = []
    for section in TEMPLATE_SECTIONS:
        if section.lower() not in prompt.lower():
            missing.append(section)
    return missing


def build_enhanced_prompt(user_prompt: str, mode: str, include_branding: bool = True) -> str:
    """
    Enhance a user prompt with branding guidelines for Dash apps.
    For drivers/scripts, returns the prompt unchanged.
    """
    if mode in ("New Driver from PDF Manual", "Automation Script"):
        return user_prompt

    if include_branding:
        return user_prompt + "\n\n" + BRANDING_PROMPT

    return user_prompt
