from __future__ import annotations

import ast
import asyncio
import builtins
from datetime import datetime, timezone
import inspect
import io
import ipaddress
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
from typing import Any, Callable

import pytest


TESTS_ROOT = Path(__file__).resolve().parent
SERVER_ROOT = TESTS_ROOT.parent
REPO_ROOT = SERVER_ROOT.parent
INVENTORY_PATH = TESTS_ROOT / "python-test-inventory.json"

for import_root in (TESTS_ROOT, SERVER_ROOT):
    import_path = os.fspath(import_root)
    if import_path not in sys.path:
        sys.path.insert(0, import_path)

from _parameter_contract import (  # noqa: E402
    ParameterContractError,
    collected_function_identity,
    fixture_names_from_source,
    validate_check_parameters,
)


def _load_inventory() -> dict[str, Any]:
    payload = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise RuntimeError("unsupported Python test inventory schema")
    return payload


INVENTORY = _load_inventory()
DEFAULT_OFFLINE = frozenset(INVENTORY["default_offline"])
EXCLUDED = {
    entry["path"]
    for category in ("controlled_integration", "manual_diagnostic")
    for entry in INVENTORY[category]
}
LEGACY_ENTRYPOINTS = dict(INVENTORY["legacy_entrypoints"])
collect_ignore = sorted(EXCLUDED)


def _validate_default_check_parameters() -> None:
    conftest_source = Path(__file__).read_text(encoding="utf-8")
    fixture_names = fixture_names_from_source(
        conftest_source,
        filename=Path(__file__).name,
    )
    for relative_path in sorted(DEFAULT_OFFLINE):
        test_path = TESTS_ROOT / relative_path
        try:
            validate_check_parameters(
                test_path.read_text(encoding="utf-8"),
                filename=relative_path,
                fixture_names=fixture_names,
            )
        except ParameterContractError as exc:
            raise pytest.UsageError(
                f"Python test parameter contract failed before collection: {exc}"
            ) from exc


_validate_default_check_parameters()


_SESSION_TEMP = tempfile.TemporaryDirectory(prefix="project-kei-pytest-")
SESSION_TEMP_ROOT = Path(_SESSION_TEMP.name)
os.environ["PROJECT_KEI_ENV_FILE"] = os.fspath(SESSION_TEMP_ROOT / "missing.env")
os.environ["PROJECT_KEI_LLM_PROFILE_PATH"] = os.fspath(
    SESSION_TEMP_ROOT / "llm-profile.json"
)
os.environ["PROJECT_KEI_VOICE_PACK_REGISTRY"] = os.fspath(
    SESSION_TEMP_ROOT / "voice-pack-registry.json"
)
os.environ["PROJECT_KEI_NO_BROWSER"] = "1"
os.environ["PROJECT_KEI_NO_PAUSE"] = "1"
sys.dont_write_bytecode = True


class ProtectedPathAccess(AssertionError):
    """A default test reached real Project Kei state before test isolation."""


class ExternalNetworkAccess(AssertionError):
    """A default test attempted non-loopback network access."""


def _absolute_lexical(value: object) -> str | None:
    if isinstance(value, int):
        return None
    try:
        raw = os.fsdecode(os.fspath(value))
    except TypeError:
        return None
    return os.path.normcase(os.path.abspath(raw))


def _resolved_path_key(value: object) -> str | None:
    if isinstance(value, int):
        return None
    try:
        raw = os.fsdecode(os.fspath(value))
    except TypeError:
        return None
    return os.path.normcase(os.fspath(Path(raw).resolve(strict=False)))


_REPO_KEY = _absolute_lexical(REPO_ROOT)
assert _REPO_KEY is not None
_PROTECTED_ROOTS = tuple(
    value
    for value in (
        _absolute_lexical(REPO_ROOT / ".env"),
        _absolute_lexical(REPO_ROOT / "README.local.md"),
        _absolute_lexical(REPO_ROOT / ".venv"),
        _absolute_lexical(REPO_ROOT / "vendor"),
        _absolute_lexical(SERVER_ROOT / ".env"),
        _absolute_lexical(SERVER_ROOT / ".venv-asr"),
        _absolute_lexical(SERVER_ROOT / "cache"),
        _absolute_lexical(SERVER_ROOT / "data"),
        _absolute_lexical(SERVER_ROOT / "intel_history"),
        _absolute_lexical(SERVER_ROOT / "models"),
        _absolute_lexical(SERVER_ROOT / "output"),
        _absolute_lexical(SERVER_ROOT / "profiles"),
        _absolute_lexical(SERVER_ROOT / "reference_audio"),
        _absolute_lexical(SERVER_ROOT / "runtime"),
        _absolute_lexical(SERVER_ROOT / "systems" / "data"),
        _absolute_lexical(SERVER_ROOT / "voice_packs"),
        _absolute_lexical(SERVER_ROOT / "qq_bridge" / ".env"),
        _absolute_lexical(SERVER_ROOT / "qq_bridge" / "data"),
        _absolute_lexical(SERVER_ROOT / "qq_bridge" / "node_modules"),
        _absolute_lexical(SERVER_ROOT / "qq_bridge" / "runtime"),
    )
    if value is not None
)


def _is_same_or_child(candidate: str, root: str) -> bool:
    return candidate == root or candidate.startswith(root + os.sep)


def _guard_path(value: object, *, write: bool = False) -> None:
    candidate = _absolute_lexical(value)
    if candidate is None:
        return
    if any(_is_same_or_child(candidate, root) for root in _PROTECTED_ROOTS):
        raise ProtectedPathAccess("protected Project Kei path rejected before I/O")
    if write and _is_same_or_child(candidate, _REPO_KEY):
        raise ProtectedPathAccess("repository write rejected; use pytest temporary paths")


_RESTORE: list[tuple[object, str, object]] = []


def _replace(owner: object, name: str, replacement: object) -> None:
    _RESTORE.append((owner, name, getattr(owner, name)))
    setattr(owner, name, replacement)


_original_builtin_open = builtins.open
_original_io_open = io.open
_original_os_open = os.open


def _guarded_builtin_open(file, mode="r", *args, **kwargs):
    _guard_path(file, write=any(flag in mode for flag in "wax+"))
    return _original_builtin_open(file, mode, *args, **kwargs)


def _guarded_io_open(file, mode="r", *args, **kwargs):
    _guard_path(file, write=any(flag in mode for flag in "wax+"))
    return _original_io_open(file, mode, *args, **kwargs)


def _guarded_os_open(path, flags, *args, **kwargs):
    write_flags = (
        os.O_WRONLY
        | os.O_RDWR
        | os.O_CREAT
        | os.O_TRUNC
        | os.O_APPEND
    )
    _guard_path(path, write=bool(flags & write_flags))
    return _original_os_open(path, flags, *args, **kwargs)


def _wrap_path_call(original: Callable, *, write: bool = False) -> Callable:
    def guarded(path=".", *args, **kwargs):
        _guard_path(path, write=write)
        return original(path, *args, **kwargs)

    return guarded


def _wrap_two_path_call(original: Callable) -> Callable:
    def guarded(source, target, *args, **kwargs):
        _guard_path(source, write=True)
        _guard_path(target, write=True)
        return original(source, target, *args, **kwargs)

    return guarded


def _wrap_path_method(original: Callable, *, write: bool = False) -> Callable:
    def guarded(path: Path, *args, **kwargs):
        _guard_path(path, write=write)
        return original(path, *args, **kwargs)

    return guarded


def _wrap_path_open(original: Callable) -> Callable:
    def guarded(path: Path, mode="r", *args, **kwargs):
        _guard_path(path, write=any(flag in mode for flag in "wax+"))
        return original(path, mode, *args, **kwargs)

    return guarded


def _is_loopback_host(host: object) -> bool:
    if host is None:
        return True
    if isinstance(host, bytes):
        host = host.decode("ascii", "strict")
    if not isinstance(host, str):
        return False
    value = host.strip().strip("[]").casefold()
    if value == "localhost":
        return True
    try:
        return ipaddress.ip_address(value).is_loopback
    except ValueError:
        return False


_original_getaddrinfo = socket.getaddrinfo
_original_create_connection = socket.create_connection
_original_socket_connect = socket.socket.connect
_original_socket_connect_ex = socket.socket.connect_ex
_original_socket_sendto = socket.socket.sendto


def _guard_network_address(address: object) -> None:
    if isinstance(address, tuple) and address:
        raise ExternalNetworkAccess("outbound network rejected before socket I/O")


def _guarded_getaddrinfo(host, *args, **kwargs):
    if not _is_loopback_host(host):
        raise ExternalNetworkAccess("external DNS rejected before resolver I/O")
    return _original_getaddrinfo(host, *args, **kwargs)


def _guarded_create_connection(address, *args, **kwargs):
    _guard_network_address(address)
    return _original_create_connection(address, *args, **kwargs)


def _stdlib_socketpair_is_calling() -> bool:
    frame = sys._getframe(1)
    while frame is not None:
        if (
            frame.f_code.co_name in {"socketpair", "_fallback_socketpair"}
            and Path(frame.f_code.co_filename).name == "socket.py"
        ):
            return True
        frame = frame.f_back
    return False


def _guarded_connect(sock, address):
    if not _stdlib_socketpair_is_calling():
        _guard_network_address(address)
    return _original_socket_connect(sock, address)


def _guarded_connect_ex(sock, address):
    _guard_network_address(address)
    return _original_socket_connect_ex(sock, address)


def _guarded_sendto(sock, data, *args, **kwargs):
    address = args[-1] if args else kwargs.get("address")
    _guard_network_address(address)
    return _original_socket_sendto(sock, data, *args, **kwargs)


def _install_guards() -> None:
    _replace(builtins, "open", _guarded_builtin_open)
    _replace(io, "open", _guarded_io_open)
    _replace(os, "open", _guarded_os_open)
    for name in ("mkdir", "makedirs", "remove", "rmdir", "unlink"):
        _replace(os, name, _wrap_path_call(getattr(os, name), write=True))
    for name in ("rename", "replace"):
        _replace(os, name, _wrap_two_path_call(getattr(os, name)))
    _replace(socket, "getaddrinfo", _guarded_getaddrinfo)
    _replace(socket, "create_connection", _guarded_create_connection)
    _replace(socket.socket, "connect", _guarded_connect)
    _replace(socket.socket, "connect_ex", _guarded_connect_ex)
    _replace(socket.socket, "sendto", _guarded_sendto)


_install_guards()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    restore_from = len(_RESTORE)
    # Python 3.10 pathlib dispatches through a private accessor instead of the
    # io/os functions patched above.  Guard the stable public Path methods for
    # the duration of each test so all supported Python versions fail before
    # protected I/O while pytest collection and dependency imports remain free
    # to inspect their own runtime files.
    _replace(Path, "open", _wrap_path_open(Path.open))
    for name in ("lstat", "stat"):
        _replace(Path, name, _wrap_path_method(getattr(Path, name)))
    for name in ("access", "listdir", "lstat", "readlink", "scandir", "stat"):
        _replace(os, name, _wrap_path_call(getattr(os, name)))
    try:
        yield
    finally:
        while len(_RESTORE) > restore_from:
            owner, name, original = _RESTORE.pop()
            setattr(owner, name, original)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def path(tmp_path: Path) -> Path:
    return tmp_path / "state.json"


@pytest.fixture
def cache_dir(tmp_path: Path) -> Path:
    value = tmp_path / "cache"
    value.mkdir()
    return value


@pytest.fixture
def temp_root(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def clock(request):
    clock_type = getattr(request.module, "MutableClock", None)
    if clock_type is None:
        pytest.fail("clock fixture requires the test module's MutableClock")
    return clock_type(datetime(2026, 7, 22, 8, 0, tzinfo=timezone.utc))


@pytest.fixture
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture
def protected_path_error():
    return ProtectedPathAccess


@pytest.fixture
def external_network_error():
    return ExternalNetworkAccess


@pytest.fixture
def fixed_utc_now() -> datetime:
    return datetime(2026, 7, 22, 8, 0, tzinfo=timezone.utc)


def _legacy_wrapper(callable_obj: Callable) -> Callable[[], None]:
    def run() -> None:
        result = (
            asyncio.run(callable_obj())
            if inspect.iscoroutinefunction(callable_obj)
            else callable_obj()
        )
        if isinstance(result, int) and not isinstance(result, bool) and result != 0:
            pytest.fail(f"legacy entrypoint returned non-zero status {result}")

    run.__name__ = "test_legacy_entrypoint"
    run.__doc__ = f"pytest compatibility wrapper for {callable_obj.__name__}"
    return run


def pytest_pycollect_makeitem(collector, name: str, obj: object):
    module_name = Path(str(collector.path)).name
    entrypoint = LEGACY_ENTRYPOINTS.get(module_name)
    if entrypoint == name and callable(obj):
        return pytest.Function.from_parent(
            collector,
            name="test_legacy_entrypoint",
            callobj=_legacy_wrapper(obj),
        )
    collector_module = getattr(collector, "obj", None)
    if (
        inspect.isfunction(obj)
        and getattr(obj, "__module__", None)
        != getattr(collector_module, "__name__", None)
    ):
        return []
    return None


def _top_level_checks(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=os.fspath(path))
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("check_")
    }


def pytest_collection_finish(session) -> None:
    if session.testsfailed:
        return
    requested = {
        _resolved_path_key(str(argument).split("::", 1)[0])
        for argument in session.config.args
    }
    if requested != {_resolved_path_key(TESTS_ROOT)}:
        return
    collected: set[tuple[str, str]] = set()
    for item in session.items:
        module_key = _resolved_path_key(getattr(item, "path", None))
        if module_key is None:
            continue
        skipped = any(
            next(item.iter_markers(name=marker_name), None) is not None
            for marker_name in ("skip", "skipif")
        )
        identity = collected_function_identity(
            module_key,
            getattr(item, "originalname", None),
            module_level=(
                isinstance(item, pytest.Function)
                and isinstance(getattr(item, "parent", None), pytest.Module)
            ),
            skipped=skipped,
        )
        if identity is not None:
            collected.add(identity)
    missing: list[str] = []
    for filename in sorted(DEFAULT_OFFLINE):
        path = TESTS_ROOT / filename
        relative = f"server/tests/{filename}"
        module_key = _resolved_path_key(path)
        assert module_key is not None
        for check_name in sorted(_top_level_checks(path)):
            expected = f"{relative}::{check_name}"
            if (module_key, check_name) not in collected:
                missing.append(expected)
        if filename in LEGACY_ENTRYPOINTS:
            expected = f"{relative}::test_legacy_entrypoint"
            if (module_key, "test_legacy_entrypoint") not in collected:
                missing.append(expected)
    if missing:
        raise pytest.UsageError(
            "default Python checks escaped pytest collection: " + ", ".join(missing)
        )


def pytest_report_header() -> str:
    return (
        f"Project Kei offline guard: default_files={len(DEFAULT_OFFLINE)} "
        f"isolated_files={len(EXCLUDED)} network=outbound-blocked "
        "protected_project_state=blocked"
    )


def pytest_unconfigure(config) -> None:
    while _RESTORE:
        owner, name, original = _RESTORE.pop()
        setattr(owner, name, original)
    _SESSION_TEMP.cleanup()
