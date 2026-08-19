from __future__ import annotations

import asyncio
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI, Request

from core.local_access import TRUSTED_LOCAL_ORIGINS, is_loopback_host
from core.restart_supervisor import (
    PROTOCOL_VERSION,
    RESTART_CONFIRMATION,
    RestartControlClient,
    _atomic_json,
)
from features.dashboard.restart_router import create_restart_router


SUPERVISOR_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "supervise_core.py"


def _load_supervisor_module():
    spec = importlib.util.spec_from_file_location("project_kei_test_supervisor", SUPERVISOR_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _control_guard(request: Request) -> bool:
    origins = request.headers.getlist("origin")
    return (
        request.client is not None
        and is_loopback_host(request.client.host)
        and len(origins) == 1
        and origins[0] in TRUSTED_LOCAL_ORIGINS
    )


def _session(tmp_path: Path, *, state: str = "running") -> tuple[RestartControlClient, Path]:
    runtime = tmp_path / "runtime" / "supervisor"
    session_id = "a" * 32
    directory = runtime / session_id
    directory.mkdir(parents=True)
    _atomic_json(directory / "session.json", {
        "schema_version": PROTOCOL_VERSION,
        "session_id": session_id,
        "scope": "core",
    })
    _atomic_json(directory / "status.json", {
        "schema_version": PROTOCOL_VERSION,
        "state": state,
        "scope": "core",
        "request_id": None,
        "generation": 0,
        "message": "Core is running under the local supervisor.",
    })
    return RestartControlClient(runtime, session_id), directory


def _app(client: RestartControlClient) -> FastAPI:
    app = FastAPI()
    def read_guard(request: Request) -> bool:
        origins = request.headers.getlist("origin")
        return (
            request.client is not None
            and is_loopback_host(request.client.host)
            and (not origins or (len(origins) == 1 and origins[0] in TRUSTED_LOCAL_ORIGINS))
        )

    app.include_router(create_restart_router(
        client,
        local_read_guard=read_guard,
        local_control_guard=_control_guard,
    ))
    return app


@pytest.mark.asyncio
async def test_restart_requires_supervisor_loopback_exact_origin_and_confirmation(tmp_path: Path) -> None:
    unavailable = RestartControlClient(tmp_path / "missing", None)
    transport = httpx.ASGITransport(app=_app(unavailable), client=("127.0.0.1", 43100))
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as http:
        no_origin = await http.post("/api/v1/dashboard/service/restart", json={"confirmation": RESTART_CONFIRMATION})
        assert no_origin.status_code == 403
        response = await http.post(
            "/api/v1/dashboard/service/restart",
            headers={"Origin": "http://127.0.0.1:8000"},
            json={"confirmation": RESTART_CONFIRMATION},
        )
        assert response.status_code == 503
        assert response.json()["state"] == "unavailable"
        assert response.json()["available"] is False

        status_without_origin = await http.get("/api/v1/dashboard/service/restart/status")
        assert status_without_origin.status_code == 200
        status_with_origin = await http.get(
            "/api/v1/dashboard/service/restart/status",
            headers={"Origin": "http://localhost:8000"},
        )
        assert status_with_origin.status_code == 200
        bad_status_origin = await http.get(
            "/api/v1/dashboard/service/restart/status",
            headers={"Origin": "http://192.168.1.7:8000"},
        )
        assert bad_status_origin.status_code == 403

    client, _ = _session(tmp_path / "active")
    transport = httpx.ASGITransport(app=_app(client), client=("10.20.30.40", 43100))
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as http:
        response = await http.post(
            "/api/v1/dashboard/service/restart",
            headers={
                "Origin": "http://127.0.0.1:8000",
                "Host": "127.0.0.1:8000",
                "X-Forwarded-For": "127.0.0.1",
                "Forwarded": "for=127.0.0.1",
            },
            json={"confirmation": RESTART_CONFIRMATION},
        )
        assert response.status_code == 403


@pytest.mark.asyncio
async def test_rejected_get_and_post_stop_before_supervisor_side_effects() -> None:
    class TripwireClient:
        def status(self):
            raise AssertionError("rejected GET reached supervisor status I/O")

        def request_restart(self, confirmation):
            raise AssertionError("rejected POST reached supervisor process control")

    remote = httpx.ASGITransport(app=_app(TripwireClient()), client=("192.168.50.8", 43100))
    async with httpx.AsyncClient(transport=remote, base_url="http://127.0.0.1:8000") as http:
        get_response = await http.get(
            "/api/v1/dashboard/service/restart/status",
            headers={
                "Origin": "http://127.0.0.1:8000",
                "Host": "127.0.0.1:8000",
                "X-Forwarded-For": "127.0.0.1",
                "Forwarded": "for=127.0.0.1",
            },
        )
        assert get_response.status_code == 403
        post_response = await http.post(
            "/api/v1/dashboard/service/restart",
            headers={
                "Origin": "http://127.0.0.1:8000",
                "Host": "127.0.0.1:8000",
                "X-Forwarded-For": "127.0.0.1",
                "Forwarded": "for=127.0.0.1",
            },
            json={"confirmation": RESTART_CONFIRMATION},
        )
        assert post_response.status_code == 403

    local = httpx.ASGITransport(app=_app(TripwireClient()), client=("127.0.0.1", 43100))
    async with httpx.AsyncClient(transport=local, base_url="http://127.0.0.1:8000") as http:
        bad_origin = await http.get(
            "/api/v1/dashboard/service/restart/status",
            headers={"Origin": "null"},
        )
        assert bad_origin.status_code == 403
        missing_post_origin = await http.post(
            "/api/v1/dashboard/service/restart",
            json={"confirmation": RESTART_CONFIRMATION},
        )
        assert missing_post_origin.status_code == 403
        for origin in ("null", "http://192.168.50.8:8000", "https://127.0.0.1:8000"):
            rejected = await http.post(
                "/api/v1/dashboard/service/restart",
                headers={"Origin": origin},
                json={"confirmation": RESTART_CONFIRMATION},
            )
            assert rejected.status_code == 403
        duplicate_origin = await http.post(
            "/api/v1/dashboard/service/restart",
            headers=[
                ("Origin", "http://127.0.0.1:8000"),
                ("Origin", "http://127.0.0.1:8000"),
            ],
            json={"confirmation": RESTART_CONFIRMATION},
        )
        assert duplicate_origin.status_code == 403


@pytest.mark.asyncio
async def test_restart_rejects_browser_supplied_execution_fields(tmp_path: Path) -> None:
    client, directory = _session(tmp_path)
    transport = httpx.ASGITransport(app=_app(client), client=("::1", 43100))
    headers = {"Origin": "http://[::1]:8000"}
    async with httpx.AsyncClient(transport=transport, base_url="http://[::1]:8000") as http:
        for body in (
            {},
            {"confirmation": "yes"},
            {"confirmation": RESTART_CONFIRMATION, "command": "anything"},
            {"confirmation": RESTART_CONFIRMATION, "pid": 123},
            {"confirmation": RESTART_CONFIRMATION, "port": 9000},
        ):
            response = await http.post("/api/v1/dashboard/service/restart", headers=headers, json=body)
            assert response.status_code == 400
        wrong_media = await http.post(
            "/api/v1/dashboard/service/restart",
            headers={**headers, "Content-Type": "text/plain"},
            content='{"confirmation":"restart-project-kei-core"}',
        )
        assert wrong_media.status_code == 415
    assert not (directory / "request.json").exists()


@pytest.mark.asyncio
async def test_concurrent_and_duplicate_restart_requests_are_deduplicated(tmp_path: Path) -> None:
    client, directory = _session(tmp_path)
    transport = httpx.ASGITransport(app=_app(client), client=("127.0.0.1", 43100))
    headers = {"Origin": "http://localhost:8000"}
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost:8000") as http:
        first, second = await asyncio.gather(*(
            http.post(
                "/api/v1/dashboard/service/restart",
                headers=headers,
                json={"confirmation": RESTART_CONFIRMATION},
            )
            for _ in range(2)
        ))
        assert first.status_code == second.status_code == 202
        assert first.json()["request_id"] == second.json()["request_id"]
        status = await http.get("/api/v1/dashboard/service/restart/status", headers=headers)
        assert status.status_code == 200
        assert status.json()["state"] == "accepted"
        assert status.json()["retry_after_ms"] == 500
    request = json.loads((directory / "request.json").read_text(encoding="utf-8"))
    assert set(request) == {"schema_version", "action", "session_id", "request_id"}
    assert request["action"] == "restart_core"


def test_tampered_status_message_and_linked_session_fail_closed(tmp_path: Path) -> None:
    client, directory = _session(tmp_path)
    _atomic_json(directory / "status.json", {
        "schema_version": PROTOCOL_VERSION,
        "state": "failed",
        "scope": "core",
        "request_id": "b" * 32,
        "generation": 1,
        "message": "C:\\private\\secret.env",
    })
    status = client.status()
    assert status["state"] == "unavailable"
    assert "secret" not in status["message"].lower()

    linked_root = tmp_path / "linked"
    try:
        linked_root.symlink_to(tmp_path / "runtime" / "supervisor", target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is unavailable on this Windows host")
    linked_client = RestartControlClient(linked_root, "a" * 32)
    assert linked_client.status()["state"] == "unavailable"


def test_real_api_assembly_allows_browser_get_without_origin_but_keeps_post_strict(tmp_path: Path) -> None:
    script = """
import asyncio
import json
import httpx
import api

async def check():
    transport = httpx.ASGITransport(app=api.app, client=("127.0.0.1", 45200))
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        no_origin = await client.get("/api/v1/dashboard/service/restart/status")
        good_origin = await client.get(
            "/api/v1/dashboard/service/restart/status",
            headers={"Origin": "http://127.0.0.1:8000"},
        )
        bad_origin = await client.get(
            "/api/v1/dashboard/service/restart/status",
            headers={"Origin": "null"},
        )
        post_without_origin = await client.post(
            "/api/v1/dashboard/service/restart",
            json={"confirmation": "restart-project-kei-core"},
        )
        print(json.dumps([
            no_origin.status_code,
            good_origin.status_code,
            bad_origin.status_code,
            post_without_origin.status_code,
        ]))

asyncio.run(check())
"""
    environment = dict(os.environ)
    environment["PROJECT_KEI_ENV_FILE"] = str(tmp_path / "missing.env")
    environment.pop("PROJECT_KEI_SUPERVISOR_SESSION", None)
    result = subprocess.run(
        [sys.executable, "-B", "-c", script],
        cwd=str(SUPERVISOR_SCRIPT.parents[1] / "server"),
        env=environment,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout
    assert json.loads(result.stdout.splitlines()[-1]) == [200, 200, 403, 403]


class FakeProcess:
    def __init__(self) -> None:
        self.returncode = None
        self.signals: list[object] = []

    def poll(self):
        return self.returncode

    def send_signal(self, value):
        self.signals.append(value)

    def wait(self, timeout=None):
        self.returncode = 0
        return 0

    def terminate(self):
        self.returncode = 0


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def now(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.value += seconds


def _prepared_supervisor(tmp_path: Path, *, run_code: int = 0):
    module = _load_supervisor_module()
    processes: list[FakeProcess] = []

    def popen(command, **options):
        assert command == list(module.CORE_COMMAND)
        assert options["cwd"] == str(module.SERVER_ROOT)
        assert options["env"]["PROJECT_KEI_SUPERVISOR_SESSION"]
        process = FakeProcess()
        processes.append(process)
        return process

    clock = FakeClock()
    supervisor = module.CoreSupervisor(
        runtime_root=tmp_path / "supervisor",
        popen=popen,
        run=lambda *args, **kwargs: SimpleNamespace(returncode=run_code),
        sleep=clock.sleep,
        monotonic=clock.now,
        ready_probe=lambda: True,
        ready_timeout=1,
    )
    supervisor.prepare()
    supervisor._start_child()
    supervisor._write_status("running", "Core is running under the local supervisor.")
    supervisor._port_is_free = lambda: True
    return supervisor, processes


def test_supervisor_restarts_only_fixed_core_and_preserves_old_on_preflight_failure(tmp_path: Path) -> None:
    supervisor, processes = _prepared_supervisor(tmp_path / "ok")
    client = RestartControlClient(supervisor.runtime_root, supervisor.session_id)
    accepted = client.request_restart(RESTART_CONFIRMATION)
    supervisor._restart(supervisor._take_request())
    assert len(processes) == 2
    assert processes[0].signals
    assert client.status()["state"] == "running"
    assert client.status()["generation"] == 1
    command = list(_load_supervisor_module().CORE_COMMAND)
    assert command[1:] == [
        "-B", "-m", "uvicorn", "api:app", "--host", "127.0.0.1", "--port", "8000",
    ]
    assert command[3] == "uvicorn" and command[4] == "api:app"
    assert not any(
        token in {"services.asr_server:app", "src/index.mjs", "gpt-sovits", "collector"}
        for token in command[1:]
    )

    blocked, old_processes = _prepared_supervisor(tmp_path / "blocked", run_code=1)
    blocked_client = RestartControlClient(blocked.runtime_root, blocked.session_id)
    blocked_client.request_restart(RESTART_CONFIRMATION)
    blocked._restart(blocked._take_request())
    assert len(old_processes) == 1
    assert old_processes[0].signals == []
    assert old_processes[0].poll() is None
    assert blocked_client.status()["state"] == "failed"


def test_supervisor_reports_port_and_startup_failures_without_touching_unrelated_processes(tmp_path: Path) -> None:
    supervisor, processes = _prepared_supervisor(tmp_path / "port")
    clock = FakeClock()
    supervisor._monotonic = clock.now
    supervisor._sleep = clock.sleep
    supervisor._port_is_free = lambda: False
    client = RestartControlClient(supervisor.runtime_root, supervisor.session_id)
    client.request_restart(RESTART_CONFIRMATION)
    supervisor._restart(supervisor._take_request())
    assert len(processes) == 1
    assert client.status()["state"] == "failed"
    assert "port" in client.status()["message"].lower()

    module = _load_supervisor_module()
    first = FakeProcess()
    calls = 0

    def failing_popen(command, **options):
        nonlocal calls
        calls += 1
        if calls == 1:
            return first
        raise OSError("synthetic start failure")

    clock = FakeClock()
    failed = module.CoreSupervisor(
        runtime_root=tmp_path / "start" / "supervisor",
        popen=failing_popen,
        run=lambda *args, **kwargs: SimpleNamespace(returncode=0),
        sleep=clock.sleep,
        monotonic=clock.now,
        ready_probe=lambda: True,
        ready_timeout=1,
    )
    failed.prepare()
    failed._start_child()
    failed._write_status("running", "Core is running under the local supervisor.")
    failed._port_is_free = lambda: True
    failed_client = RestartControlClient(failed.runtime_root, failed.session_id)
    failed_client.request_restart(RESTART_CONFIRMATION)
    failed._restart(failed._take_request())
    assert calls == 2
    assert failed_client.status()["state"] == "failed"
    assert "could not be started" in failed_client.status()["message"]


def test_launcher_supervisor_contract_is_script_relative_and_has_no_browser_execution_inputs() -> None:
    source = SUPERVISOR_SCRIPT.read_text(encoding="utf-8")
    start_source = (SUPERVISOR_SCRIPT.parent / "start.ps1").read_text(encoding="utf-8")
    assert "Path(__file__).resolve().parents[1]" in source
    assert "len(sys.argv) != 1" in source
    assert '"--host",\n    CORE_HOST' in source
    assert 'CORE_HOST = "127.0.0.1"' in source
    assert 'CORE_PORT = 8000' in source
    assert "Invoke-CoreSupervisor" in start_source
    assert "scripts\\supervise_core.py" in start_source
