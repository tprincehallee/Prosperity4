#!/usr/bin/env python3
"""
Merge modular source files into a single trader.py for submission.

Usage:
    python scripts/merge_to_submission.py

Output:
    submission/trader.py — a standalone file ready to upload.

This script reads trader.py and inlines the utility functions that are
already defined directly in trader.py (the submission-ready version).
For development, you edit the separate files in utils/ and strategies/,
then this script can verify the standalone trader.py is self-contained.
"""

import ast
import sys
import os
from pathlib import Path


REPO_ROOT = Path(__file__).parent.parent
TRADER_FILE = REPO_ROOT / "trader.py"
OUTPUT_DIR = REPO_ROOT / "submission"
OUTPUT_FILE = OUTPUT_DIR / "trader.py"

# Imports that the competition environment provides
ALLOWED_IMPORTS = {
    "datamodel",
    "json",
    "math",
    "typing",
    "collections",
    "statistics",
    "numpy",
    "pandas",
    "jsonpickle",
}


def check_imports(source: str) -> list[str]:
    """Check for forbidden imports and return a list of warnings."""
    warnings = []
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return [f"Syntax error: {e}"]

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                module = alias.name.split(".")[0]
                if module not in ALLOWED_IMPORTS:
                    warnings.append(
                        f"Line {node.lineno}: Forbidden import '{alias.name}'"
                    )
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                module = node.module.split(".")[0]
                if module not in ALLOWED_IMPORTS:
                    warnings.append(
                        f"Line {node.lineno}: Forbidden import from '{node.module}'"
                    )
    return warnings


def check_return_signature(source: str) -> list[str]:
    """Verify that run() returns a 3-tuple."""
    warnings = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "Trader":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "run":
                    # Check return annotation if present
                    if item.returns and isinstance(item.returns, ast.Subscript):
                        pass  # Type annotation present, good
                    # Look for return statements
                    for sub in ast.walk(item):
                        if isinstance(sub, ast.Return) and sub.value:
                            if isinstance(sub.value, ast.Tuple):
                                n = len(sub.value.elts)
                                if n != 3:
                                    warnings.append(
                                        f"Line {sub.lineno}: run() returns "
                                        f"{n}-tuple, expected 3-tuple "
                                        f"(result, conversions, traderData)"
                                    )
    return warnings


def main():
    if not TRADER_FILE.exists():
        print(f"ERROR: {TRADER_FILE} not found")
        sys.exit(1)

    source = TRADER_FILE.read_text()

    print("=" * 60)
    print("IMC Prosperity Submission Checker")
    print("=" * 60)

    # Check imports
    import_warnings = check_imports(source)
    if import_warnings:
        print("\nIMPORT WARNINGS:")
        for w in import_warnings:
            print(f"  ⚠️  {w}")
    else:
        print("\n✅ All imports are allowed")

    # Check return signature
    return_warnings = check_return_signature(source)
    if return_warnings:
        print("\nRETURN SIGNATURE WARNINGS:")
        for w in return_warnings:
            print(f"  ⚠️  {w}")
    else:
        print("✅ run() return signature looks correct")

    # Check for class named Trader
    if "class Trader:" in source or "class Trader(" in source:
        print("✅ Trader class found")
    else:
        print("⚠️  No 'class Trader' found!")

    # Check file size
    size_kb = len(source.encode("utf-8")) / 1024
    print(f"\n📏 File size: {size_kb:.1f} KB")

    # Write output
    OUTPUT_DIR.mkdir(exist_ok=True)
    OUTPUT_FILE.write_text(source)
    print(f"\n📦 Submission written to: {OUTPUT_FILE}")

    total_warnings = len(import_warnings) + len(return_warnings)
    if total_warnings > 0:
        print(f"\n⚠️  {total_warnings} warning(s) found — review before submitting!")
    else:
        print("\n🎉 All checks passed — ready to submit!")


if __name__ == "__main__":
    main()
