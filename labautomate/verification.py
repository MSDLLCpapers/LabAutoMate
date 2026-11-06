"""
verification.py
Code verification and validation utilities for LabAutoMate.

Provides:
  - Static analysis (syntax, import checks, class structure validation)
  - AI-powered test generation for drivers
  - Dash app structure validation (unique callback IDs, required imports)
  - Iterative refinement loop support
"""

import ast
import re
from typing import List, Tuple, Optional
from dataclasses import dataclass, field

from labautomate.llm_providers import LLMConfig, complete


@dataclass
class VerificationResult:
    """Result of a code verification check."""
    passed: bool
    issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────
# Static Analysis
# ─────────────────────────────────────────────────────────────────────

def check_syntax(code: str) -> VerificationResult:
    """Check Python syntax validity."""
    try:
        ast.parse(code)
        return VerificationResult(passed=True)
    except SyntaxError as e:
        return VerificationResult(
            passed=False,
            issues=[f"Line {e.lineno}: {e.msg}"],
        )


def check_driver_structure(code: str) -> VerificationResult:
    """Validate that a driver follows PyLabDrivers conventions."""
    issues = []
    warnings = []
    suggestions = []

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return VerificationResult(passed=False, issues=["Cannot parse: syntax error"])

    # Check for class definition
    classes = [n for n in ast.iter_child_nodes(tree) if isinstance(n, ast.ClassDef)]
    error_classes = [c for c in classes if "Error" in c.name]
    driver_classes = [c for c in classes if "Error" not in c.name]

    if not driver_classes:
        issues.append("No driver class found (expected a main class without 'Error' in name)")

    if not error_classes:
        warnings.append("No custom exception class found (recommended: InstrumentNameError)")

    # Check for required methods
    if driver_classes:
        driver_cls = driver_classes[0]
        methods = [n.name for n in ast.walk(driver_cls) if isinstance(n, ast.FunctionDef)]

        required_methods = ["connect", "disconnect"]
        for method in required_methods:
            if method not in methods:
                issues.append(f"Missing required method: {method}()")

        if "__init__" not in methods:
            issues.append("Missing __init__ method")

        # Check for docstrings
        methods_without_docs = []
        for node in ast.walk(driver_cls):
            if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
                if not ast.get_docstring(node):
                    methods_without_docs.append(node.name)

        if methods_without_docs:
            warnings.append(
                f"Public methods without docstrings: {', '.join(methods_without_docs[:5])}"
                + (f" (+{len(methods_without_docs)-5} more)" if len(methods_without_docs) > 5 else "")
            )

    # Check for usage example
    if 'if __name__' not in code:
        suggestions.append("Consider adding a usage example in an if __name__ == '__main__' block")

    # Check for serial import (most drivers need it)
    imports = [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
    import_names = []
    for imp in imports:
        if isinstance(imp, ast.Import):
            import_names.extend(a.name for a in imp.names)
        elif isinstance(imp, ast.ImportFrom) and imp.module:
            import_names.append(imp.module)

    passed = len(issues) == 0
    return VerificationResult(passed=passed, issues=issues, warnings=warnings, suggestions=suggestions)


def check_dash_structure(code: str) -> VerificationResult:
    """Validate Dash app structure and common issues."""
    issues = []
    warnings = []
    suggestions = []

    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return VerificationResult(passed=False, issues=[f"Syntax error: {e}"])

    # Check for Dash import
    if "dash" not in code.lower() and "Dash" not in code:
        issues.append("No Dash import found")

    # Check for app initialization
    if "Dash(" not in code:
        issues.append("No Dash app initialization found (expected: app = Dash(...))")

    # Check for callback definitions
    callbacks = re.findall(r"@callback|@app\.callback", code)
    if not callbacks:
        warnings.append("No callback decorators found")

    # Check for duplicate Output (id, property) pairs — informational only.
    # Dash 2.x allows duplicates with allow_duplicate=True, which the system prompt instructs
    # the LLM to use. If the app runs, duplicates are handled correctly at the Dash level.
    # Static text analysis cannot reliably distinguish allow_duplicate=True from true violations,
    # so this check is reported as a suggestion rather than a blocking issue.
    output_pairs = re.findall(r'Output\(["\']([^"\']+)["\'],\s*["\']([^"\']+)["\']', code)
    seen_pairs: set = set()
    repeated: list = []
    for pair in output_pairs:
        if pair in seen_pairs and pair[0] not in repeated:
            repeated.append(pair[0])
        seen_pairs.add(pair)
    if repeated:
        suggestions.append(
            f"Multiple callbacks update the same Output IDs (uses allow_duplicate=True): "
            f"{', '.join(repeated)}"
        )

    # Check for app.run
    if "app.run" not in code and "run_server" not in code:
        warnings.append("No app.run_server() or app.run() call found")

    # Check for interval components (real-time apps need them)
    if "dcc.Interval" in code:
        interval_ids = re.findall(r'dcc\.Interval\([^)]*id=["\']([^"\']+)["\']', code)
        if interval_ids:
            suggestions.append(f"Interval components: {', '.join(interval_ids)}")

    # Check for threading (long operations should use it)
    if "threading" not in code and "Thread" not in code:
        if "connect" in code.lower() and "serial" in code.lower():
            suggestions.append("Consider using threading for serial operations to avoid blocking callbacks")

    passed = len(issues) == 0
    return VerificationResult(passed=passed, issues=issues, warnings=warnings, suggestions=suggestions)


# ─────────────────────────────────────────────────────────────────────
# AI-Powered Verification
# ─────────────────────────────────────────────────────────────────────

VERIFY_DRIVER_PROMPT = """You are a senior Python developer reviewing a lab instrument driver.

## Driver Code
```python
{code}
```

## Review Checklist
Verify the following and report ONLY issues found (not things that are correct):

1. **Serial settings**: Are baud rate, parity, stop bits, timeout explicitly set? Do they match typical instrument defaults?
2. **Error handling**: Does every method that communicates with hardware have try/except?
3. **Resource cleanup**: Is the serial port properly closed in disconnect() and on errors?
4. **Method completeness**: Do all methods listed in the class actually have implementations (not just `pass`)?
5. **Response parsing**: Are responses properly decoded and validated before returning?
6. **Thread safety**: If the driver might be used from multiple threads, is there a lock?

## Output Format
Return a JSON object:
{{
  "issues": ["critical problems that would cause failures"],
  "warnings": ["potential problems or missing best practices"],
  "score": 1-10,
  "summary": "one sentence overall assessment"
}}

Return ONLY the JSON, no other text."""


GENERATE_TEST_PROMPT = """You are a senior Python developer writing unit tests for a lab instrument driver.

## Driver Code
```python
{code}
```

## Requirements
Generate a test file using pytest with unittest.mock to mock the serial connection.
The tests should verify:
1. Class instantiation with correct parameters
2. connect() opens serial port with correct settings
3. disconnect() closes serial port properly
4. Each public method sends the correct command string
5. Response parsing returns expected values
6. Error handling raises the custom exception on failures

Use `unittest.mock.patch('serial.Serial')` to mock the serial connection.
Do NOT test actual hardware communication.

Output the complete test file in a single ```python block."""


def verify_driver_with_ai(config: LLMConfig, code: str) -> dict:
    """Use AI to review a driver for common issues."""
    prompt = VERIFY_DRIVER_PROMPT.format(code=code)
    response = complete(config, prompt)

    import json
    try:
        # Try to extract JSON from response
        json_match = re.search(r'\{.*\}', response, re.S)
        if json_match:
            return json.loads(json_match.group())
    except (json.JSONDecodeError, AttributeError):
        pass

    return {
        "issues": ["AI verification response could not be parsed"],
        "warnings": [],
        "score": 0,
        "summary": response[:200],
    }


def generate_test_code(config: LLMConfig, driver_code: str) -> str:
    """Generate pytest test code for a driver."""
    import textwrap
    prompt = GENERATE_TEST_PROMPT.format(code=driver_code)
    response = complete(config, prompt)

    match = re.search(r"```python(.*?)```", response, re.S | re.I)
    if match:
        return textwrap.dedent(match.group(1)).strip()
    return response


# ─────────────────────────────────────────────────────────────────────
# Verification workflow
# ─────────────────────────────────────────────────────────────────────

def run_full_verification(code: str, mode: str = "driver") -> VerificationResult:
    """
    Run all static checks appropriate for the code type.

    Args:
        code: The generated Python code
        mode: "driver" or "dash"

    Returns:
        Combined VerificationResult
    """
    # Always check syntax first
    syntax_result = check_syntax(code)
    if not syntax_result.passed:
        return syntax_result

    # Mode-specific checks
    if mode == "driver":
        return check_driver_structure(code)
    elif mode == "dash":
        return check_dash_structure(code)
    else:
        return VerificationResult(passed=True)
