from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import socket
import subprocess
import sys

import pytest
from pytest import fixture as pytest_fixture

from _parameter_contract import (
    ParameterContractError,
    collected_function_identity,
    validate_check_parameters,
)


@pytest.fixture(name="pk030_module_local_value", params=("pytest-fixture-injected",))
def _pk030_module_local_value(request) -> str:
    return request.param


@pytest_fixture(name="pk030_module_local_async_value")
async def _pk030_module_local_async_value() -> str:
    await asyncio.sleep(0)
    return "pytest-async-fixture-awaited"


def _isolated_pytest_environment(repo_root: Path) -> dict[str, str]:
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    tests_root = repo_root / "server" / "tests"
    old_python_path = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = (
        os.fspath(tests_root)
        if not old_python_path
        else os.fspath(tests_root) + os.pathsep + old_python_path
    )
    return environment


def _write_contract_collection_project(root: Path, source: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    synthetic_test = root / "test_contract.py"
    synthetic_test.write_text(source, encoding="utf-8")
    (root / "pytest.ini").write_text(
        "[pytest]\npython_functions = test_* check_*\n",
        encoding="utf-8",
    )
    (root / "conftest.py").write_text(
        "\n".join(
            (
                "from pathlib import Path",
                "import pytest",
                "from _parameter_contract import (",
                "    ParameterContractError,",
                "    validate_check_parameters,",
                ")",
                "",
                "source_path = Path(__file__).with_name('test_contract.py')",
                "try:",
                "    validate_check_parameters(",
                "        source_path.read_text(encoding='utf-8'),",
                "        filename=source_path.name,",
                "        fixture_names={'tmp_path'},",
                "    )",
                "except ParameterContractError as exc:",
                "    raise pytest.UsageError(",
                "        f'parameter contract failed before collection: {exc}'",
                "    ) from exc",
            )
        ),
        encoding="utf-8",
    )
    return synthetic_test


def _run_child_pytest(
    root: Path,
    repo_root: Path,
    *arguments: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            *arguments,
        ],
        cwd=root,
        env=_isolated_pytest_environment(repo_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        check=False,
    )


async def check_async_test_is_actually_awaited(tmp_path: Path) -> None:
    marker = tmp_path / "async-executed.txt"
    await asyncio.sleep(0)
    marker.write_text("awaited", encoding="utf-8")
    assert marker.read_text(encoding="utf-8") == "awaited"


def check_external_network_is_blocked(external_network_error) -> None:
    try:
        socket.getaddrinfo("example.com", 443)
    except external_network_error:
        pass
    else:
        raise AssertionError("external DNS reached the real resolver")
    try:
        socket.create_connection(("127.0.0.1", 8000))
    except external_network_error:
        pass
    else:
        raise AssertionError("a real loopback service was reachable")


def check_protected_paths_fail_before_io(
    repo_root: Path,
    protected_path_error,
) -> None:
    for path, operation in (
        (repo_root / "server" / ".env", "read"),
        (repo_root / "server" / "data" / "pytest-tripwire.json", "write"),
        (repo_root / "server" / "systems" / "data" / "pytest-tripwire.json", "stat"),
        (repo_root / ".venv" / "Scripts" / "python.exe", "stat"),
        (repo_root / "vendor" / "pytest-tripwire.txt", "read"),
    ):
        try:
            if operation == "read":
                path.read_text(encoding="utf-8")
            elif operation == "write":
                path.write_text("must not be written", encoding="utf-8")
            else:
                path.stat()
        except protected_path_error:
            pass
        else:
            raise AssertionError(f"protected {operation} was not rejected")


def check_fixed_clock_fixture(fixed_utc_now) -> None:
    assert fixed_utc_now.isoformat() == "2026-07-22T08:00:00+00:00"


def check_manual_main_parameter_is_rejected_before_collection(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import conftest as quality_conftest

    source = "\n".join(
        (
            "def check_manual_payload(manual_payload):",
            "    assert manual_payload == 'legacy-main-value'",
            "",
            "def check_keyword_only(*, manual_keyword):",
            "    assert manual_keyword",
            "",
            "def main():",
            "    check_manual_payload('legacy-main-value')",
        )
    )
    with pytest.raises(ParameterContractError, match=r"manual_payload") as caught:
        validate_check_parameters(
            source,
            filename="test_synthetic_legacy_main.py",
            fixture_names=(),
        )
    assert "manual_keyword" in str(caught.value)
    synthetic_test = tmp_path / "test_synthetic_legacy_main.py"
    synthetic_test.write_text(source, encoding="utf-8")
    monkeypatch.setattr(
        quality_conftest,
        "DEFAULT_OFFLINE",
        frozenset({synthetic_test.name}),
    )
    monkeypatch.setattr(quality_conftest, "TESTS_ROOT", tmp_path)
    with pytest.raises(pytest.UsageError, match=r"before collection.*manual_payload"):
        quality_conftest._validate_default_check_parameters()


def check_positional_only_fixture_is_rejected_during_collection(
    repo_root: Path,
    tmp_path: Path,
) -> None:
    source = "\n".join(
        (
            "def check_posonly(tmp_path, /):",
            "    assert tmp_path",
        )
    )
    with pytest.raises(ParameterContractError, match=r"positional-only.*tmp_path"):
        validate_check_parameters(
            source,
            filename="test_positional_only.py",
            fixture_names={"tmp_path"},
        )
    parametrized_positional_only = "\n".join(
        (
            "import pytest",
            "@pytest.mark.parametrize('case', [1])",
            "def check_posonly_case(case, /):",
            "    assert case",
        )
    )
    with pytest.raises(ParameterContractError, match=r"positional-only.*case"):
        validate_check_parameters(
            parametrized_positional_only,
            filename="test_parametrized_positional_only.py",
            fixture_names=(),
        )

    synthetic_test = _write_contract_collection_project(
        tmp_path / "positional-only",
        source,
    )
    completed = _run_child_pytest(
        synthetic_test.parent,
        repo_root,
        "--collect-only",
        os.fspath(synthetic_test),
    )
    assert completed.returncode != 0
    assert "failed before collection" in completed.stdout
    assert "positional-only" in completed.stdout
    assert "TypeError" not in completed.stdout
    assert "fixture 'tmp_path' not found" not in completed.stdout


def check_parameter_contract_static_fixture_boundaries() -> None:
    local_fixtures = "\n".join(
        (
            "import pytest",
            "",
            "@pytest.fixture(name='local_value', params=('ok',))",
            "def _local_value(request):",
            "    return request.param",
            "",
            "@pytest.fixture",
            "async def async_local_value():",
            "    return 'async-ok'",
            "",
            "def check_local(local_value, *, tmp_path):",
            "    assert local_value and tmp_path",
            "",
            "async def check_async_local(async_local_value):",
            "    assert async_local_value",
        )
    )
    contracts = validate_check_parameters(
        local_fixtures,
        filename="test_local_fixtures.py",
        fixture_names=(),
    )
    assert [contract.category for contract in contracts] == [
        "fixture_or_parametrize",
        "fixture_or_parametrize",
    ]

    explicit_aliases = "\n".join(
        (
            "import pytest as pt",
            "from pytest import fixture as pf",
            "",
            "@pt.fixture(name='first')",
            "def _first():",
            "    return 1",
            "",
            "@pf",
            "def second():",
            "    return 2",
            "",
            "@pt.mark.parametrize('case', [3])",
            "def check_aliases(first, second, case):",
            "    assert first + second == case",
        )
    )
    alias_contract = validate_check_parameters(
        explicit_aliases,
        filename="test_explicit_aliases.py",
        fixture_names=(),
    )[0]
    assert alias_contract.fixture_parameters == ("first", "second")
    assert alias_contract.parametrized_parameters == ("case",)

    invalid_sources = {
        "duplicate fixture": (
            "\n".join(
                (
                    "import pytest",
                    "@pytest.fixture(name='same')",
                    "def first(): pass",
                    "@pytest.fixture(name='same')",
                    "def second(): pass",
                    "def check_same(same): pass",
                )
            ),
            r"duplicate module fixture name same",
        ),
        "non-literal fixture": (
            "\n".join(
                (
                    "import pytest",
                    "fixture_name = 'dynamic'",
                    "@pytest.fixture(name=fixture_name)",
                    "def value(): pass",
                    "def check_value(dynamic): pass",
                )
            ),
            r"fixture name must be a non-empty literal string",
        ),
        "unknown decorator": (
            "\n".join(
                (
                    "def fixture(function): return function",
                    "@fixture",
                    "def local_value(): return 1",
                    "def check_local(local_value): pass",
                )
            ),
            r"not fixtures or literal parametrize arguments: local_value",
        ),
        "redefined pytest alias": (
            "\n".join(
                (
                    "import pytest as pt",
                    "pt = object()",
                    "@pt.fixture",
                    "def local_value(): return 1",
                    "def check_local(local_value): pass",
                )
            ),
            r"not fixtures or literal parametrize arguments: local_value",
        ),
        "unsupported positional decorator": (
            "\n".join(
                (
                    "import pytest",
                    "@pytest.fixture('name')",
                    "def local_value(): return 1",
                    "def check_local(local_value): pass",
                )
            ),
            r"fixture decorator positional arguments are not statically supported",
        ),
        "unknown keyword-only": (
            "def check_unknown(*, missing_value): pass",
            r"not fixtures or literal parametrize arguments: missing_value",
        ),
    }
    for label, (invalid_source, error_pattern) in invalid_sources.items():
        with pytest.raises(ParameterContractError, match=error_pattern):
            validate_check_parameters(
                invalid_source,
                filename=f"test_{label.replace(' ', '_')}.py",
                fixture_names=(),
            )


def check_module_scope_pytest_alias_rebinding_fails_closed(
    repo_root: Path,
    tmp_path: Path,
) -> None:
    binding_cases = {
        "for": "for pt in []:\n    pass",
        "if_assign": "if True:\n    pt = object()",
        "try_assign": "try:\n    pt = object()\nexcept Exception:\n    pass",
        "except_name": "try:\n    pass\nexcept Exception as pt:\n    pass",
        "with_as": "with context as pt:\n    pass",
        "walrus": "if (pt := object()):\n    pass",
        "delete": "del pt",
        "tuple_unpack": "pt, other = values",
        "starred_unpack": "other, *pt = values",
        "async_for": "async for pt in values:\n    pass",
        "async_with": "async with context as pt:\n    pass",
        "match_pattern": "match value:\n    case {'value': pt}:\n        pass",
        "conditional_import": "if False:\n    import other_module as pt",
        "default_walrus": "def helper(value=(pt := object())):\n    pass",
    }
    required_subprocess_cases = {
        "for",
        "if_assign",
        "try_assign",
        "except_name",
        "with_as",
        "walrus",
        "delete",
    }
    for label, binding in binding_cases.items():
        source = "\n".join(
            (
                "import pytest as pt",
                binding,
                "@pt.fixture",
                "def local_value():",
                "    return 'unsafe'",
                "def check_local(local_value):",
                "    assert local_value",
            )
        )
        with pytest.raises(ParameterContractError, match=r"local_value"):
            validate_check_parameters(
                source,
                filename=f"test_alias_rebind_{label}.py",
                fixture_names=(),
            )
        if label not in required_subprocess_cases:
            continue
        synthetic_test = _write_contract_collection_project(
            tmp_path / label,
            source,
        )
        completed = _run_child_pytest(
            synthetic_test.parent,
            repo_root,
            "--collect-only",
            os.fspath(synthetic_test),
        )
        assert completed.returncode != 0
        assert "failed before collection" in completed.stdout
        assert "local_value" in completed.stdout
        assert "TypeError" not in completed.stdout

    nested_scopes_are_safe = "\n".join(
        (
            "import pytest as pt",
            "def helper():",
            "    pt = object()",
            "class Nested:",
            "    pt = object()",
            "values = [pt for pt in ()]",
            "@pt.fixture",
            "def local_value():",
            "    return 'safe'",
            "def check_local(local_value):",
            "    assert local_value",
        )
    )
    contract = validate_check_parameters(
        nested_scopes_are_safe,
        filename="test_nested_alias_scope.py",
        fixture_names=(),
    )[0]
    assert contract.fixture_parameters == ("local_value",)


def check_parameterized_collection_uses_original_function_identity(
    repo_root: Path,
    tmp_path: Path,
) -> None:
    assert collected_function_identity(
        "module-one",
        "check_shared",
        module_level=True,
        skipped=False,
    ) == ("module-one", "check_shared")
    assert (
        collected_function_identity(
            "module-one",
            "check_shared[param-id]",
            module_level=True,
            skipped=False,
        )
        is None
    )
    assert (
        collected_function_identity(
            "module-one",
            "check_shared",
            module_level=False,
            skipped=False,
        )
        is None
    )
    assert (
        collected_function_identity(
            "module-one",
            "check_shared",
            module_level=True,
            skipped=True,
        )
        is None
    )
    assert collected_function_identity(
        "module-one",
        "check_shared_prefix",
        module_level=True,
        skipped=False,
    ) != ("module-one", "check_shared")

    project = tmp_path / "parameterized-collection"
    project.mkdir()
    (project / "pytest.ini").write_text(
        "[pytest]\npython_functions = test_* check_*\n",
        encoding="utf-8",
    )
    (project / "test_one.py").write_text(
        "\n".join(
            (
                "import pytest",
                "",
                "@pytest.mark.parametrize(",
                "    'left,right',",
                "    [",
                "        pytest.param(1, 2, id='left[bracket]::slash/value'),",
                "        pytest.param(2, 3, id='right ] [ :: value'),",
                "    ],",
                ")",
                "def check_shared(left, right):",
                "    assert right == left + 1",
                "",
                "class TestShadow:",
                "    def check_shared(self):",
                "        assert True",
            )
        ),
        encoding="utf-8",
    )
    (project / "test_two.py").write_text(
        "def check_shared():\n    assert True\n",
        encoding="utf-8",
    )
    (project / "conftest.py").write_text(
        "\n".join(
            (
                "import os",
                "from pathlib import Path",
                "import pytest",
                "from _parameter_contract import collected_function_identity",
                "",
                "def module_key(value):",
                "    return os.path.normcase(str(Path(value).resolve()))",
                "",
                "def pytest_collection_finish(session):",
                "    identities = []",
                "    for item in session.items:",
                "        skipped = any(",
                "            next(item.iter_markers(name=name), None) is not None",
                "            for name in ('skip', 'skipif')",
                "        )",
                "        identity = collected_function_identity(",
                "            module_key(item.path),",
                "            getattr(item, 'originalname', None),",
                "            module_level=(",
                "                isinstance(item, pytest.Function)",
                "                and isinstance(item.parent, pytest.Module)",
                "            ),",
                "            skipped=skipped,",
                "        )",
                "        if identity is not None:",
                "            identities.append(identity)",
                "    one = (module_key(Path(__file__).with_name('test_one.py')), 'check_shared')",
                "    two = (module_key(Path(__file__).with_name('test_two.py')), 'check_shared')",
                "    if identities.count(one) != 2 or identities.count(two) != 1:",
                "        raise pytest.UsageError(f'base identity mismatch: {identities!r}')",
                "    if collected_function_identity(",
                "        one[0], 'check_shared[fake]', module_level=True, skipped=False",
                "    ) is not None:",
                "        raise pytest.UsageError('forged bracket identity was accepted')",
                "    prefix = collected_function_identity(",
                "        one[0], 'check_shared_prefix', module_level=True, skipped=False",
                "    )",
                "    if prefix == one:",
                "        raise pytest.UsageError('same-prefix identity was accepted')",
            )
        ),
        encoding="utf-8",
    )

    collect = _run_child_pytest(project, repo_root, "--collect-only", ".")
    assert collect.returncode == 0, collect.stdout
    assert "4 tests collected" in collect.stdout
    run = _run_child_pytest(project, repo_root, ".")
    assert run.returncode == 0, run.stdout
    assert "4 passed" in run.stdout
    assert "skipped" not in run.stdout


def check_fixture_parameter_is_injected(pk030_module_local_value) -> None:
    assert pk030_module_local_value == "pytest-fixture-injected"


async def check_async_fixture_parameter_is_awaited(
    pk030_module_local_async_value,
) -> None:
    await asyncio.sleep(0)
    assert pk030_module_local_async_value == "pytest-async-fixture-awaited"


def check_pytest_reports_later_items_after_a_failure(tmp_path: Path) -> None:
    fixture = tmp_path / "test_failure_continuation.py"
    fixture.write_text(
        "\n".join(
            (
                "def test_first_fails():",
                "    assert False, 'intentional sentinel failure'",
                "",
                "def test_second_still_runs():",
                "    assert True",
            )
        ),
        encoding="utf-8",
    )
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            os.fspath(fixture),
        ],
        cwd=tmp_path,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert completed.returncode == 1
    assert "1 failed" in completed.stdout
    assert "1 passed" in completed.stdout


def check_inventory_is_machine_readable(repo_root: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-B",
            os.fspath(repo_root / "scripts" / "check_python_test_inventory.py"),
            "--json",
        ],
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["test_files"] == (
        payload["default_files"] + payload["isolated_files"]
    )
    assert payload["isolated_files"] == 14
    assert payload["top_level_check_functions"] >= 167
    assert payload["default_check_parameter_unsatisfied"] == 0
    assert payload["default_check_parameter_legacy_wrapper"] == 0
    assert payload["default_check_parameter_total"] == (
        payload["default_check_parameter_zero"]
        + payload["default_check_parameter_fixture_or_parametrize"]
        + payload["default_check_parameter_legacy_wrapper"]
    )
    assert payload["legacy_entrypoints_zero_parameter"] == payload["legacy_entrypoints"]
