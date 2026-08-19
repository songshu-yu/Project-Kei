"""Loopback-only HTTP adapter for an injected voice runtime controller."""
from __future__ import annotations

import inspect
from collections.abc import Mapping
from typing import Any, Callable

from fastapi import APIRouter, HTTPException, Request


RequestGuard = Callable[[Request], bool]
ProviderSource = Any
TARGETS = ("asr", "gpt-sovits")
PUBLIC_STATES = frozenset({
    "failed",
    "external_running",
    "missing_launcher",
    "missing_model",
    "missing_registration",
    "ready",
    "running",
    "starting",
    "stop_failed",
    "unavailable",
})
SELECTION_STATES = frozenset({
    "cancelled",
    "configured",
    "invalid_configuration",
    "invalid_model",
    "picker_failed",
    "save_failed",
    "selection_in_progress",
    "unavailable",
    "unconfigured",
})


def _state_message(target: str, state: str) -> str:
    label = "ASR" if target == "asr" else "GPT-SoVITS"
    messages = {
        "failed": f"{label} 启动失败。",
        "external_running": f"{label} 正在运行，但不是由当前控制台启动。",
        "missing_launcher": f"{label} 固定启动入口不可用。",
        "missing_model": "ASR 模型尚未配置。",
        "missing_registration": "GPT-SoVITS 本机引擎尚未登记。",
        "ready": f"{label} 已就绪，可以显式启动。",
        "running": f"{label} 已在运行。",
        "starting": f"{label} 正在启动。",
        "stop_failed": f"{label} 未能安全关闭。",
        "unavailable": f"{label} 运行时控制能力未安装。",
    }
    return messages[state]


def _unavailable_target(target: str) -> dict[str, Any]:
    return {
        "running": False,
        "ready": False,
        "state": "unavailable",
        "message": _state_message(target, "unavailable"),
        "launcher_exists": False,
        "configuration_ready": False,
        "owned": False,
        "can_stop": False,
    }


def _public_target_status(target: str, value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return _unavailable_target(target)
    state = value.get("state")
    if state not in PUBLIC_STATES:
        return _unavailable_target(target)
    public = {
        "running": value.get("running") is True,
        "ready": value.get("ready") is True,
        "state": state,
        "message": _state_message(target, state),
        "launcher_exists": value.get("launcher_exists") is True,
        "configuration_ready": value.get("configuration_ready") is True,
        "owned": value.get("owned") is True,
        "can_stop": value.get("can_stop") is True,
    }
    if "started" in value:
        public["started"] = value.get("started") is True
    if "stopped" in value:
        public["stopped"] = value.get("stopped") is True
    return public


def _resolve_provider(source: ProviderSource) -> Any:
    provider = source
    if (
        callable(source)
        and not callable(getattr(source, "status", None))
        and not callable(getattr(source, "start", None))
    ):
        try:
            provider = source()
        except Exception:
            return None
    if not callable(getattr(provider, "status", None)):
        return None
    if not callable(getattr(provider, "start", None)):
        return None
    return provider


def _provider_status(source: ProviderSource) -> dict[str, dict[str, Any]]:
    provider = _resolve_provider(source)
    if provider is None:
        return {target: _unavailable_target(target) for target in TARGETS}
    try:
        value = provider.status()
    except Exception:
        value = None
    if not isinstance(value, Mapping):
        return {target: _unavailable_target(target) for target in TARGETS}
    return {
        target: _public_target_status(target, value.get(target))
        for target in TARGETS
    }


def _selection_message(state: str) -> str:
    return {
        "cancelled": "已取消选择，原配置保持不变。",
        "configured": "ASR 模型目录已验证并配置。",
        "invalid_configuration": "已保存的 ASR 模型目录当前无效。",
        "invalid_model": "所选目录不是可用的 ASR 模型目录，原配置保持不变。",
        "picker_failed": "无法打开本机目录选择器。",
        "save_failed": "ASR 模型目录保存失败，原配置保持不变。",
        "selection_in_progress": "另一个 ASR 目录选择正在进行。",
        "unavailable": "本机 ASR 目录选择能力不可用。",
        "unconfigured": "尚未配置 ASR 模型目录。",
    }[state]


def _unavailable_selection() -> dict[str, Any]:
    return {
        "available": False,
        "configured": False,
        "state": "unavailable",
        "directory_name": None,
        "message": _selection_message("unavailable"),
    }


def _public_selection_status(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or value.get("state") not in SELECTION_STATES:
        return _unavailable_selection()
    state = value["state"]
    name = value.get("directory_name")
    if not isinstance(name, str) or not name.strip():
        name = None
    else:
        name = name.strip()[:80]
        if name in {".", ".."} or "/" in name or "\\" in name or ":" in name:
            name = None
    return {
        "available": value.get("available") is True,
        "configured": value.get("configured") is True,
        "state": state,
        "directory_name": name,
        "message": _selection_message(state),
    }


def _provider_selection_status(source: ProviderSource) -> dict[str, Any]:
    provider = _resolve_provider(source)
    method = getattr(provider, "asr_model_selection_status", None)
    if not callable(method):
        return _unavailable_selection()
    try:
        return _public_selection_status(method())
    except Exception:
        return _unavailable_selection()


def create_voice_control_router(
    provider_source: ProviderSource,
    *,
    read_guard: RequestGuard,
    write_guard: RequestGuard,
) -> APIRouter:
    router = APIRouter(tags=["voice-control"])

    def require_read(request: Request) -> None:
        if not read_guard(request):
            raise HTTPException(status_code=403, detail="local_loopback_required")

    def require_write(request: Request) -> None:
        if not write_guard(request):
            raise HTTPException(status_code=403, detail="local_trusted_origin_required")

    async def start_target(request: Request, target: str, *, background: bool = False):
        require_write(request)
        if (await request.body()).strip():
            raise HTTPException(status_code=422, detail="invalid_request")
        provider = _resolve_provider(provider_source)
        if provider is None:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "voice_runtime_control_unavailable",
                    "target": target,
                },
            )
        method = getattr(provider, "start_background" if background else "start", None)
        if not callable(method):
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "voice_runtime_background_start_unavailable"
                    if background else "voice_runtime_control_unavailable",
                    "target": target,
                },
            )
        try:
            raw_result = method(target)
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"{target}_start_failed",
            ) from exc
        result = _public_target_status(target, raw_result)
        if not result["running"]:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": f"{target}_not_ready",
                    "target": target,
                    "state": result["state"],
                    "message": result["message"],
                },
            )
        return result

    async def stop_target(request: Request, target: str):
        require_write(request)
        if (await request.body()).strip():
            raise HTTPException(status_code=422, detail="invalid_request")
        provider = _resolve_provider(provider_source)
        method = getattr(provider, "stop", None)
        if not callable(method):
            raise HTTPException(
                status_code=503,
                detail={"code": "voice_runtime_stop_unavailable", "target": target},
            )
        try:
            raw_result = method(target)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"{target}_stop_failed") from exc
        result = _public_target_status(target, raw_result)
        if result.get("stopped") is not True:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": f"{target}_not_stopped",
                    "target": target,
                    "state": result["state"],
                    "message": result["message"],
                },
            )
        return result

    async def select_asr_model_directory(request: Request):
        require_write(request)
        if (await request.body()).strip():
            raise HTTPException(status_code=422, detail="invalid_request")
        provider = _resolve_provider(provider_source)
        method = getattr(provider, "select_asr_model_directory", None)
        if not callable(method):
            raise HTTPException(
                status_code=503,
                detail={"code": "asr_model_directory_selection_unavailable"},
            )
        try:
            value = method()
            if inspect.isawaitable(value):
                value = await value
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail="asr_model_directory_selection_failed",
            ) from exc
        result = _public_selection_status(value)
        status_codes = {
            "invalid_model": 422,
            "selection_in_progress": 409,
            "save_failed": 500,
            "picker_failed": 500,
            "unavailable": 503,
        }
        status_code = status_codes.get(result["state"])
        if status_code is not None:
            raise HTTPException(status_code=status_code, detail=result)
        return result

    @router.get("/api/v1/voice-control/status")
    async def status(request: Request):
        require_read(request)
        return _provider_status(provider_source)

    @router.post("/api/v1/voice-control/asr/start")
    async def start_asr(request: Request):
        return await start_target(request, "asr")

    @router.post("/api/v1/voice-control/asr/start-background")
    async def start_asr_background(request: Request):
        return await start_target(request, "asr", background=True)

    @router.post("/api/v1/voice-control/asr/stop")
    async def stop_asr(request: Request):
        return await stop_target(request, "asr")

    @router.get("/api/v1/voice-control/asr/model-directory/status")
    async def asr_model_directory_status(request: Request):
        require_read(request)
        return _provider_selection_status(provider_source)

    @router.post("/api/v1/voice-control/asr/model-directory/select")
    async def select_asr_model(request: Request):
        return await select_asr_model_directory(request)

    @router.post("/api/v1/voice-control/gpt-sovits/start")
    async def start_tts_runtime(request: Request):
        return await start_target(request, "gpt-sovits")

    @router.post("/api/v1/voice-control/gpt-sovits/start-background")
    async def start_tts_runtime_background(request: Request):
        return await start_target(request, "gpt-sovits", background=True)

    @router.post("/api/v1/voice-control/gpt-sovits/stop")
    async def stop_tts_runtime(request: Request):
        return await stop_target(request, "gpt-sovits")

    return router


__all__ = ["create_voice_control_router"]
