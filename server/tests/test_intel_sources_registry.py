"""Isolated PK-115 registry checks; every persisted config uses a temporary path."""

from __future__ import annotations

import ast
import json
import os
import tempfile
import threading
from datetime import date, datetime, timezone
from pathlib import Path

import _path_setup  # noqa: F401

from features.daily_briefing.models import CollectRequest
from features.intel_sources.models import SOURCE_FIELDS, normalize_source_config
from features.intel_sources.repository import (
    IntelSourceConfigRepository,
    IntelSourcePersistenceError,
    IntelSourceStateError,
)
from features.intel_sources.service import IntelSourceRegistry
from services.intel_source_config import normalize_intel_sources


FIXED_TIME = datetime(2026, 7, 22, 6, 30, tzinfo=timezone.utc)
DEFAULTS = {
    "twitter_users": ["OpenAI"],
    "money_twitter_users": [],
    "github_users": [],
    "github_repos": [],
    "bilibili_uids": [],
    "youtube_channel_ids": [],
    "paper_priority_authors": [],
    "paper_secondary_authors": [],
    "paper_ai_authors": [],
}


def registry(path: Path, *, replace=None) -> IntelSourceRegistry:
    repository = (
        IntelSourceConfigRepository(path)
        if replace is None
        else IntelSourceConfigRepository(path, replace=replace)
    )
    return IntelSourceRegistry(
        repository,
        defaults_provider=lambda: {key: list(value) for key, value in DEFAULTS.items()},
        clock=lambda: FIXED_TIME,
    )


def full_payload() -> dict[str, list[object]]:
    return {
        "twitter_users": ["@KeiBot", "keibot", "OpenAI"],
        "money_twitter_users": ["IndieHackers"],
        "github_users": ["openai"],
        "github_repos": ["openai/openai-python"],
        "bilibili_uids": [123, "456", "123"],
        "youtube_channel_ids": ["UC1234567890123456789012"],
        "paper_priority_authors": ["Ada   Lovelace"],
        "paper_secondary_authors": ["Grace Hopper"],
        "paper_ai_authors": [],
    }


def check_validation() -> None:
    normalized = normalize_source_config(full_payload(), DEFAULTS)
    assert normalized["twitter_users"] == ("KeiBot", "OpenAI")
    assert normalized["bilibili_uids"] == (123, 456)
    assert normalized["paper_priority_authors"] == ("Ada Lovelace",)

    legacy = normalize_intel_sources({"twitter_users": ["@KeiBot"]}, DEFAULTS)
    assert legacy["twitter_users"] == ["KeiBot"]
    assert legacy["github_repos"] == []

    invalid_cases = [
        ({"github_repos": ["not-a-repository"]}, "owner/repository"),
        ({"bilibili_uids": [0]}, "positive integer"),
        ({"youtube_channel_ids": ["?"]}, "format is invalid"),
        ({"twitter_users": "OpenAI"}, "must be a list"),
        ({"api_token": "synthetic-secret"}, "unknown source configuration field"),
        ({"schema_version": 2}, "unsupported source configuration schema"),
        ({"schema_version": 1.5}, "unsupported source configuration schema"),
        ({"schema_version": "1"}, "unsupported source configuration schema"),
    ]
    for payload, message in invalid_cases:
        try:
            normalize_source_config(payload, DEFAULTS)
        except ValueError as exc:
            assert message in str(exc)
        else:
            raise AssertionError(f"invalid payload was accepted: {payload!r}")


def check_crud_and_snapshot() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "intel_sources.json"
        source_registry = registry(path)
        initial = source_registry.read()
        assert initial["using_local_override"] is False
        assert initial["twitter_users"] == ["OpenAI"]
        assert not path.exists()

        unchanged = source_registry.add("twitter_users", "@openai")
        assert unchanged["changed"] is False
        assert not path.exists()

        added = source_registry.add("twitter_users", "@KeiBot")
        assert added["changed"] is True
        assert added["twitter_users"] == ["OpenAI", "KeiBot"]
        assert added["updated_at"] == "2026-07-22T06:30:00+00:00"

        updated = source_registry.update("twitter_users", 1, "Karpathy")
        assert updated["twitter_users"] == ["OpenAI", "Karpathy"]
        try:
            source_registry.update("twitter_users", 1, "openai")
        except ValueError as exc:
            assert "already exists" in str(exc)
        else:
            raise AssertionError("duplicate update was accepted")
        assert source_registry.read()["twitter_users"] == ["OpenAI", "Karpathy"]

        removed = source_registry.remove("twitter_users", 0)
        assert removed["twitter_users"] == ["Karpathy"]

        saved = source_registry.replace(full_payload())
        assert saved["using_local_override"] is True
        stored = json.loads(path.read_text(encoding="utf-8"))
        assert stored["schema_version"] == 1
        assert set(stored) == set(SOURCE_FIELDS) | {"schema_version", "updated_at"}
        assert "synthetic-secret" not in path.read_text(encoding="utf-8")

        snapshot = source_registry.snapshot()
        assert snapshot["github_repos"] == ("openai/openai-python",)
        try:
            snapshot["github_repos"] = ()  # type: ignore[index]
        except TypeError:
            pass
        else:
            raise AssertionError("Collector snapshot mapping is mutable")

        request = CollectRequest(
            local_date=date(2026, 7, 22),
            timezone="Asia/Shanghai",
            source_ids=("github",),
            source_config_snapshot=source_registry.snapshot(["github"]),
        )
        assert request.source_config_snapshot == {
            "github_users": ["openai"],
            "github_repos": ["openai/openai-python"],
        }
        assert not ({"twitter_users", "bilibili_uids"} & set(request.source_config_snapshot))


def check_atomic_failure_and_invalid_state() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "intel_sources.json"
        source_registry = registry(path)
        source_registry.replace(full_payload())
        original_bytes = path.read_bytes()
        failure_attempts = 0

        def fail_replace(_source, _target) -> None:
            nonlocal failure_attempts
            failure_attempts += 1
            raise OSError("synthetic replace failure")

        failing_registry = registry(path, replace=fail_replace)
        changed = full_payload()
        changed["github_repos"] = ["example/changed"]
        try:
            failing_registry.replace(changed)
        except IntelSourcePersistenceError as exc:
            assert "could not be saved" in str(exc)
        else:
            raise AssertionError("replace failure was not reported")
        assert failure_attempts == 1
        assert path.read_bytes() == original_bytes
        assert not list(path.parent.glob(".intel_sources.json.*.tmp"))

        path.write_text("{not valid json", encoding="utf-8")
        recovered = source_registry.read()
        assert recovered["using_local_override"] is False
        assert recovered["load_warning"] == "local source registry is unavailable; using defaults"
        assert recovered["twitter_users"] == ["OpenAI"]
        try:
            source_registry.snapshot()
        except IntelSourceStateError:
            pass
        else:
            raise AssertionError("invalid local state was silently exposed as a Collector snapshot")
        assert path.read_text(encoding="utf-8") == "{not valid json"


def check_transient_windows_replace_retry_is_bounded_and_atomic() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "intel_sources.json"
        source_registry = registry(path)
        source_registry.replace(full_payload())

        transient_attempts = 0

        def transient_then_succeed(source, target) -> None:
            nonlocal transient_attempts
            transient_attempts += 1
            if transient_attempts < 3:
                exc = PermissionError("synthetic Windows sharing violation")
                exc.winerror = 32
                raise exc
            os.replace(source, target)

        changed = full_payload()
        changed["github_repos"] = ["example/retried"]
        registry(path, replace=transient_then_succeed).replace(changed)
        assert transient_attempts == 3
        assert json.loads(path.read_text(encoding="utf-8"))["github_repos"] == [
            "example/retried"
        ]
        stable_bytes = path.read_bytes()

        exhausted_attempts = 0

        def always_transient(_source, _target) -> None:
            nonlocal exhausted_attempts
            exhausted_attempts += 1
            exc = PermissionError("synthetic Windows lock violation")
            exc.winerror = 33
            raise exc

        try:
            registry(path, replace=always_transient).replace(full_payload())
        except IntelSourcePersistenceError:
            pass
        else:
            raise AssertionError("exhausted transient replace was not reported")
        assert exhausted_attempts == 5
        assert path.read_bytes() == stable_bytes
        assert not list(path.parent.glob(".intel_sources.json.*.tmp"))


def check_concurrent_atomic_writes() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "intel_sources.json"
        failures: list[BaseException] = []
        attempts_by_temporary_path: dict[str, int] = {}
        start_barrier = threading.Barrier(12)

        def transient_once_then_replace(source, target) -> None:
            key = os.fspath(source)
            attempts_by_temporary_path[key] = attempts_by_temporary_path.get(key, 0) + 1
            if attempts_by_temporary_path[key] == 1:
                exc = PermissionError("synthetic concurrent Windows sharing violation")
                exc.winerror = 5
                raise exc
            os.replace(source, target)

        def worker(index: int) -> None:
            try:
                payload = full_payload()
                payload["github_repos"] = [f"example/repository-{index}"]
                start_barrier.wait()
                registry(path, replace=transient_once_then_replace).replace(payload)
            except BaseException as exc:  # pragma: no cover - reported by parent assertion
                failures.append(exc)

        threads = [threading.Thread(target=worker, args=(index,)) for index in range(12)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert not failures
        assert len(attempts_by_temporary_path) == 12
        assert set(attempts_by_temporary_path.values()) == {2}
        persisted = json.loads(path.read_text(encoding="utf-8"))
        normalize_source_config(persisted, DEFAULTS)
        assert len(persisted["github_repos"]) == 1
        assert not list(path.parent.glob(".intel_sources.json.*.tmp"))


def check_forbidden_dependency_edges() -> None:
    feature_root = Path(__file__).resolve().parents[1] / "features" / "intel_sources"
    compatibility_path = Path(__file__).resolve().parents[1] / "services" / "intel_source_config.py"
    forbidden = {
        "features.daily_briefing.collector_gateway",
        "features.daily_briefing.service",
        "features.daily_briefing.repository",
        "features.daily_briefing.router",
    }
    for path in [*feature_root.glob("*.py"), compatibility_path]:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        assert not (forbidden & imported), (path.name, forbidden & imported)
        assert not any(name.startswith("intel.collectors") for name in imported), path.name


def main() -> int:
    check_validation()
    check_crud_and_snapshot()
    check_atomic_failure_and_invalid_state()
    check_transient_windows_replace_retry_is_bounded_and_atomic()
    check_concurrent_atomic_writes()
    check_forbidden_dependency_edges()
    print("PK-115 intel source registry tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
