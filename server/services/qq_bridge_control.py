"""Compatibility facade for the versioned QQ control feature."""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from features.qq_control import QQControlService, QQScheduleRepository

SERVER_ROOT = Path(__file__).resolve().parents[1]
QQ_BRIDGE_ROOT = SERVER_ROOT / "qq_bridge"
DEFAULT_LAUNCHER = QQ_BRIDGE_ROOT / "start_qq_bridge.bat"
DEFAULT_ENV_PATH = QQ_BRIDGE_ROOT / ".env"
DEFAULT_DEPENDENCY_PATH = QQ_BRIDGE_ROOT / "node_modules" / "ws"
DAILY_SCHEDULE_PATH = SERVER_ROOT / "data" / "daily_briefing_schedule.json"
LIFE_SUPPORT_SCHEDULE_PATH = SERVER_ROOT / "data" / "life_support_schedule.json"


def _batch_process_running() -> bool:
    """Check the fixed bridge process without exposing command lines or environment."""
    command = (
        "$launchers = @(Get-CimInstance Win32_Process -Filter \"Name = 'cmd.exe'\" "
        "-ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "
        "'*start_qq_bridge.bat*' }); "
        "$node = Get-CimInstance Win32_Process -Filter \"Name = 'node.exe'\" "
        "-ErrorAction SilentlyContinue | Where-Object { $launchers.ProcessId -contains "
        "$_.ParentProcessId -and $_.CommandLine -like '*src*index.mjs*' } | "
        "Select-Object -First 1; if ($null -ne $node) { Write-Output 'running' }"
    )
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
            creationflags=creationflags,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0 and result.stdout.strip() == "running"


qq_control_service = QQControlService(
    QQScheduleRepository(DAILY_SCHEDULE_PATH, LIFE_SUPPORT_SCHEDULE_PATH),
    launcher=DEFAULT_LAUNCHER,
    env_path=DEFAULT_ENV_PATH,
    dependency_path=DEFAULT_DEPENDENCY_PATH,
    process_checker=_batch_process_running,
)

# Legacy callers injected paths and process doubles directly into these helpers.
# Keep that test/application seam while production continues to use the single
# versioned service above.
_launched_process: Any = None
_launched_at = 0.0


def _uses_default_dependencies(
    launcher: str | Path,
    env_path: str | Path,
    dependency_path: str | Path,
    process_checker: Any,
    popen_factory: Any,
) -> bool:
    return (
        Path(launcher) == DEFAULT_LAUNCHER
        and Path(env_path) == DEFAULT_ENV_PATH
        and Path(dependency_path) == DEFAULT_DEPENDENCY_PATH
        and process_checker is None
        and popen_factory is None
    )


def _compat_service(
    *,
    launcher: str | Path,
    env_path: str | Path,
    dependency_path: str | Path,
    process_checker: Any,
    popen_factory: Any = None,
) -> QQControlService:
    global _launched_process, _launched_at

    checker = process_checker or _batch_process_running
    factory = popen_factory or subprocess.Popen

    if popen_factory is not None:
        def legacy_popen(command: list[str], **kwargs: Any) -> Any:
            normalized = list(command)
            if len(normalized) >= 4 and normalized[1:3] == ["/d", "/c"]:
                normalized = [normalized[0], "/c", normalized[-1]]
            return factory(normalized, **kwargs)
    else:
        legacy_popen = factory

    service = QQControlService(
        QQScheduleRepository(DAILY_SCHEDULE_PATH, LIFE_SUPPORT_SCHEDULE_PATH),
        launcher=launcher,
        env_path=env_path,
        dependency_path=dependency_path,
        process_checker=checker,
        popen_factory=legacy_popen,
        # The legacy seam treated dependency_path as the complete readiness
        # signal and did not expose a separate Node checker.
        node_checker=(lambda: True) if process_checker is not None else None,
    )
    service._launched_process = _launched_process
    service._launched_at = _launched_at
    return service


def qq_bridge_status(
    *,
    launcher: str | Path = DEFAULT_LAUNCHER,
    env_path: str | Path = DEFAULT_ENV_PATH,
    dependency_path: str | Path = DEFAULT_DEPENDENCY_PATH,
    process_checker: Any = None,
) -> dict:
    if _uses_default_dependencies(
        launcher, env_path, dependency_path, process_checker, None
    ):
        return qq_control_service.status()
    return _compat_service(
        launcher=launcher,
        env_path=env_path,
        dependency_path=dependency_path,
        process_checker=process_checker,
    ).status()


def launch_qq_bridge(
    *,
    launcher: str | Path = DEFAULT_LAUNCHER,
    env_path: str | Path = DEFAULT_ENV_PATH,
    dependency_path: str | Path = DEFAULT_DEPENDENCY_PATH,
    process_checker: Any = None,
    popen_factory: Any = None,
) -> dict:
    global _launched_process, _launched_at

    if _uses_default_dependencies(
        launcher, env_path, dependency_path, process_checker, popen_factory
    ):
        result = qq_control_service.start()
        _launched_process = qq_control_service._launched_process
        _launched_at = qq_control_service._launched_at
    else:
        service = _compat_service(
            launcher=launcher,
            env_path=env_path,
            dependency_path=dependency_path,
            process_checker=process_checker,
            popen_factory=popen_factory,
        )
        result = service.start()
        _launched_process = service._launched_process
        _launched_at = service._launched_at
    return {**result, "pid": getattr(_launched_process, "pid", None)}
