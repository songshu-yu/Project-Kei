"""Safe local control for the two fixed Project Kei voice sidecars."""
from __future__ import annotations

import asyncio
import os
import signal
import socket
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .asr_model_directory import AsrModelDirectoryService


PopenFactory = Callable[..., Any]
ReadinessChecker = Callable[[], bool]
PortChecker = Callable[[int], bool]


def local_port_open(port: int) -> bool:
    """Check only the fixed loopback port without sending application data."""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.2):
            return True
    except OSError:
        return False


@dataclass(frozen=True)
class RuntimeTarget:
    key: str
    label: str
    launcher: Path
    port: int
    readiness: ReadinessChecker
    missing_state: str
    missing_message: str


class VoiceRuntimeControlService:
    """Expose read-only readiness and explicit starts for fixed local BAT files."""

    def __init__(
        self,
        *,
        asr_launcher: str | Path,
        gpt_sovits_launcher: str | Path,
        asr_readiness: ReadinessChecker,
        gpt_sovits_readiness: ReadinessChecker,
        port_checker: PortChecker = local_port_open,
        popen_factory: PopenFactory = subprocess.Popen,
        asr_model_directory: AsrModelDirectoryService | None = None,
        stop_timeout_seconds: float = 10.0,
    ) -> None:
        self._targets = {
            "asr": RuntimeTarget(
                key="asr",
                label="ASR",
                launcher=Path(asr_launcher),
                port=8010,
                readiness=asr_readiness,
                missing_state="missing_model",
                missing_message="未找到已配置或项目标准目录中的 ASR 模型。",
            ),
            "gpt-sovits": RuntimeTarget(
                key="gpt-sovits",
                label="GPT-SoVITS",
                launcher=Path(gpt_sovits_launcher),
                port=9880,
                readiness=gpt_sovits_readiness,
                missing_state="missing_registration",
                missing_message="GPT-SoVITS 本机引擎尚未登记。",
            ),
        }
        self._port_checker = port_checker
        self._popen_factory = popen_factory
        self._asr_model_directory = asr_model_directory or AsrModelDirectoryService(
            Path(asr_launcher).parent
            / "data"
            / "modules"
            / "voice"
            / "asr-model.local.json"
        )
        self._lock = threading.RLock()
        self._processes: dict[str, Any] = {}
        self._stop_timeout_seconds = max(0.1, min(float(stop_timeout_seconds), 30.0))

    def _spawned_process_active(self, key: str) -> bool:
        process = self._processes.get(key)
        return process is not None and process.poll() is None

    def _status_unlocked(self, key: str) -> dict[str, Any]:
        target = self._targets[key]
        try:
            owned = self._spawned_process_active(key)
            running = owned or bool(
                self._port_checker(target.port)
            )
        except Exception:
            owned = self._spawned_process_active(key)
            running = owned
        launcher_exists = target.launcher.is_file()
        try:
            configuration_ready = bool(target.readiness())
        except Exception:
            configuration_ready = False
        if key == "asr" and self._asr_model_directory.configured_path() is not None:
            configuration_ready = True

        if running:
            state = "running"
            message = f"{target.label} 已在运行，不会重复启动。"
        elif not launcher_exists:
            state = "missing_launcher"
            message = f"未找到 {target.label} 固定启动 BAT。"
        elif not configuration_ready:
            state = target.missing_state
            message = target.missing_message
        else:
            state = "ready"
            message = f"{target.label} 已就绪，可以从控制台启动。"
        return {
            "running": running,
            "ready": state == "ready",
            "state": state,
            "message": message,
            "launcher_exists": launcher_exists,
            "configuration_ready": configuration_ready,
            "owned": owned,
            "can_stop": owned,
        }

    def status(self) -> dict[str, dict[str, Any]]:
        """Read fixed local readiness without starting or writing anything."""
        with self._lock:
            return {
                key: self._status_unlocked(key)
                for key in ("asr", "gpt-sovits")
            }

    def asr_model_selection_status(self) -> dict[str, Any]:
        """Return only safe selection state; the stored path remains private."""
        return self._asr_model_directory.status()

    async def select_asr_model_directory(self) -> dict[str, Any]:
        """Open the native picker outside the event loop after an explicit POST."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._asr_model_directory.select)

    def start(self, key: str) -> dict[str, Any]:
        """Start exactly one known launcher in a new console, once."""
        return self._start(key, background=False)

    def start_background(self, key: str) -> dict[str, Any]:
        """Start one fixed launcher without a visible console window, once."""
        return self._start(key, background=True)

    def _start(self, key: str, *, background: bool) -> dict[str, Any]:
        if key not in self._targets:
            raise KeyError("unsupported_voice_runtime")
        with self._lock:
            status = self._status_unlocked(key)
            if status["running"]:
                return {**status, "started": False}
            if status["state"] != "ready":
                return {**status, "started": False}

            target = self._targets[key]
            command_processor = os.environ.get("COMSPEC") or "cmd.exe"
            creationflags = (
                getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                | getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
            )
            spawn_kwargs = {
                "cwd": str(target.launcher.parent),
                "creationflags": creationflags,
            }
            if background and os.name == "nt" and hasattr(subprocess, "STARTUPINFO"):
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 0)
                startupinfo.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
                spawn_kwargs["startupinfo"] = startupinfo
            if key == "asr" and not os.environ.get("ASR_MODEL_PATH", "").strip():
                configured_path = self._asr_model_directory.configured_path()
                if configured_path is not None:
                    environment = os.environ.copy()
                    environment["ASR_MODEL_PATH"] = str(configured_path)
                    spawn_kwargs["env"] = environment
            process = self._popen_factory(
                [command_processor, "/d", "/c", str(target.launcher)],
                **spawn_kwargs,
            )
            self._processes[key] = process
            return {
                **status,
                "running": True,
                "ready": False,
                "state": "starting",
                "message": (
                    f"{target.label} 正在后台启动。"
                    if background
                    else f"已打开 {target.label} 调试窗口，正在启动。"
                ),
                "started": True,
                "owned": True,
                "can_stop": True,
            }

    def stop(self, key: str) -> dict[str, Any]:
        """Stop only the fixed runtime process group started by this service."""
        if key not in self._targets:
            raise KeyError("unsupported_voice_runtime")
        with self._lock:
            status = self._status_unlocked(key)
            if not status["running"]:
                return {**status, "stopped": False}
            if not status["can_stop"]:
                return {
                    **status,
                    "state": "external_running",
                    "message": "服务正在运行，但不是由当前控制台启动，不能从这里关闭。",
                    "stopped": False,
                }

            process = self._processes[key]
            try:
                if os.name == "nt":
                    process.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    process.terminate()
                process.wait(timeout=self._stop_timeout_seconds)
            except Exception:
                return {
                    **status,
                    "state": "stop_failed",
                    "message": "服务未能在限定时间内安全关闭。",
                    "stopped": False,
                }
            if process.poll() is None:
                return {
                    **status,
                    "state": "stop_failed",
                    "message": "服务未能在限定时间内安全关闭。",
                    "stopped": False,
                }
            self._processes.pop(key, None)
            final_status = self._status_unlocked(key)
            if final_status["running"]:
                return {
                    **final_status,
                    "state": "stop_failed",
                    "message": "受控进程已退出，但固定本机端口仍由其他实例占用。",
                    "stopped": False,
                }
            return {**final_status, "stopped": True}


__all__ = ["VoiceRuntimeControlService", "local_port_open"]
