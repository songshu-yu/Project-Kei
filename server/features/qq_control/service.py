"""Use cases for safe status, explicit launch, and scheduler configuration."""
from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .repository import QQScheduleRepository, ScheduleStateError

ProcessChecker = Callable[[], bool]
PopenFactory = Callable[..., Any]
Clock = Callable[[], float]

DAILY_DEFAULT = {
    "enabled": False,
    "prebuild_time": "07:00",
    "send_time": "08:00",
    "updated_at": None,
}
LIFE_SUPPORT_DEFAULT = {
    "enabled": False,
    "start_time": "08:00",
    "end_time": "22:00",
    "interval_hours": 2,
    "interval_minutes": 0,
    "updated_at": None,
}


def _is_clock(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.strptime(value, "%H:%M")
    except ValueError:
        return False
    return parsed.strftime("%H:%M") == value


def _has_only_keys(payload: dict[str, Any], allowed: set[str]) -> bool:
    return set(payload).issubset(allowed)


def _is_updated_at(value: object) -> bool:
    if value is None:
        return True
    if not isinstance(value, str) or not value or len(value) > 40:
        return False
    try:
        datetime.fromisoformat(value)
    except ValueError:
        return False
    return True


class QQControlService:
    """Single service shared by versioned and legacy QQ control routes."""

    def __init__(
        self,
        repository: QQScheduleRepository,
        *,
        launcher: str | Path,
        env_path: str | Path,
        dependency_path: str | Path,
        process_checker: ProcessChecker,
        popen_factory: PopenFactory = subprocess.Popen,
        node_checker: Callable[[], bool] | None = None,
        monotonic: Clock = time.monotonic,
    ) -> None:
        self.repository = repository
        self.launcher = Path(launcher)
        self.env_path = Path(env_path)
        self.dependency_path = Path(dependency_path)
        self._process_checker = process_checker
        self._popen_factory = popen_factory
        self._node_checker = node_checker or (lambda: shutil.which("node") is not None)
        self._monotonic = monotonic
        self._launch_lock = threading.RLock()
        self._launched_process: Any = None
        self._launched_at = 0.0

    def _spawned_process_active(self) -> bool:
        return (
            self._launched_process is not None
            and self._launched_process.poll() is None
            and self._monotonic() - self._launched_at < 30.0
        )

    def status(self) -> dict[str, Any]:
        """Read local readiness only; this method never writes or starts anything."""
        with self._launch_lock:
            try:
                running = self._spawned_process_active() or bool(self._process_checker())
            except Exception:
                running = False
            launcher_exists = self.launcher.is_file()
            env_configured = self.env_path.is_file()
            node_ready = bool(self._node_checker())
            dependency_present = self.dependency_path.exists()
            dependencies_ready = node_ready and dependency_present
            if running:
                state, message = "running", "QQ bridge 已在运行，不会重复启动。"
            elif not launcher_exists:
                state, message = "missing_launcher", "未找到 QQ bridge 启动 BAT。"
            elif not env_configured:
                state, message = "missing_env", "QQ bridge 的 .env 尚未配置，请先在本机完成配置。"
            elif not node_ready:
                state, message = "missing_node", "未找到 Node.js，请先在本机安装并重新打开终端。"
            elif not dependency_present:
                state, message = "missing_dependencies", "QQ bridge 依赖尚未安装，请在项目根目录运行 setup.bat --profile qq。"
            else:
                state, message = "ready", "QQ bridge 已就绪，可以从控制台启动。"
            return {
                "running": running,
                "ready": state == "ready",
                "state": state,
                "message": message,
                "launcher_exists": launcher_exists,
                "env_configured": env_configured,
                "node_ready": node_ready,
                "dependencies_ready": dependencies_ready,
            }

    def start(self) -> dict[str, Any]:
        """Start only the project-owned fixed BAT, once, after readiness checks."""
        with self._launch_lock:
            status = self.status()
            if status["running"]:
                return {**status, "started": False}
            if status["state"] != "ready":
                return {**status, "started": False}
            command_processor = os.environ.get("COMSPEC") or "cmd.exe"
            creationflags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
            self._launched_process = self._popen_factory(
                [command_processor, "/d", "/c", str(self.launcher)],
                cwd=str(self.launcher.parent),
                creationflags=creationflags,
            )
            self._launched_at = self._monotonic()
            return {
                **status,
                "running": True,
                "ready": False,
                "state": "starting",
                "message": "已打开 QQ bridge 控制台窗口，正在启动。",
                "started": True,
            }

    def get_daily_schedule(self) -> dict[str, Any]:
        payload = self.repository.read_daily()
        if payload is None:
            return dict(DAILY_DEFAULT)
        return self._validate_daily_state(payload)

    @staticmethod
    def _validate_daily_state(payload: dict[str, Any]) -> dict[str, Any]:
        if not _has_only_keys(payload, {"enabled", "prebuild_time", "send_time", "updated_at"}):
            raise ScheduleStateError("daily_schedule_invalid_fields")
        if not isinstance(payload.get("enabled"), bool):
            raise ScheduleStateError("daily_schedule_invalid_enabled")
        if not _is_clock(payload.get("prebuild_time")) or not _is_clock(payload.get("send_time")):
            raise ScheduleStateError("daily_schedule_invalid")
        if payload["prebuild_time"] >= payload["send_time"]:
            raise ScheduleStateError("daily_schedule_invalid_order")
        updated_at = payload.get("updated_at")
        if not _is_updated_at(updated_at):
            raise ScheduleStateError("daily_schedule_invalid_updated_at")
        return {
            "enabled": payload["enabled"],
            "prebuild_time": payload["prebuild_time"],
            "send_time": payload["send_time"],
            "updated_at": updated_at,
        }

    def update_daily_schedule(self, update: Any) -> dict[str, Any]:
        if not _is_clock(update.prebuild_time) or not _is_clock(update.send_time):
            raise ValueError("时间必须使用 HH:MM 格式")
        if update.prebuild_time >= update.send_time:
            raise ValueError("推送时间必须晚于生成时间，且两者需在同一天")
        return self.repository.replace_daily({
            "enabled": bool(update.enabled),
            "prebuild_time": update.prebuild_time,
            "send_time": update.send_time,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }, validate_existing=self._validate_daily_state)

    def get_life_support_schedule(self) -> dict[str, Any]:
        payload = self.repository.read_life_support()
        if payload is None:
            return dict(LIFE_SUPPORT_DEFAULT)
        return self._validate_life_support_state(payload)

    @staticmethod
    def _validate_life_support_state(payload: dict[str, Any]) -> dict[str, Any]:
        if not _has_only_keys(
            payload,
            {"enabled", "start_time", "end_time", "interval_hours", "interval_minutes", "updated_at"},
        ):
            raise ScheduleStateError("life_support_schedule_invalid_fields")
        if not isinstance(payload.get("enabled"), bool):
            raise ScheduleStateError("life_support_schedule_invalid_enabled")
        raw_hours = payload.get("interval_hours")
        raw_minutes = payload.get("interval_minutes")
        if type(raw_hours) is not int or type(raw_minutes) is not int:
            raise ScheduleStateError("life_support_schedule_invalid_interval")
        hours = raw_hours
        minutes = raw_minutes
        start = payload.get("start_time")
        end = payload.get("end_time")
        if (
            not _is_clock(start)
            or not _is_clock(end)
            or start >= end
            or hours < 0
            or minutes < 0
            or minutes >= 60
            or hours * 60 + minutes <= 0
        ):
            raise ScheduleStateError("life_support_schedule_invalid")
        updated_at = payload.get("updated_at")
        if not _is_updated_at(updated_at):
            raise ScheduleStateError("life_support_schedule_invalid_updated_at")
        return {
            "enabled": payload["enabled"],
            "start_time": start,
            "end_time": end,
            "interval_hours": hours,
            "interval_minutes": minutes,
            "updated_at": updated_at,
        }

    def update_life_support_schedule(self, update: Any) -> dict[str, Any]:
        if not _is_clock(update.start_time) or not _is_clock(update.end_time):
            raise ValueError("时间必须使用 HH:MM 格式")
        if update.start_time >= update.end_time:
            raise ValueError("结束时间必须晚于开始时间，且两者需在同一天")
        if update.interval_hours < 0 or not 0 <= update.interval_minutes < 60:
            raise ValueError("间隔小时必须不小于 0，分钟必须在 0 到 59 之间")
        if update.interval_hours * 60 + update.interval_minutes <= 0:
            raise ValueError("提醒间隔不能为 0 小时 0 分钟")
        return self.repository.replace_life_support({
            "enabled": bool(update.enabled),
            "start_time": update.start_time,
            "end_time": update.end_time,
            "interval_hours": update.interval_hours,
            "interval_minutes": update.interval_minutes,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }, validate_existing=self._validate_life_support_state)
