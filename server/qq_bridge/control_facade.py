"""QQ control facade backed by the installed sidecar lifecycle adapter.

The facade owns no paths or commands. Production composition supplies the
process-wide ModuleManager, the exact adapter registered on that manager and
the existing schedule service. Versioned and legacy routers can therefore keep
one schedule repository while status/start use the same installed deployment
as the module lifecycle.
"""

from __future__ import annotations

import threading
import re
import inspect
from typing import Any

from .configuration import (
    QQBridgeConfigurationStore,
    QQConfigurationError,
    create_qq_media_capability_provider,
)
from .module_adapter import MODULE_ID, QQBridgeAdapterError, QQBridgeSidecarAdapter


_STATE_MESSAGES = {
    "running": "QQ is connected and the bridge is receiving events.",
    "connecting": "QQ bridge process is running and connecting to QQ.",
    "identified_or_ready": "QQ bridge identified; waiting for a healthy heartbeat.",
    "reconnect_wait": "QQ bridge is waiting to reconnect.",
    "gateway_failed": "QQ bridge process is running, but the QQ connection failed.",
    "gateway_unavailable": "QQ bridge process is running, but no fresh connection status is available.",
    "stopped": "QQ bridge is enabled and waiting for manual start.",
    "ready": "QQ bridge is enabled and waiting for manual start.",
    "missing_module": "QQ bridge module is not installed.",
    "missing_env": "QQ bridge configuration is missing.",
    "missing_node": "The supported Node.js runtime is unavailable.",
    "missing_dependencies": "QQ bridge dependencies are unavailable.",
    "missing_package": "The installed QQ bridge package is unavailable.",
    "unavailable": "QQ bridge readiness is unavailable.",
    "start_failed": "QQ bridge could not be started.",
    "shutdown_channel_unavailable": "QQ bridge is running outside this controller and cannot be stopped here.",
    "shutdown_failed": "QQ bridge did not stop through its controlled shutdown channel.",
}
_GATEWAY_ERROR_MESSAGES = {
    "gateway_failed": "QQ Gateway failed; retry is bounded.",
    "gateway_hello_timeout": "QQ Gateway Hello timed out; retry is bounded.",
    "gateway_request_failed": "QQ Gateway discovery request failed; retry is bounded.",
    "gateway_rejected": "QQ Gateway discovery was rejected; check QQ application access.",
    "gateway_response_invalid": "QQ Gateway discovery returned an invalid response.",
    "gateway_ready_timeout": "QQ Gateway READY timed out; retry is bounded.",
    "gateway_url_invalid": "QQ Gateway returned an invalid endpoint.",
    "gateway_url_missing": "QQ Gateway response did not include an endpoint.",
    "gateway_url_rejected": "QQ Gateway returned an endpoint outside the allowlist.",
    "heartbeat_send_failed": "QQ Gateway heartbeat could not be sent.",
    "heartbeat_timeout": "QQ Gateway heartbeat timed out; retry is bounded.",
    "identify_send_failed": "QQ Gateway identify could not be sent.",
    "invalid_session": "QQ Gateway rejected the session; retry is bounded.",
    "server_reconnect": "QQ Gateway requested a reconnect.",
    "token_rejected": "QQ access token was rejected; check QQ application credentials.",
    "token_request_failed": "QQ access token request failed; retry is bounded.",
    "token_response_invalid": "QQ access token response was invalid.",
    "websocket_closed": "QQ Gateway WebSocket closed before becoming ready.",
    "websocket_constructor_failed": "QQ Gateway WebSocket could not be created.",
    "websocket_error": "QQ Gateway WebSocket connection failed.",
}
_VOICE_RESULT_MESSAGES = {
    "voice_sent": "The QQ voice reply was sent.",
    "voice_disabled": "QQ voice replies are disabled.",
    "voice_text_invalid": "The reply text was not eligible for voice synthesis.",
    "voice_unavailable": "The Project Kei voice profile was unavailable.",
    "voice_duplicate": "This QQ voice reply was already claimed or sent.",
    "voice_cancelled": "The QQ voice reply was cancelled during shutdown.",
    "voice_metadata_invalid": "The synthesized voice metadata was invalid.",
    "voice_audio_invalid": "The synthesized Silk audio was invalid.",
    "voice_audio_too_large": "The synthesized voice exceeded the local size limit.",
    "voice_upload_failed": "QQ rejected or could not receive the voice upload.",
    "voice_file_info_invalid": "QQ returned invalid voice upload metadata.",
    "voice_message_failed": "QQ did not accept the uploaded voice message.",
    "voice_delivery_failed": "The QQ voice reply failed at a protected delivery stage.",
}
_REMINDER_TOPICS = {
    "hydrate": "喝水补充水分",
    "move": "起身走动和活动身体",
    "stretch": "拉伸肩颈和腰背",
    "eyes": "离开屏幕并眺望远处",
    "rest": "短暂休息并调整状态",
}
_EMOTION_PREFIX = re.compile(r"^\s*\[emotion:[^\]\r\n]{1,32}\]\s*", re.IGNORECASE)
_QQ_MEDIA_CAPABILITIES = {"unknown", "available", "unavailable", "denied"}
_VOICE_PROFILE = "qq_c2c_voice_v1"


class QQControlAdapterFacade:
    """Expose finite status/start results and delegate schedules unchanged."""

    def __init__(
        self,
        manager: Any,
        adapter: QQBridgeSidecarAdapter,
        schedule_service: Any,
        text_generator_provider: Any = None,
        configuration_store: QQBridgeConfigurationStore | None = None,
        voice_health_provider: Any = None,
        qq_media_capability_provider: Any = None,
    ) -> None:
        self._manager = manager
        self._adapter = adapter
        self._schedule_service = schedule_service
        self._text_generator_provider = text_generator_provider
        if configuration_store is None:
            configuration_path = getattr(adapter, "configuration_path", None)
            configuration_store = (
                QQBridgeConfigurationStore(configuration_path)
                if configuration_path is not None
                else None
            )
        self._configuration_store = configuration_store
        self._voice_health_provider = voice_health_provider
        self._qq_media_capability_provider = (
            qq_media_capability_provider
            if qq_media_capability_provider is not None
            else (
                create_qq_media_capability_provider(configuration_store)
                if configuration_store is not None
                else None
            )
        )
        self._lock = threading.RLock()

    @staticmethod
    def _result(
        state: str,
        *,
        running: bool = False,
        started: bool | None = None,
        snapshot: Any = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "running": running,
            "process_running": running,
            "gateway_ready": bool(getattr(snapshot, "gateway_ready", False)),
            "gateway_state": str(getattr(snapshot, "gateway_state", "stopped")),
            "ready": state == "ready",
            "state": state,
            "message": _STATE_MESSAGES[state],
            "launcher_exists": bool(
                getattr(snapshot, "package_ready", False)
            ),
            "env_configured": bool(
                getattr(snapshot, "env_configured", False)
            ),
            "node_ready": bool(getattr(snapshot, "node_ready", False)),
            "dependencies_ready": bool(
                getattr(snapshot, "dependencies_ready", False)
            ),
            "can_stop": bool(getattr(snapshot, "can_stop", False)),
        }
        error_code = getattr(snapshot, "gateway_last_error_code", None)
        close_code = getattr(snapshot, "gateway_last_close_code", None)
        last_ready_at = getattr(snapshot, "gateway_last_ready_at", None)
        payload["gateway_last_error_code"] = (
            error_code if error_code in _GATEWAY_ERROR_MESSAGES else None
        )
        payload["gateway_message"] = (
            _GATEWAY_ERROR_MESSAGES.get(error_code)
            if isinstance(error_code, str)
            else None
        )
        payload["gateway_last_close_code"] = (
            close_code if isinstance(close_code, int) else None
        )
        payload["gateway_reconnect_count"] = int(
            getattr(snapshot, "gateway_reconnect_count", 0) or 0
        )
        payload["gateway_last_ready_at"] = (
            last_ready_at if isinstance(last_ready_at, int) else None
        )
        voice_code = getattr(snapshot, "voice_last_result_code", None)
        voice_attempt_at = getattr(snapshot, "voice_last_attempt_at", None)
        payload["voice_last_result_code"] = (
            voice_code if voice_code in _VOICE_RESULT_MESSAGES else None
        )
        payload["voice_message"] = (
            _VOICE_RESULT_MESSAGES.get(voice_code)
            if isinstance(voice_code, str)
            else None
        )
        payload["voice_last_attempt_at"] = (
            voice_attempt_at if isinstance(voice_attempt_at, int) else None
        )
        if started is not None:
            payload["started"] = started
        return payload

    def _deployment(self):
        try:
            return self._manager.resolve_sidecar_deployment(MODULE_ID)
        except Exception:
            return None

    def status(self) -> dict[str, Any]:
        """Read adapter readiness only; never start, write or access QQ data."""

        with self._lock:
            deployment = self._deployment()
            if deployment is None:
                return self._result("missing_module")
            try:
                snapshot = self._adapter.inspect(
                    deployment.package_root,
                    deployment.dependency_deployment_root,
                    deployment,
                )
            except Exception:
                return self._result("unavailable")
            state = {
                "running": "running",
                "connecting": "connecting",
                "identified_or_ready": "identified_or_ready",
                "reconnect_wait": "reconnect_wait",
                "failed": "gateway_failed",
                "gateway_unavailable": "gateway_unavailable",
                "stopped": "stopped",
                "ready": "ready",
                "needs_configuration": "missing_env",
                "node_missing": "missing_node",
                "dependencies_missing": "missing_dependencies",
                "deployment_missing": "missing_dependencies",
                "deployment_invalid": "unavailable",
                "integrity_mismatch": "unavailable",
                "package_invalid": "missing_package",
            }.get(snapshot.state, "unavailable")
            return self._result(
                state,
                running=bool(
                    getattr(snapshot, "process_running", getattr(snapshot, "running", False))
                ),
                snapshot=snapshot,
            )

    def start(self) -> dict[str, Any]:
        """Start once through the registered adapter and current descriptor."""

        with self._lock:
            status = self.status()
            if status["running"]:
                return {**status, "started": False}
            if status["state"] != "ready":
                return {**status, "started": False}
            deployment = self._deployment()
            if deployment is None:
                return self._result("missing_module", started=False)
            try:
                description = self._manager.get(MODULE_ID)
                if description.get("enabled"):
                    self._adapter.start_deployment(None, deployment)
                else:
                    self._manager.enable(MODULE_ID)
                    deployment = self._deployment()
                    if deployment is None:
                        return self._result("missing_module", started=False)
                    self._adapter.start_deployment(None, deployment)
                if not self._adapter.is_deployment_healthy(None, deployment):
                    return self._result("start_failed", started=False)
            except Exception:
                return self._result("start_failed", started=False)
            return {**self.status(), "started": True}

    def stop(self) -> dict[str, Any]:
        """Stop only the bridge process owned by this adapter instance."""
        with self._lock:
            status = self.status()
            if not status["running"]:
                return {**status, "stopped": False}
            if not status.get("can_stop"):
                return self._result(
                    "shutdown_channel_unavailable",
                    running=True,
                ) | {"stopped": False}
            deployment = self._deployment()
            if deployment is None:
                return self._result("missing_module") | {"stopped": False}
            try:
                self._adapter.stop_deployment(None, deployment)
            except QQBridgeAdapterError as exc:
                state = (
                    exc.code
                    if exc.code in {"shutdown_channel_unavailable", "shutdown_failed"}
                    else "shutdown_failed"
                )
                return self._result(state, running=True) | {"stopped": False}
            except Exception:
                return self._result("shutdown_failed", running=True) | {"stopped": False}
            return {**self.status(), "stopped": True}

    def get_daily_schedule(self):
        return self._schedule_service.get_daily_schedule()

    def update_daily_schedule(self, update):
        return self._schedule_service.update_daily_schedule(update)

    def get_life_support_schedule(self):
        return self._schedule_service.get_life_support_schedule()

    def update_life_support_schedule(self, update):
        return self._schedule_service.update_life_support_schedule(update)

    @staticmethod
    def _provider_value(provider: Any) -> Any:
        if callable(provider):
            return provider()
        return provider

    @staticmethod
    def _voice_readiness_values(health: Any, raw_capability: Any) -> dict[str, Any]:
        profile_ready = False
        try:
            profile = (
                health.get("synthesis_profiles", {}).get(_VOICE_PROFILE, {})
                if isinstance(health, dict)
                else {}
            )
            profile_ready = bool(
                isinstance(profile, dict)
                and profile.get("available") is True
                and profile.get("content_type") == "audio/silk"
                and profile.get("final") is True
                and isinstance(profile.get("max_bytes"), int)
                and 0 < profile["max_bytes"] <= 8 * 1024 * 1024
                and isinstance(profile.get("max_duration_seconds"), (int, float))
                and not isinstance(profile.get("max_duration_seconds"), bool)
                and 0 < profile["max_duration_seconds"] <= 60
            )
        except Exception:
            profile_ready = False
        try:
            capability = str(raw_capability or "unknown").lower()
        except Exception:
            capability = "unknown"
        if capability not in _QQ_MEDIA_CAPABILITIES:
            capability = "unknown"
        available = profile_ready and capability == "available"
        if available:
            state = "available"
        elif not profile_ready:
            state = "encoding_unavailable"
        else:
            state = f"qq_media_{capability}"
        return {
            "voice_profile": _VOICE_PROFILE,
            "voice_profile_ready": profile_ready,
            "qq_media_upload_capability": capability,
            "voice_reply_available": available,
            "voice_reply_state": state,
        }

    def _voice_readiness(self, capability_override: str | None = None) -> dict[str, Any]:
        try:
            health = self._provider_value(self._voice_health_provider)
            capability = (
                capability_override
                if capability_override is not None
                else self._provider_value(self._qq_media_capability_provider)
            )
            if inspect.isawaitable(health) or inspect.isawaitable(capability):
                if inspect.iscoroutine(health):
                    health.close()
                if inspect.iscoroutine(capability):
                    capability.close()
                return self._voice_readiness_values(None, "unknown")
            return self._voice_readiness_values(health, capability)
        except Exception:
            return self._voice_readiness_values(None, "unknown")

    async def _voice_readiness_async(
        self, capability_override: str | None = None
    ) -> dict[str, Any]:
        try:
            health = self._provider_value(self._voice_health_provider)
            capability = (
                capability_override
                if capability_override is not None
                else self._provider_value(self._qq_media_capability_provider)
            )
            if inspect.isawaitable(health):
                health = await health
            if inspect.isawaitable(capability):
                capability = await capability
            return self._voice_readiness_values(health, capability)
        except Exception:
            return self._voice_readiness_values(None, "unknown")

    def get_configuration(self) -> dict[str, Any]:
        if self._configuration_store is None:
            raise RuntimeError("configuration_unavailable")
        return {**self._configuration_store.status(), **self._voice_readiness()}

    async def get_configuration_async(self) -> dict[str, Any]:
        if self._configuration_store is None:
            raise RuntimeError("configuration_unavailable")
        return {
            **self._configuration_store.status(),
            **await self._voice_readiness_async(),
        }

    def update_configuration(
        self,
        *,
        appid: str | None,
        secret: str | None,
        reply_with_voice: bool | None = None,
        qq_media_upload_capability: str | None = None,
        life_forecast_enabled: bool | None = None,
    ) -> dict[str, Any]:
        if self._configuration_store is None:
            raise RuntimeError("configuration_unavailable")
        readiness = self._voice_readiness(qq_media_upload_capability)
        if reply_with_voice is True and not readiness["voice_reply_available"]:
            raise QQConfigurationError("voice_unavailable")
        saved = self._configuration_store.update(
            appid=appid,
            secret=secret,
            reply_with_voice=reply_with_voice,
            qq_media_upload_capability=qq_media_upload_capability,
            life_forecast_enabled=life_forecast_enabled,
        )
        return {**saved, **self._voice_readiness()}

    async def update_configuration_async(
        self,
        *,
        appid: str | None,
        secret: str | None,
        reply_with_voice: bool | None = None,
        qq_media_upload_capability: str | None = None,
        life_forecast_enabled: bool | None = None,
    ) -> dict[str, Any]:
        if self._configuration_store is None:
            raise RuntimeError("configuration_unavailable")
        readiness = await self._voice_readiness_async(qq_media_upload_capability)
        if reply_with_voice is True and not readiness["voice_reply_available"]:
            raise QQConfigurationError("voice_unavailable")
        saved = self._configuration_store.update(
            appid=appid,
            secret=secret,
            reply_with_voice=reply_with_voice,
            qq_media_upload_capability=qq_media_upload_capability,
            life_forecast_enabled=life_forecast_enabled,
        )
        return {**saved, **await self._voice_readiness_async()}

    async def generate_life_support_reminder(self, kind: str) -> dict[str, Any]:
        """Generate without chat history; missing PK-200 always degrades safely."""

        topic = _REMINDER_TOPICS.get(str(kind or ""))
        if topic is None:
            raise ValueError("unsupported_reminder_kind")
        fallback = f"老师，该{topic}了。别等身体提出抗议才想起来，执行。"
        provider = self._text_generator_provider
        if (
            callable(provider)
            and not callable(getattr(provider, "generate_text", None))
        ):
            try:
                provider = provider()
            except Exception:
                provider = None
        generate = getattr(provider, "generate_text", None)
        if not callable(generate):
            return {"text": fallback, "generated": False, "model": None}
        try:
            result = await generate(
                (
                    "生成一到两句简短中文生命维持提醒。语气冷静、轻微嘴硬、"
                    "关心老师；不要 Markdown、标题、emoji、情绪标签、解释、"
                    "系统提示或模型信息。"
                ),
                f"现在请提醒老师：{topic}。",
                max_tokens=90,
                temperature=0.8,
                fallback=fallback,
            )
        except Exception:
            return {"text": fallback, "generated": False, "model": None}
        text = _EMOTION_PREFIX.sub("", str(getattr(result, "text", "") or ""))
        text = " ".join(text.split())[:180].strip()
        generated = bool(getattr(result, "generated", False) and text)
        model = getattr(result, "model", None) if generated else None
        if not isinstance(model, str) or len(model) > 120:
            model = None
        return {
            "text": text or fallback,
            "generated": generated,
            "model": model,
        }


__all__ = ["QQControlAdapterFacade"]
