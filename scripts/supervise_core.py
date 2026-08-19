"""Own and restart the fixed Project Kei Core child process.

This program is launched only by scripts/start.ps1.  It accepts no command
line arguments: the executable, module, bind address, port, working directory,
and control directory are all derived from this installed file and the current
Python runtime.
"""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Callable
from urllib.request import ProxyHandler, build_opener


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SERVER_ROOT = PROJECT_ROOT / "server"
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from core.restart_supervisor import (  # noqa: E402
    PROTOCOL_VERSION,
    REQUEST_ID_PATTERN,
    SUPERVISOR_ENV,
    _atomic_json,
    _is_link_or_reparse,
    _read_object,
)


CORE_HOST = "127.0.0.1"
CORE_PORT = 8000
CORE_COMMAND = (
    sys.executable,
    "-B",
    "-m",
    "uvicorn",
    "api:app",
    "--host",
    CORE_HOST,
    "--port",
    str(CORE_PORT),
)


class CoreSupervisor:
    def __init__(
        self,
        *,
        runtime_root: Path = SERVER_ROOT / "runtime" / "supervisor",
        popen: Callable[..., Any] = subprocess.Popen,
        run: Callable[..., Any] = subprocess.run,
        sleep: Callable[[float], None] = time.sleep,
        ready_timeout: float = 30.0,
        ready_probe: Callable[[], bool] | None = None,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.runtime_root = Path(runtime_root)
        self.session_id = uuid.uuid4().hex
        self.session = self.runtime_root / self.session_id
        self._popen = popen
        self._run = run
        self._sleep = sleep
        self._ready_timeout = ready_timeout
        self._ready_probe = ready_probe or self._default_ready_probe
        self._monotonic = monotonic
        self._generation = 0
        self._child: Any | None = None

    @property
    def child(self) -> Any | None:
        return self._child

    def _write_status(self, state: str, message: str, request_id: str | None = None) -> None:
        _atomic_json(self.session / "status.json", {
            "schema_version": PROTOCOL_VERSION,
            "state": state,
            "scope": "core",
            "request_id": request_id,
            "generation": self._generation,
            "message": message,
        })

    def prepare(self) -> None:
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        if _is_link_or_reparse(self.runtime_root):
            raise RuntimeError("supervisor_runtime_root_is_link")
        self.session.mkdir(mode=0o700)
        _atomic_json(self.session / "session.json", {
            "schema_version": PROTOCOL_VERSION,
            "session_id": self.session_id,
            "scope": "core",
        })
        self._write_status("starting", "Core is starting under the local supervisor.")

    @staticmethod
    def _default_ready_probe() -> bool:
        opener = build_opener(ProxyHandler({}))
        try:
            with opener.open("http://127.0.0.1:8000/", timeout=0.75) as response:
                return 200 <= int(response.status) < 500
        except Exception:
            return False

    @staticmethod
    def _port_is_free() -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(0.2)
            return probe.connect_ex((CORE_HOST, CORE_PORT)) != 0

    def _environment(self) -> dict[str, str]:
        environment = dict(os.environ)
        environment[SUPERVISOR_ENV] = self.session_id
        current = environment.get("PYTHONPATH", "")
        environment["PYTHONPATH"] = str(SERVER_ROOT) + (os.pathsep + current if current else "")
        environment["PYTHONIOENCODING"] = "utf-8"
        return environment

    def _start_child(self) -> Any:
        options: dict[str, Any] = {
            "cwd": str(SERVER_ROOT),
            "env": self._environment(),
        }
        if os.name == "nt":
            options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        self._child = self._popen(list(CORE_COMMAND), **options)
        return self._child

    def _wait_ready(self) -> bool:
        deadline = self._monotonic() + self._ready_timeout
        while self._monotonic() < deadline:
            if self._child is None or self._child.poll() is not None:
                return False
            if self._ready_probe():
                return True
            self._sleep(0.1)
        return False

    def _preflight(self) -> bool:
        result = self._run(
            [sys.executable, "-B", "-c", "import fastapi,uvicorn,api"],
            cwd=str(SERVER_ROOT),
            env=self._environment(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return int(result.returncode) == 0

    def _stop_child(self) -> bool:
        child = self._child
        if child is None or child.poll() is not None:
            return True
        try:
            if os.name == "nt":
                child.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                child.send_signal(signal.SIGINT)
            child.wait(timeout=10)
            return True
        except Exception:
            try:
                child.terminate()
                child.wait(timeout=5)
                return True
            except Exception:
                return False

    def _take_request(self) -> dict[str, Any] | None:
        path = self.session / "request.json"
        try:
            request = _read_object(
                path,
                allowed_keys={"schema_version", "action", "session_id", "request_id"},
            )
        except FileNotFoundError:
            return None
        except Exception:
            path.unlink(missing_ok=True)
            return None
        expected = {
            "schema_version": PROTOCOL_VERSION,
            "action": "restart_core",
            "session_id": self.session_id,
        }
        if any(request.get(key) != value for key, value in expected.items()):
            path.unlink(missing_ok=True)
            return None
        request_id = request.get("request_id")
        if not isinstance(request_id, str) or not REQUEST_ID_PATTERN.fullmatch(request_id):
            path.unlink(missing_ok=True)
            return None
        return request

    def _finish_request(self) -> None:
        (self.session / "request.json").unlink(missing_ok=True)

    def _restart(self, request: dict[str, Any]) -> None:
        request_id = request["request_id"]
        if not self._preflight():
            self._finish_request()
            self._write_status("failed", "Core restart preflight failed; the running Core was left unchanged.", request_id)
            return
        self._write_status("restarting", "Core is restarting.", request_id)
        if not self._stop_child():
            self._finish_request()
            self._write_status("failed", "Core could not be stopped safely; no replacement was started.", request_id)
            return
        deadline = self._monotonic() + 10
        while self._monotonic() < deadline and not self._port_is_free():
            self._sleep(0.1)
        if not self._port_is_free():
            self._finish_request()
            self._write_status("failed", "Core port did not become available; no unrelated process was stopped.", request_id)
            return
        self._finish_request()
        self._generation += 1
        try:
            self._start_child()
        except Exception:
            self._write_status("failed", "The replacement Core process could not be started.", request_id)
            return
        if self._wait_ready():
            self._write_status("running", "Core restart completed.", request_id)
        else:
            self._stop_child()
            self._write_status("failed", "The replacement Core process did not become ready.", request_id)

    def run(self) -> int:
        self.prepare()
        try:
            self._start_child()
            if not self._wait_ready():
                self._stop_child()
                self._write_status("failed", "Core did not become ready.")
                return 23
            self._write_status("running", "Core is running under the local supervisor.")
            while True:
                if self._child is None or self._child.poll() is not None:
                    code = 1 if self._child is None else int(self._child.returncode or 0)
                    self._write_status("failed", "Core exited; the supervisor did not restart it without a request.")
                    return code
                request = self._take_request()
                if request is not None:
                    self._restart(request)
                self._sleep(0.2)
        except KeyboardInterrupt:
            self._stop_child()
            return 130


def main() -> int:
    if len(sys.argv) != 1:
        print("[error] supervisor accepts no command-line arguments", file=sys.stderr)
        return 2
    return CoreSupervisor().run()


if __name__ == "__main__":
    raise SystemExit(main())
