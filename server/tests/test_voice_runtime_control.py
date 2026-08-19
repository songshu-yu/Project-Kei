"""Isolated checks for fixed ASR/GPT-SoVITS dashboard launch controls."""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import tempfile
import threading
from pathlib import Path

import httpx
from fastapi import FastAPI

import _path_setup  # noqa: F401

from features.voice.control_router import create_voice_control_router
from features.voice.asr_model_directory import AsrModelDirectoryService
from features.voice.runtime_control import VoiceRuntimeControlService


class FakeProcess:
    def __init__(self):
        self.returncode = None
        self.signals = []
        self.waits = []

    def poll(self):
        return self.returncode

    def send_signal(self, value):
        self.signals.append(value)

    def terminate(self):
        self.signals.append("terminate")

    def wait(self, timeout=None):
        self.waits.append(timeout)
        self.returncode = 0
        return 0


def make_service(
    root: Path,
    *,
    asr_ready: bool = True,
    gpt_ready: bool = True,
    running_ports: set[int] | None = None,
    model_directory: AsrModelDirectoryService | None = None,
):
    asr_launcher = root / "start_asr.bat"
    gpt_launcher = root / "start_gptsovits.bat"
    asr_launcher.write_text("@echo off\n", encoding="utf-8")
    gpt_launcher.write_text("@echo off\n", encoding="utf-8")
    popen_calls = []

    def popen(command, **kwargs):
        popen_calls.append((command, kwargs))
        return FakeProcess()

    service = VoiceRuntimeControlService(
        asr_launcher=asr_launcher,
        gpt_sovits_launcher=gpt_launcher,
        asr_readiness=lambda: asr_ready,
        gpt_sovits_readiness=lambda: gpt_ready,
        port_checker=lambda port: port in (running_ports or set()),
        popen_factory=popen,
        asr_model_directory=model_directory,
    )
    return service, popen_calls


def make_model(path: Path) -> Path:
    path.mkdir(parents=True)
    (path / "model.bin").write_bytes(b"model")
    (path / "config.json").write_text('{"model_type":"fake"}\n', encoding="utf-8")
    (path / "tokenizer.json").write_text('{"fake":true}\n', encoding="utf-8")
    return path


def test_model_directory_cancel_invalid_reparse_and_save_failure_are_atomic():
    with tempfile.TemporaryDirectory(prefix="kei-asr-directory-") as temp_dir:
        root = Path(temp_dir)
        config = root / "state" / "asr-model.local.json"
        first = make_model(root / "first-model")
        second = make_model(root / "second-model")

        initial = AsrModelDirectoryService(config, picker=lambda: str(first))
        assert initial.select()["state"] == "configured"
        original = config.read_bytes()

        cancelled = AsrModelDirectoryService(config, picker=lambda: None)
        assert cancelled.select()["state"] == "cancelled"
        assert config.read_bytes() == original

        wrong = root / "not-a-model"
        wrong.mkdir()
        invalid = AsrModelDirectoryService(config, picker=lambda: str(wrong))
        assert invalid.select()["state"] == "invalid_model"
        assert config.read_bytes() == original
        assert invalid.validate(r"\\attacker.invalid\share\model") is None

        reparse = AsrModelDirectoryService(
            config,
            picker=lambda: str(second),
            reparse_checker=lambda path: path == second,
        )
        assert reparse.select()["state"] == "invalid_model"
        assert config.read_bytes() == original

        def fail_replace(_source, _destination):
            raise OSError("simulated save failure")

        failing = AsrModelDirectoryService(
            config,
            picker=lambda: str(second),
            replace=fail_replace,
        )
        assert failing.select()["state"] == "save_failed"
        assert config.read_bytes() == original
        assert not list(config.parent.glob(".asr-model-*.tmp"))


def test_model_directory_ignores_reparse_outside_selected_tree_but_rejects_model_entries():
    with tempfile.TemporaryDirectory(prefix="kei-asr-directory-") as temp_dir:
        root = Path(temp_dir)
        model = make_model(root / "model")
        config = root / "state" / "asr-model.local.json"

        # Windows runners may place TEMP below a system-managed junction.  That
        # ancestor is outside the explicitly selected tree and must not make a
        # valid model fail closed.
        outside_ancestor = root.parent
        valid = AsrModelDirectoryService(
            config,
            picker=lambda: str(model),
            reparse_checker=lambda path: path == outside_ancestor,
        )
        assert valid.select()["state"] == "configured"

        protected_entries = (
            model,
            model / "model.bin",
            model / "config.json",
            model / "tokenizer.json",
        )
        for protected_entry in protected_entries:
            guarded = AsrModelDirectoryService(
                root / f"blocked-{protected_entry.name}.json",
                picker=lambda: str(model),
                reparse_checker=lambda path, blocked=protected_entry: path == blocked,
            )
            assert guarded.select()["state"] == "invalid_model", (
                f"reparse entry was accepted: {protected_entry.name}"
            )

        assert valid.validate(model / ".." / "model") is None
        assert valid.validate(r"\\attacker.invalid\share\model") is None


def test_model_directory_checks_short_alias_and_canonical_model_entries():
    with tempfile.TemporaryDirectory(prefix="kei-asr-directory-") as temp_dir:
        root = Path(temp_dir)
        canonical = make_model(root / "runneradmin" / "model")
        short_alias = root / "RUNNER~1" / "model"
        model_names = ("model.bin", "config.json", "tokenizer.json")

        def resolve_alias(path: Path) -> Path:
            assert path == short_alias
            return canonical

        for spelling_root in (short_alias, canonical):
            for name in model_names:
                blocked = spelling_root / name
                guarded = AsrModelDirectoryService(
                    root / f"blocked-{spelling_root.name}-{name}.json",
                    picker=lambda: str(short_alias),
                    reparse_checker=lambda path, entry=blocked: path == entry,
                    resolve=resolve_alias,
                )
                assert guarded.select()["state"] == "invalid_model", (
                    f"reparse entry was accepted: {blocked}"
                )

        valid = AsrModelDirectoryService(
            root / "alias-valid.json",
            picker=lambda: str(short_alias),
            reparse_checker=lambda _path: False,
            resolve=resolve_alias,
        )
        assert valid.select()["state"] == "configured"


def test_model_directory_concurrent_selection_is_single_dialog():
    with tempfile.TemporaryDirectory(prefix="kei-asr-directory-") as temp_dir:
        root = Path(temp_dir)
        model = make_model(root / "fake-model")
        entered = threading.Event()
        release = threading.Event()
        picker_calls = []

        def picker():
            picker_calls.append(True)
            entered.set()
            release.wait(timeout=3)
            return str(model)

        manager = AsrModelDirectoryService(root / "config.json", picker=picker)
        results = []
        thread = threading.Thread(target=lambda: results.append(manager.select()))
        thread.start()
        assert entered.wait(timeout=3)
        second = manager.select()
        release.set()
        thread.join(timeout=3)
        assert second["state"] == "selection_in_progress"
        assert results[0]["state"] == "configured"
        assert len(picker_calls) == 1


def test_selected_model_is_private_and_used_only_for_fixed_asr_start():
    with tempfile.TemporaryDirectory(prefix="kei-asr-directory-") as temp_dir:
        root = Path(temp_dir)
        model = make_model(root / "private-model")
        manager = AsrModelDirectoryService(
            root / "state" / "config.json",
            picker=lambda: str(model),
        )
        assert manager.select()["state"] == "configured"
        service, popen_calls = make_service(
            root,
            asr_ready=False,
            model_directory=manager,
        )
        public = service.asr_model_selection_status()
        assert public["directory_name"] == "private-model"
        assert str(root) not in json.dumps(public, ensure_ascii=False)
        started = service.start("asr")
        assert started["started"] is True
        assert Path(popen_calls[0][1]["env"]["ASR_MODEL_PATH"]).samefile(model)
        assert str(model) not in json.dumps(started, ensure_ascii=False)


def test_core_without_asr_model_remains_read_only():
    with tempfile.TemporaryDirectory(prefix="kei-asr-directory-") as temp_dir:
        root = Path(temp_dir)
        manager = AsrModelDirectoryService(
            root / "state" / "config.json",
            picker=lambda: None,
        )
        service, popen_calls = make_service(
            root,
            asr_ready=False,
            model_directory=manager,
        )
        before = {path.relative_to(root) for path in root.rglob("*")}
        assert service.status()["asr"]["state"] == "missing_model"
        selection = service.asr_model_selection_status()
        assert selection["state"] == "unconfigured"
        assert before == {path.relative_to(root) for path in root.rglob("*")}
        assert not popen_calls


def test_status_is_read_only_and_path_free():
    with tempfile.TemporaryDirectory(prefix="kei-voice-control-") as temp_dir:
        root = Path(temp_dir)
        service, popen_calls = make_service(root)
        before = {path.relative_to(root) for path in root.rglob("*")}
        result = service.status()
        assert result["asr"]["state"] == "ready"
        assert result["gpt-sovits"]["state"] == "ready"
        assert not popen_calls
        assert before == {path.relative_to(root) for path in root.rglob("*")}
        assert str(root) not in json.dumps(result, ensure_ascii=False)


def test_missing_prerequisites_and_running_ports_do_not_start():
    with tempfile.TemporaryDirectory(prefix="kei-voice-control-") as temp_dir:
        root = Path(temp_dir)
        service, popen_calls = make_service(
            root,
            asr_ready=False,
            gpt_ready=False,
        )
        assert service.start("asr")["state"] == "missing_model"
        assert service.start("gpt-sovits")["state"] == "missing_registration"
        assert not popen_calls

        running, popen_calls = make_service(root, running_ports={8010, 9880})
        assert running.start("asr")["state"] == "running"
        assert running.start("gpt-sovits")["state"] == "running"
        assert not popen_calls


def test_concurrent_start_uses_each_fixed_launcher_once():
    with tempfile.TemporaryDirectory(prefix="kei-voice-control-") as temp_dir:
        root = Path(temp_dir)
        service, popen_calls = make_service(root)
        results = []
        threads = [
            threading.Thread(target=lambda: results.append(service.start("asr")))
            for _ in range(8)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert len(popen_calls) == 1
        assert sum(bool(result["started"]) for result in results) == 1
        assert Path(popen_calls[0][0][-1]) == root / "start_asr.bat"

        started = service.start("gpt-sovits")
        assert started["started"]
        assert len(popen_calls) == 2
        assert Path(popen_calls[1][0][-1]) == root / "start_gptsovits.bat"


def test_background_start_is_hidden_but_debug_start_keeps_console():
    with tempfile.TemporaryDirectory(prefix="kei-voice-control-") as temp_dir:
        root = Path(temp_dir)
        background, background_calls = make_service(root)
        started = background.start_background("asr")
        assert started["started"] is True
        assert "后台启动" in started["message"]
        background_kwargs = background_calls[0][1]
        assert background_kwargs["creationflags"] & getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        ) == getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        if os.name == "nt":
            startupinfo = background_kwargs["startupinfo"]
            assert startupinfo.dwFlags & getattr(subprocess, "STARTF_USESHOWWINDOW", 0)
            assert startupinfo.wShowWindow == getattr(subprocess, "SW_HIDE", 0)

        debug, debug_calls = make_service(root)
        debug_started = debug.start("gpt-sovits")
        assert debug_started["started"] is True
        assert "调试窗口" in debug_started["message"]
        assert "startupinfo" not in debug_calls[0][1]


def test_stop_is_owned_only_and_idempotent():
    with tempfile.TemporaryDirectory(prefix="kei-voice-control-") as temp_dir:
        root = Path(temp_dir)
        service, popen_calls = make_service(root)
        started = service.start("asr")
        assert started["can_stop"] is True
        process = service._processes["asr"]
        stopped = service.stop("asr")
        assert stopped["stopped"] is True
        assert stopped["running"] is False
        assert stopped["can_stop"] is False
        assert len(process.signals) == 1
        assert len(process.waits) == 1
        again = service.stop("asr")
        assert again["stopped"] is False
        assert len(process.signals) == 1
        assert len(popen_calls) == 1

        external, external_calls = make_service(root, running_ports={9880})
        status = external.status()["gpt-sovits"]
        assert status["running"] is True
        assert status["can_stop"] is False
        result = external.stop("gpt-sovits")
        assert result["state"] == "external_running"
        assert result["stopped"] is False
        assert not external_calls

        occupied_after_stop, _ = make_service(root)
        occupied_after_stop.start("asr")
        occupied_after_stop._port_checker = lambda port: port == 8010
        failed = occupied_after_stop.stop("asr")
        assert failed["state"] == "stop_failed"
        assert failed["stopped"] is False
        assert failed["can_stop"] is False


def test_routes_require_loopback_origin_and_reject_arbitrary_commands():
    asyncio.run(_exercise_routes())


async def _exercise_routes():
    with tempfile.TemporaryDirectory(prefix="kei-voice-control-") as temp_dir:
        root = Path(temp_dir)
        service, popen_calls = make_service(
            root,
            model_directory=AsrModelDirectoryService(
                root / "state" / "config.json",
                picker=lambda: None,
            ),
        )
        app = FastAPI()
        app.include_router(create_voice_control_router(
            service,
            read_guard=lambda request: request.client.host == "127.0.0.1",
            write_guard=lambda request: (
                request.client.host == "127.0.0.1"
                and request.headers.get("origin") == "http://127.0.0.1:8000"
            ),
        ))
        local = httpx.ASGITransport(app=app, client=("127.0.0.1", 51000))
        remote = httpx.ASGITransport(app=app, client=("203.0.113.9", 51000))
        trusted = {"Origin": "http://127.0.0.1:8000"}
        async with httpx.AsyncClient(transport=local, base_url="http://test") as client:
            status = await client.get("/api/v1/voice-control/status")
            assert status.status_code == 200
            assert (await client.post(
                "/api/v1/voice-control/asr/start",
            )).status_code == 403
            assert (await client.post(
                "/api/v1/voice-control/asr/start",
                headers={"Origin": "https://evil.example"},
            )).status_code == 403
            arbitrary = await client.post(
                "/api/v1/voice-control/asr/start",
                headers=trusted,
                json={
                    "bat": "C:/FAKE/evil.bat",
                    "args": ["--download"],
                    "environment": {"FAKE_SECRET": "do-not-use"},
                },
            )
            assert arbitrary.status_code == 422
            assert arbitrary.json() == {"detail": "invalid_request"}
            assert not popen_calls
            selection_status = await client.get(
                "/api/v1/voice-control/asr/model-directory/status",
            )
            assert selection_status.status_code == 200
            assert "model_path" not in selection_status.text
            malicious_selection = await client.post(
                "/api/v1/voice-control/asr/model-directory/select",
                headers=trusted,
                json={"path": "C:/FAKE/model", "url": "https://evil.example"},
            )
            assert malicious_selection.status_code == 422
            cancelled = await client.post(
                "/api/v1/voice-control/asr/model-directory/select",
                headers=trusted,
            )
            assert cancelled.status_code == 200
            assert cancelled.json()["state"] == "cancelled"
            started = await client.post(
                "/api/v1/voice-control/asr/start",
                headers=trusted,
            )
            assert started.status_code == 200
            assert started.json()["started"]
            assert len(popen_calls) == 1
            stopped = await client.post(
                "/api/v1/voice-control/asr/stop",
                headers=trusted,
            )
            assert stopped.status_code == 200
            assert stopped.json()["stopped"] is True
            background = await client.post(
                "/api/v1/voice-control/gpt-sovits/start-background",
                headers=trusted,
            )
            assert background.status_code == 200
            assert background.json()["started"] is True
            assert background.json()["state"] == "starting"
            assert len(popen_calls) == 2
            malicious_background = await client.post(
                "/api/v1/voice-control/asr/start-background",
                headers=trusted,
                json={"command": "evil.exe", "hidden": True},
            )
            assert malicious_background.status_code == 422
            assert len(popen_calls) == 2
            assert (await client.post(
                "/api/v1/voice-control/gpt-sovits/stop",
                headers=trusted,
                json={"pid": 1234},
            )).status_code == 422
        async with httpx.AsyncClient(transport=remote, base_url="http://test") as client:
            assert (await client.get(
                "/api/v1/voice-control/status",
            )).status_code == 403
            assert (await client.post(
                "/api/v1/voice-control/gpt-sovits/start",
                headers=trusted,
            )).status_code == 403


if __name__ == "__main__":
    test_model_directory_cancel_invalid_reparse_and_save_failure_are_atomic()
    test_model_directory_ignores_reparse_outside_selected_tree_but_rejects_model_entries()
    test_model_directory_checks_short_alias_and_canonical_model_entries()
    test_model_directory_concurrent_selection_is_single_dialog()
    test_selected_model_is_private_and_used_only_for_fixed_asr_start()
    test_core_without_asr_model_remains_read_only()
    test_status_is_read_only_and_path_free()
    test_missing_prerequisites_and_running_ports_do_not_start()
    test_concurrent_start_uses_each_fixed_launcher_once()
    test_background_start_is_hidden_but_debug_start_keeps_console()
    test_stop_is_owned_only_and_idempotent()
    test_routes_require_loopback_origin_and_reject_arbitrary_commands()
    print("voice runtime control tests passed")
