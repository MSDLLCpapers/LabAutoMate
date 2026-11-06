"""
driver_loader.py
Dynamic discovery and source-reading for PyLabDrivers.

Locates the installed pylabdrivers package (or falls back to a sibling
repo clone) and provides:
  - get_driver_catalog()  -> dict mapping filename -> one-line description
  - read_driver_source()  -> full source text of a single driver file
  - get_drivers_path()    -> resolved path to the pylabdrivers directory
"""

import os
import re
import ast
import importlib.util
from pathlib import Path
from typing import Dict, Optional


def get_drivers_path() -> Path:
    """
    Resolve the path to the pylabdrivers package source directory.

    Priority:
      1. Installed package (pip install / pip install -e)
      2. Sibling repo clone: ../PyLabDrivers/pylabdrivers/
      3. Environment variable PYLABDRIVERS_PATH
    """
    # 1. Try to find installed package
    spec = importlib.util.find_spec("pylabdrivers")
    if spec and spec.submodule_search_locations:
        pkg_path = Path(spec.submodule_search_locations[0])
        if pkg_path.is_dir():
            return pkg_path

    # 2. Try sibling repo clone (common dev layout)
    # From labautomate/driver_loader.py -> parent.parent = dre-LabAutoMate/ -> parent = LabAutoMate Paper/
    repo_root = Path(__file__).resolve().parent.parent
    sibling = repo_root.parent / "PyLabDrivers" / "pylabdrivers"
    if sibling.is_dir():
        return sibling

    # 3. Environment variable override
    env_path = os.environ.get("PYLABDRIVERS_PATH")
    if env_path:
        p = Path(env_path)
        if p.is_dir():
            return p

    raise FileNotFoundError(
        "Cannot locate pylabdrivers package. Install it with:\n"
        "  pip install -e ../PyLabDrivers\n"
        "Or set the PYLABDRIVERS_PATH environment variable."
    )


def _extract_docstring(filepath: Path) -> str:
    """Extract the module-level docstring from a Python file."""
    try:
        source = filepath.read_text(encoding="utf-8")
        tree = ast.parse(source)
        docstring = ast.get_docstring(tree)
        if docstring:
            first_line = docstring.strip().split("\n")[0]
            return first_line
    except (SyntaxError, UnicodeDecodeError):
        pass
    return ""


def _extract_class_summary(filepath: Path) -> str:
    """Extract the main driver class name and its docstring first line."""
    try:
        source = filepath.read_text(encoding="utf-8")
        tree = ast.parse(source)
        classes = []
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef):
                classes.append(node)
        # Prefer non-Error classes (the actual driver class)
        driver_classes = [c for c in classes if "Error" not in c.name]
        target = driver_classes[0] if driver_classes else (classes[0] if classes else None)
        if target:
            cls_doc = ast.get_docstring(target)
            if cls_doc:
                return f"{target.name}: {cls_doc.strip().split(chr(10))[0]}"
            return f"{target.name} driver"
    except (SyntaxError, UnicodeDecodeError):
        pass
    return ""


def get_driver_catalog(drivers_path: Optional[Path] = None) -> Dict[str, str]:
    """
    Build a catalog of all driver files and their descriptions.

    Returns a dict: {"alicatmfc.py": "AlicatMFC: Control Alicat mass-flow controllers", ...}
    """
    if drivers_path is None:
        drivers_path = get_drivers_path()

    catalog = {}
    for py_file in sorted(drivers_path.glob("*.py")):
        if py_file.name.startswith("_"):
            continue

        description = _extract_docstring(py_file)
        if not description:
            description = _extract_class_summary(py_file)
        if not description:
            description = py_file.stem.replace("_", " ").title() + " driver"

        catalog[py_file.name] = description

    return catalog


def read_driver_source(filename: str, drivers_path: Optional[Path] = None) -> str:
    """
    Read the full source code of a driver file.

    Args:
        filename: e.g. "alicatmfc.py"
        drivers_path: override path (uses auto-detected if None)

    Returns:
        Full source text of the driver file.

    Raises:
        FileNotFoundError: if the driver file doesn't exist.
    """
    if drivers_path is None:
        drivers_path = get_drivers_path()

    filepath = drivers_path / filename
    if not filepath.exists():
        raise FileNotFoundError(f"Driver file not found: {filepath}")

    return filepath.read_text(encoding="utf-8")


def get_driver_methods(filename: str, drivers_path: Optional[Path] = None) -> Dict[str, str]:
    """
    Extract public methods and their docstrings from a driver file.

    Returns: {"method_name": "first line of docstring", ...}
    """
    if drivers_path is None:
        drivers_path = get_drivers_path()

    filepath = drivers_path / filename
    source = filepath.read_text(encoding="utf-8")
    tree = ast.parse(source)

    methods = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and not item.name.startswith("_"):
                    doc = ast.get_docstring(item) or ""
                    first_line = doc.strip().split("\n")[0] if doc else ""
                    methods[item.name] = first_line
    return methods
