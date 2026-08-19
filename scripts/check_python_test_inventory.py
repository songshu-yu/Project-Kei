"""Validate and report Project Kei's classified Python test inventory."""

from __future__ import annotations

import argparse
import ast
from collections import Counter
import json
from pathlib import Path
import sys
from typing import Any, Sequence

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 dev lock provides tomli.
    import tomli as tomllib


REPO_ROOT = Path(__file__).resolve().parents[1]
TESTS_ROOT = REPO_ROOT / "server" / "tests"
INVENTORY_PATH = TESTS_ROOT / "python-test-inventory.json"
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "windows-install.yml"

tests_import_path = str(TESTS_ROOT)
if tests_import_path not in sys.path:
    sys.path.insert(0, tests_import_path)

from _parameter_contract import (  # noqa: E402
    ParameterContractError,
    fixture_names_from_source,
    required_parameters_for_function,
    validate_check_parameters,
)


class InventoryError(RuntimeError):
    pass


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _classified(inventory: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in inventory["default_offline"]:
        if path in result:
            raise InventoryError(f"duplicate classification: {path}")
        result[path] = "default_offline"
    for category in ("controlled_integration", "manual_diagnostic"):
        for entry in inventory[category]:
            path = entry.get("path", "")
            reason = entry.get("reason", "").strip()
            if not path or not reason:
                raise InventoryError(f"{category} entry requires path and reason")
            if path in result:
                raise InventoryError(f"duplicate classification: {path}")
            result[path] = category
    return result


def _definitions(path: Path) -> dict[str, Any]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    functions: dict[str, bool] = {}
    class_tests = 0
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions[node.name] = isinstance(node, ast.AsyncFunctionDef)
        elif isinstance(node, ast.ClassDef):
            class_tests += sum(
                isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                and child.name.startswith("test_")
                for child in node.body
            )
    return {"functions": functions, "class_tests": class_tests}


def audit() -> tuple[dict[str, Any], list[dict[str, str]]]:
    inventory = _load_json(INVENTORY_PATH)
    if inventory.get("schema_version") != 1:
        raise InventoryError("unsupported inventory schema")
    classified = _classified(inventory)
    actual_files = sorted(path.name for path in TESTS_ROOT.glob("test_*.py"))
    if set(classified) != set(actual_files):
        missing = sorted(set(actual_files) - set(classified))
        stale = sorted(set(classified) - set(actual_files))
        raise InventoryError(f"inventory mismatch: missing={missing} stale={stale}")

    legacy = inventory["legacy_entrypoints"]
    counts: Counter[str] = Counter()
    counts.update(
        {
            "default_check_parameter_total": 0,
            "default_check_parameter_zero": 0,
            "default_check_parameter_fixture_or_parametrize": 0,
            "default_check_parameter_legacy_wrapper": 0,
            "default_check_parameter_unsatisfied": 0,
            "legacy_entrypoints_zero_parameter": 0,
        }
    )
    for filename in actual_files:
        definitions = _definitions(TESTS_ROOT / filename)
        functions = definitions["functions"]
        counts["top_level_check_functions"] += sum(
            name.startswith("check_") for name in functions
        )
        counts["async_check_functions"] += sum(
            name.startswith("check_") and is_async
            for name, is_async in functions.items()
        )
        counts["top_level_test_functions"] += sum(
            name.startswith("test_") for name in functions
        )
        counts["async_test_functions"] += sum(
            name.startswith("test_") and is_async
            for name, is_async in functions.items()
        )
        counts["class_test_methods"] += definitions["class_tests"]
        if filename in legacy and legacy[filename] not in functions:
            raise InventoryError(
                f"legacy entrypoint missing: {filename}:{legacy[filename]}"
            )

    default_files = set(inventory["default_offline"])
    if not set(legacy).issubset(default_files):
        raise InventoryError("legacy entrypoints must belong to default_offline")
    try:
        fixture_names = fixture_names_from_source(
            (TESTS_ROOT / "conftest.py").read_text(encoding="utf-8"),
            filename="conftest.py",
        )
    except ParameterContractError as exc:
        raise InventoryError(f"fixture contract is invalid: {exc}") from exc
    required_parameter_names: set[str] = set()
    for filename in sorted(default_files):
        test_path = TESTS_ROOT / filename
        definitions = _definitions(test_path)
        functions = definitions["functions"]
        directly_collectable = any(
            name.startswith(("check_", "test_")) for name in functions
        ) or definitions["class_tests"]
        if not directly_collectable and filename not in legacy:
            raise InventoryError(
                f"default file has no pytest item or legacy entrypoint: {filename}"
            )
        source = test_path.read_text(encoding="utf-8-sig")
        try:
            contracts = validate_check_parameters(
                source,
                filename=filename,
                fixture_names=fixture_names,
            )
        except ParameterContractError as exc:
            counts["default_check_parameter_unsatisfied"] += 1
            raise InventoryError(f"default check parameter contract failed: {exc}") from exc
        for contract in contracts:
            counts["default_check_parameter_total"] += 1
            required_parameter_names.update(contract.required)
            if contract.category == "zero_parameter":
                counts["default_check_parameter_zero"] += 1
            elif contract.category == "fixture_or_parametrize":
                counts["default_check_parameter_fixture_or_parametrize"] += 1
            else:
                raise InventoryError(
                    f"unexpected check parameter category: {filename}:{contract.name}"
                )
        if filename in legacy:
            try:
                required = required_parameters_for_function(
                    source,
                    filename=filename,
                    function_name=legacy[filename],
                )
            except ParameterContractError as exc:
                raise InventoryError(f"legacy wrapper contract failed: {exc}") from exc
            if required:
                raise InventoryError(
                    f"legacy wrapper calls without arguments but {filename}:"
                    f"{legacy[filename]} requires {', '.join(required)}"
                )
            counts["legacy_entrypoints_zero_parameter"] += 1

    pyproject = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
    pytest_config = pyproject["tool"]["pytest"]["ini_options"]
    if pytest_config.get("testpaths") != ["server/tests"]:
        raise InventoryError("pytest testpaths must be the complete server/tests suite")
    if set(pytest_config.get("python_functions", ())) != {"test_*", "check_*"}:
        raise InventoryError("pytest must collect test_* and check_* functions")
    if pytest_config.get("asyncio_mode") != "auto":
        raise InventoryError("pytest asyncio_mode must execute async checks automatically")

    dev_input = (REPO_ROOT / "requirements" / "dev.in").read_text(encoding="utf-8")
    dev_lock = (REPO_ROOT / "requirements" / "dev-win.lock.txt").read_text(
        encoding="utf-8"
    )
    for dependency in ("pytest==", "pytest-asyncio==", "ruff=="):
        if dependency not in dev_input or dependency not in dev_lock:
            raise InventoryError(f"dev dependency missing from input/lock: {dependency}")

    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    for required in (
        "python-version: [\"3.10\", \"3.11\", \"3.12\", \"3.13\"]",
        "..\\scripts\\check_python_test_inventory.py",
        "-m pytest tests",
        "-m ruff check tests ..\\scripts\\check_python_test_inventory.py",
    ):
        if required not in workflow:
            raise InventoryError(f"Windows workflow missing quality gate: {required}")
    for category in ("controlled_integration", "manual_diagnostic"):
        for entry in inventory[category]:
            if entry["path"] in workflow:
                raise InventoryError(
                    f"isolated diagnostic is hard-coded into CI: {entry['path']}"
                )

    isolated = [
        {"category": category, "path": entry["path"], "reason": entry["reason"]}
        for category in ("controlled_integration", "manual_diagnostic")
        for entry in inventory[category]
    ]
    summary = {
        "test_files": len(actual_files),
        "default_files": len(inventory["default_offline"]),
        "isolated_files": len(isolated),
        "controlled_integration_files": len(inventory["controlled_integration"]),
        "manual_diagnostic_files": len(inventory["manual_diagnostic"]),
        "legacy_entrypoints": len(legacy),
        "default_check_required_parameter_names": sorted(required_parameter_names),
        **counts,
    }
    return summary, isolated


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        summary, isolated = audit()
    except (InventoryError, OSError, ValueError, KeyError) as exc:
        print(f"python-test-inventory: error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(summary, sort_keys=True))
        return 0
    print(
        "python-test-inventory: "
        + " ".join(f"{key}={value}" for key, value in summary.items())
    )
    for entry in isolated:
        print(
            f"isolated: {entry['category']} {entry['path']} reason={entry['reason']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
