"""
functions.py
Core LLM workflow functions for LabAutoMate.

Step 1: Function-Discovery (select drivers, produce function map + app design)
Step 2: Code-Generation (build prompt with driver source, generate Dash app)
Step 3: Self-Repair (patch or full regeneration from bug reports)
"""

import ast as _ast
import json, textwrap, re
from typing import List, Tuple, Sequence, Generator

from labautomate.catalog import pump_file_catalog
from labautomate.driver_loader import get_drivers_path, read_driver_source as _load_driver
from labautomate.llm_providers import LLMConfig, complete, stream

# Resolved path to pylabdrivers source (installed package or sibling clone)
_DRIVERS_PATH = get_drivers_path()


# -----------------------------------------------------------------
#  Helper – read driver source (from installed pylabdrivers package)
# -----------------------------------------------------------------
def read_driver_source(file_name: str, repo_path=None) -> str:
    return _load_driver(file_name, drivers_path=repo_path or _DRIVERS_PATH)


# -----------------------------------------------------------------
#  Helper – extract verified imports from Python source strings
# -----------------------------------------------------------------
def _extract_imports_from_source(filename: str, source: str) -> list:
    """
    Parse a Python source string and return correct import statements for
    every non-Error class defined at module level, plus any top-level
    'from X import Y' statements (for libraries like rseriesopc, oceandirect).
    Returns a list of import statement strings.
    """
    lines = []
    try:
        tree = _ast.parse(source)
    except SyntaxError:
        return lines

    module_stem = filename.rsplit(".", 1)[0]  # e.g. "teledyneisco"

    # Collect top-level import statements (non-stdlib external libs)
    stdlib = {
        "os", "sys", "re", "json", "time", "math", "threading", "subprocess",
        "collections", "functools", "itertools", "pathlib", "io", "struct",
        "typing", "abc", "copy", "datetime", "random", "string", "textwrap",
        "logging", "warnings", "contextlib", "dataclasses", "enum", "inspect",
    }
    for node in _ast.iter_child_nodes(tree):
        if isinstance(node, _ast.ImportFrom) and node.module:
            root = node.module.split(".")[0]
            if root not in stdlib:
                names = ", ".join(a.name for a in node.names)
                lines.append(f"from {node.module} import {names}")
        elif isinstance(node, _ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root not in stdlib:
                    lines.append(f"import {alias.name}")

    # Collect driver classes defined in the file
    # Determine if this is a pylabdrivers file (module stem matches known driver)
    from labautomate.driver_loader import get_drivers_path as _gdp
    try:
        drivers_path = _gdp()
        is_pylabdriver = (drivers_path / filename).exists()
    except Exception:
        is_pylabdriver = False

    driver_classes = [
        n.name for n in _ast.iter_child_nodes(tree)
        if isinstance(n, _ast.ClassDef) and "Error" not in n.name
    ]
    for cls_name in driver_classes:
        if is_pylabdriver:
            lines.append(f"from pylabdrivers.{module_stem} import {cls_name}")
        else:
            # Uploaded driver or reference file — import from its module name directly
            lines.append(f"from {module_stem} import {cls_name}")

    return lines


def build_verified_imports_block(
    pylabdriver_files: List[str],
    custom_sources: dict | None = None,
    template_codes: Sequence[Tuple[str, str]] | None = None,
    repo_path=None,
) -> str:
    """
    Build a '## VERIFIED IMPORTS' block listing the exact import statement for
    every class available in the context: PyLabDrivers drivers, uploaded custom
    drivers, and reference template files.

    This block is injected immediately before the generation instruction so the
    LLM always sees the correct class names and never has to guess.
    """
    effective_path = repo_path or _DRIVERS_PATH
    all_imports: list = []
    seen: set = set()

    def _add(stmt: str):
        if stmt not in seen:
            seen.add(stmt)
            all_imports.append(stmt)

    # PyLabDrivers drivers selected for this generation
    for fn in pylabdriver_files:
        try:
            if custom_sources and fn in custom_sources:
                src = custom_sources[fn]
            else:
                src = read_driver_source(fn, effective_path)
            for stmt in _extract_imports_from_source(fn, src):
                _add(stmt)
        except Exception:
            pass

    # Uploaded custom drivers (not in pylabdrivers)
    if custom_sources:
        for fn, src in custom_sources.items():
            if fn not in pylabdriver_files:
                for stmt in _extract_imports_from_source(fn, src):
                    _add(stmt)

    # Reference template files (Vapourtec, Ocean Optics, Dash examples)
    if template_codes:
        for name, src in template_codes:
            for stmt in _extract_imports_from_source(name, src):
                _add(stmt)

    if not all_imports:
        return ""

    lines = "\n".join(f"    {s}" for s in all_imports)
    return (
        "\n\n## VERIFIED IMPORTS — use these exact statements, no others:\n"
        f"{lines}\n"
    )


# -----------------------------------------------------------------
#  Step 1 – Function-Discovery and App-Design draft
# -----------------------------------------------------------------
def generate_function_map(
    config: LLMConfig,
    pipeline_spec: str,
    extra_driver_names: List[str] | None = None,
) -> Tuple[str, List[str], str]:
    """
    Return (function_map_yaml, [driver filenames], dash_app_design_text).
    """
    hardcoded = "\n".join(
        f"- **{fn}**: {desc}" for fn, desc in pump_file_catalog.items()
    )
    uploaded = ""
    if extra_driver_names:
        uploaded = "\n".join(f"- **{fn}**: (uploaded driver)" for fn in extra_driver_names)
    catalog_lines = hardcoded + ("\n" + uploaded if uploaded else "")

    prompt = textwrap.dedent(
        f"""
        You are an expert lab-automation engineer and Dash developer.

        ────────────────────────────────────────────────────────────────
        Available drivers
        ────────────────────────────────────────────────────────────────
        {catalog_lines}
        ────────────────────────────────────────────────────────────────
        TASK
        ────────────────────────────────────────────────────────────────
        1. Choose only the drivers you actually need.
        2. Produce a **minimal** YAML Function Map, BUT return it as a
        **single JSON string**, lines separated by \\n (back-slash n).
        Example: "start: isco.connect(port=${{port}})\\nrun: isco.run()"
        3. Write a short Dash-app design outline – also a JSON string with
        \\n between lines.

        ────────────────────────────────────────────────────────────────
        OUTPUT  (valid JSON, nothing else)
        ────────────────────────────────────────────────────────────────
        {{
        "drivers": ["file1.py", "file2.py"],
        "function_map": "start: isco.connect(port=${{isco_port}})\\nrun: isco.run()",
        "app_design":  "ISCO panel: port & rate inputs, Connect / Run buttons\\nReaxus panel: …"
        }}
        ────────────────────────────────────────────────────────────────

        ## User specification
        {pipeline_spec}
        """
    )

    raw = complete(config, prompt).strip()
    # Strip markdown fences if the model wrapped the JSON
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw.rstrip())
    # Extract first {...} block in case there's surrounding prose
    m = re.search(r"\{.*\}", raw, re.S)
    if m:
        raw = m.group(0)
    try:
        obj = json.loads(raw)
        return obj["function_map"], obj["drivers"], obj.get("app_design", "")
    except Exception:
        raise RuntimeError("Un-parseable discovery output:\n" + raw)


# -----------------------------------------------------------------
#  Step 2 – Build final prompt for code generation
# -----------------------------------------------------------------
DESIGN_DOC = textwrap.dedent(
    """
    ### Workflow Design
    1 Driver discovery → Automation Workflow and Dashboard Layout Plan (reviewed and approved by the user)
    2 Code generation  → Dash web app
"""
)

def _fmt_template_header(template_src: str) -> str:
    """Return template section header + source, or empty string — no backslash in f-string."""
    if not template_src:
        return ""
    return "### Template app code (reference only)\n" + template_src + "\n\n"


def _fmt_template_code(templates: Sequence[Tuple[str, str]]) -> str:
    if not templates:
        return ""
    return "\n\n".join(
        f"# ===== TEMPLATE {name} =====\n```python\n{code}\n```"
        for name, code in templates
    )

def build_final_prompt(
    user_spec: str,
    function_map_yaml: str,
    driver_files: List[str],
    repo_path=None,
    template_codes: Sequence[Tuple[str, str]] | None = None,
    design_notes: str = "",
    custom_driver_sources: dict[str, str] | None = None,
) -> str:
    effective_path = repo_path or _DRIVERS_PATH
    drivers_src_parts = []
    for fn in driver_files:
        if custom_driver_sources and fn in custom_driver_sources:
            code = custom_driver_sources[fn]
        else:
            try:
                code = read_driver_source(fn, effective_path)
            except FileNotFoundError:
                code = "# source not available"
        drivers_src_parts.append(f"# ===== {fn} =====\n```python\n{code}\n```")
    drivers_src = "\n\n".join(drivers_src_parts)
    template_src = _fmt_template_code(template_codes or [])

    extra_design = (
        f"\n### Additional app-design notes (edited by user)\n{design_notes}\n"
        if design_notes.strip()
        else ""
    )

    verified_imports = build_verified_imports_block(
        pylabdriver_files=driver_files,
        custom_sources=custom_driver_sources,
        template_codes=template_codes,
        repo_path=repo_path,
    )

    instructions = textwrap.dedent(
        """
        You are an expert Python/Dash developer.
        Implement the approved Automation Workflow using ONLY the driver code below.
        If template code is supplied, you may reuse patterns but must adapt
        them as needed. Output **one** triple-backticked Python block with the
        full Dash 2.x app.
    """
    )
    return (
        f"{DESIGN_DOC}\n\n"
        f"### User specification\n{user_spec}\n\n"
        f"### Approved Automation Workflow\n```yaml\n{function_map_yaml}\n```\n"
        f"### Approved Dash Design \n"
        f"{extra_design}\n"
        f"### Driver source code\n{drivers_src}\n\n"
        f"{_fmt_template_header(template_src)}"
        f"{verified_imports}"
        f"{instructions}"
    )


# -----------------------------------------------------------------
#  Step 3 – LLM → Dash code
# -----------------------------------------------------------------
def generate_dash_code(config: LLMConfig, final_prompt: str, system_prompt: str = "") -> str:
    """Generate Dash app code from the final assembled prompt."""
    response = complete(config, final_prompt, system_prompt)
    m = re.search(r"```python(.*?)```", response, re.S | re.I)
    if not m:
        raise RuntimeError("Dash code block not found in model response.")
    return textwrap.dedent(m.group(1)).strip()


def stream_dash_code(config: LLMConfig, final_prompt: str, system_prompt: str = "") -> Generator[str, None, None]:
    """Stream Dash app code generation, yielding chunks as they arrive."""
    yield from stream(config, final_prompt, system_prompt)


# -----------------------------------------------------------------
#  Step 4 – README generation
# -----------------------------------------------------------------
def generate_readme(config: LLMConfig, app_code: str, user_spec: str) -> str:
    prompt = textwrap.dedent(
        f"""
        You are an expert technical writer.

        ## Task
        Write a concise README.md (≤ 120 lines) for the Dash 2.x app below.
        It should contain:
          * Project title
          * One-sentence overview
          * Quick-start (how to run with `python file.py`)
          * Key features (bulleted list)
          * Requirements (pip install list)
          * How to extend / customise

        ## User specification
        {user_spec}

        ## Full app source
        ```python
        {app_code}
        ```
    """
    )
    return complete(config, prompt)


# -----------------------------------------------------------------
#  Patch or full-regen helpers (debug cycle)
# -----------------------------------------------------------------
def generate_patch(config: LLMConfig, prompt: str) -> str:
    """Generate a JSON patch or fix instructions from a bug report."""
    return complete(config, prompt)


def refine_design_plan(
    config: LLMConfig,
    current_workflow: str,
    current_layout_plan: str,
    user_request: str,
    driver_files: list,
) -> tuple:
    """
    Given the current Automation Workflow and Dashboard Layout Plan plus a
    plain-English refinement request, return (updated_workflow, updated_layout_plan).
    """
    prompt = textwrap.dedent(
        f"""
        You are a lab automation expert and Dash UI designer.
        The user wants to modify their app design based on the request below.

        Current Automation Workflow:
        {current_workflow}

        Current Dashboard Layout Plan:
        {current_layout_plan}

        Drivers available: {', '.join(driver_files)}

        User's refinement request:
        {user_request}

        Update BOTH documents according to the request. If the request only affects
        one of them, keep the other exactly as-is.

        Return ONLY valid JSON in this exact format — no markdown, no explanation:
        {{
          "workflow": "<updated automation workflow text>",
          "layout_plan": "<updated dashboard layout plan text>"
        }}
        """
    )
    raw = complete(config, prompt).strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw.rstrip())
    m = re.search(r"\{.*\}", raw, re.S)
    if m:
        raw = m.group(0)
    obj = json.loads(raw)
    return obj["workflow"], obj["layout_plan"]


def generate_flow_diagram(
    config: LLMConfig,
    function_map_yaml: str,
    driver_files: list,
    app_design: str,
) -> str:
    """
    Generate a Vis.js-compatible JSON flowchart of the high-level automation logic.
    Returns a JSON string {"nodes": [...], "edges": [...]} for browser rendering.
    Readable by non-experts — plain-English labels, no code detail.
    """
    prompt = textwrap.dedent(
        f"""
        You are a lab automation expert. Create a high-level flow diagram that shows
        the automation logic of this application in plain, readable terms.

        AUDIENCE: Laboratory scientists who are not software developers.
        PURPOSE: Show WHAT the app does and in WHAT ORDER — not how it is coded.

        OUTPUT FORMAT — return ONLY valid JSON, nothing else:
        {{
          "nodes": [
            {{"id": 1, "label": "User clicks Connect", "group": "user"}},
            {{"id": 2, "label": "ISCO Pump", "group": "instrument"}},
            {{"id": 3, "label": "Connection OK?", "group": "decision"}},
            {{"id": 4, "label": "Pump ready to run", "group": "outcome"}},
            {{"id": 5, "label": "Data saved to Excel", "group": "data"}}
          ],
          "edges": [
            {{"from": 1, "to": 2}},
            {{"from": 2, "to": 3}},
            {{"from": 3, "to": 4, "label": "Yes"}}
          ]
        }}

        NODE GROUPS — use exactly these strings:
        - "user"       : user actions (light teal box)
        - "instrument" : instrument names / major processing steps (dark blue box)
        - "decision"   : yes/no branch points (teal diamond)
        - "outcome"    : instrument responses or results (white box)
        - "data"       : data saving / export events (purple cylinder)

        RULES:
        - Plain English only — no Python, no method names, no callback IDs
        - 4-8 nodes per instrument section; 15-35 nodes total
        - Number IDs sequentially starting from 1
        - Edges must flow in logical top-to-bottom order
        - Every node must be reachable from node 1

        Automation Workflow:
        {function_map_yaml[:2000]}

        Instruments used: {', '.join(driver_files)}

        App Design:
        {app_design[:1500]}
        """
    )
    raw = complete(config, prompt).strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw.rstrip())
    m = re.search(r"\{.*\}", raw, re.S)
    if m:
        raw = m.group(0)
    return raw


def generate_full_code(config: LLMConfig, prompt: str, system_prompt: str = "") -> str:
    """Regenerate full code from a bug report + original code."""
    response = complete(config, prompt, system_prompt)
    match = re.search(r"```python(.*?)```", response, re.S | re.I)
    if not match:
        raise RuntimeError("Updated Dash code block not found.")
    return textwrap.dedent(match.group(1)).strip()


# -----------------------------------------------------------------
#  Automation Script — instrument auto-detection
# -----------------------------------------------------------------
def generate_ui_mockup(
    config: LLMConfig,
    app_design: str,
    function_map_yaml: str,
) -> str:
    """
    Generate a self-contained HTML/CSS mockup of the Dash app UI layout.
    Returns an HTML string that can be rendered directly in an iframe.
    """
    prompt = textwrap.dedent(
        f"""
        You are a senior UI designer creating a professional scientific laboratory automation mockup.

        CRITICAL RULE: NEVER include any company name anywhere — not in titles, labels, footers,
        comments, or any UI text. The application should not identify or reference any organization.

        MANDATORY COLOR PALETTE:
        - Background: #F7F7F7 (app), #FFFFFF (cards)
        - Primary (≥30%): Primary Blue #2563EB — title bar accent, primary buttons, active indicators, borders
        - Secondary: Dark Slate #1E293B — section headers, body text, card titles
        - Accent: Light Blue #60A5FA — badges, highlights, hover-state borders
        - White background with generous whitespace
        - Flat design ONLY — NO gradients, NO drop-shadows heavier than 0 1px 4px rgba(0,0,0,0.08), NO 3D effects
        - Consistent 1-2px borders and line weights
        - Executive-level pharmaceutical presentation aesthetic

        ADVANCED CSS REQUIREMENTS (inline CSS only — no external links):
        - Layout: CSS Grid or Flexbox (never HTML table layout)
        - Title bar: background #1E293B; color #FFFFFF; 4px left border in #2563EB; padding 12px 20px
        - Cards: border-radius:8px; box-shadow:0 1px 4px rgba(0,0,0,0.08); padding:16px; background:#FFFFFF
        - Section headers: color:#1E293B; font-weight:600; border-bottom:2px solid #2563EB; padding-bottom:6px; margin-bottom:12px
        - Buttons: border-radius:4px; font-weight:500; padding:6px 14px; border:none; cursor:pointer
          * Connect/Start: background:#28a745; color:#FFFFFF
          * Disconnect/Stop: background:#dc3545; color:#FFFFFF
          * Run/Set/Apply: background:#2563EB; color:#FFFFFF
          * Warning/Pause: background:#ffc107; color:#1E293B
        - Status badges: border-radius:12px; padding:2px 10px; font-size:11px; font-weight:500
          * Connected: background:#d4edda; color:#155724; border:1px solid #c3e6cb
          * Disconnected: background:#f8d7da; color:#721c24; border:1px solid #f5c6cb
        - Input fields: border:1px solid #D9D9D9; border-radius:4px; padding:5px 9px; font-size:13px; width:100%; box-sizing:border-box
        - Dropdown selects: same as input fields
        - Status message area: background:#F0F0F0; border-radius:4px; padding:8px 12px; font-style:italic; color:#555; font-size:12px; min-height:32px
        - Font: font-family:-apple-system,Helvetica Neue,Arial,sans-serif; color:#1E293B
        - All numeric values in inputs must have realistic placeholders (e.g. "1.5", "100", "25.0")

        PROFESSIONAL SVG ICONS (inline SVG, 24×24px, color #2563EB, placed next to section headers):
        - Syringe/HPLC pump: draw a rectangle body with a smaller rectangle plunger extending left
        - Peristaltic/flow pump: draw a circle with internal curved arrows (rotary symbol)
        - Valve / flow controller: draw a diamond with arrows through it
        - Spectrometer / UV-Vis: draw a prism triangle dispersing a line into spread lines
        - Pressure sensor: draw a gauge circle with a needle line
        - Data / chart: draw a simple bar chart (3 ascending bars)
        - Generic instrument: draw a rounded hexagon outline
        - Connect status indicator: filled circle — green #28a745 if connected, grey #999 if not

        LAYOUT REQUIREMENTS:
        - Render EVERY button, input field, dropdown, and indicator from the spec
        - Use a CSS grid matching the described layout (2-column typical for multi-instrument)
        - Each instrument gets its own card with SVG icon + instrument name as header
        - Realistic placeholder values in all inputs
        - At least one status indicator (badge) per instrument card
        - App title bar at top spanning full width with app name and "Laboratory Automation" subtitle
        - Footer: thin #D9D9D9 border, small text "Laboratory Automation"

        App Design:
        {app_design[:3000]}

        Function Map (for context):
        {function_map_yaml[:1500]}

        Return ONLY the complete HTML string starting with <!DOCTYPE html> — inline CSS and SVG only, no CDN links, no markdown.
        """
    )
    raw = complete(config, prompt).strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw.rstrip())
    return raw


def detect_drivers_for_automation(
    config: LLMConfig,
    prompt_text: str,
    catalog: dict,
) -> list:
    """
    Given the user's automation prompt and the driver catalog, return the list
    of driver filenames (e.g. ['teledynereaxus.py', 'milligatpump.py']) that
    match the instruments mentioned in the prompt.
    """
    catalog_lines = "\n".join(
        f"- {fn}: {desc}" for fn, desc in sorted(catalog.items())
    )
    prompt = textwrap.dedent(
        f"""
        You are a lab automation expert. Identify which PyLabDrivers instrument
        drivers are needed for the user's request below.

        Available drivers (filename: description):
        {catalog_lines}

        User's request:
        {prompt_text}

        Match instrument names flexibly (e.g. "Teledyne ISCO ReaXus" →
        "teledynereaxus.py", "milliGAT pump" → "milligatpump.py").

        Return ONLY a JSON object with a single key "drivers" containing a list
        of matched filenames. Include only drivers that are genuinely needed.
        Example: {{"drivers": ["teledynereaxus.py", "milligatpump.py"]}}
        """
    )
    raw = complete(config, prompt).strip()
    # Strip markdown fences if the model wrapped the JSON
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw.rstrip())
    try:
        obj = json.loads(raw)
        detected = obj.get("drivers", [])
    except Exception:
        # Fallback: extract a JSON array from anywhere in the response
        m = re.search(r"\[.*?\]", raw, re.S)
        detected = json.loads(m.group(0)) if m else []
    # Filter to only filenames that actually exist in the catalog
    valid = set(catalog.keys())
    return [fn for fn in detected if fn in valid]
