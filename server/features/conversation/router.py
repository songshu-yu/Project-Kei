"""Versioned conversation and local profile HTTP boundaries."""

from __future__ import annotations

import base64
import inspect
from datetime import datetime
from typing import Any, Callable, Optional

from fastapi import APIRouter, Body, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from .models import (
    ConversationChatRequest,
    ConversationChatResponse,
    ConversationReply,
    HistoryClearResponse,
    HistoryResponse,
    LegacyChatRequest,
    LegacyChatResponse,
    LLMProfileResponse,
    LLMProfileUpdate,
    VALID_EMOTIONS,
)
from .repository import ProfileValidationError
from .service import ConversationClosedError, ConversationService, ProfileApplyError


ServiceProvider = Callable[[], Optional[ConversationService]]
LocalControlGuard = Callable[[Request], bool]
LegacyCommandHandler = Callable[[str], Any]
AudioSynthesizer = Callable[[str, str], Any]


async def _await_if_needed(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _coerce_reply(value: Any) -> ConversationReply | None:
    if value is None:
        return None
    if isinstance(value, ConversationReply):
        return value
    if isinstance(value, dict):
        text = str(value.get("text", "")).strip()
        if not text:
            return None
        emotion = str(value.get("emotion", "calm")).strip().lower()
        if emotion not in VALID_EMOTIONS:
            emotion = "calm"
        timestamp = str(value.get("timestamp", "")).strip() or datetime.now().isoformat()
        return ConversationReply(text=text, emotion=emotion, timestamp=timestamp)
    return None


def create_conversation_router(
    service_provider: ServiceProvider,
    *,
    local_control_guard: LocalControlGuard,
    local_read_guard: LocalControlGuard | None = None,
    include_legacy: bool = False,
    legacy_command_handler: LegacyCommandHandler | None = None,
    audio_synthesizer: AudioSynthesizer | None = None,
) -> APIRouter:
    router = APIRouter(tags=["conversation"])

    def service() -> ConversationService:
        value = service_provider()
        if value is None:
            raise HTTPException(status_code=503, detail="对话服务尚未启动完成")
        return value

    def require_local_read(request: Request) -> None:
        guard = local_read_guard or local_control_guard
        if not guard(request):
            raise HTTPException(status_code=403, detail="This action is available only from this computer")

    def require_local_control(request: Request) -> None:
        if not local_control_guard(request):
            raise HTTPException(status_code=403, detail="This action is available only from this computer")

    async def reply_for(message: str) -> ConversationReply:
        if legacy_command_handler is not None:
            command_reply = _coerce_reply(
                await _await_if_needed(legacy_command_handler(message))
            )
            if command_reply is not None:
                return command_reply
        return await service().chat(message)

    async def profile_update(payload: Any):
        try:
            parsed = LLMProfileUpdate.parse_obj(payload)
        except (ValidationError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail="模型方案请求字段无效") from exc
        try:
            profile = await service().update_profile(parsed.dict())
        except ProfileValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except ProfileApplyError as exc:
            raise HTTPException(
                status_code=exc.status_code,
                detail={"code": exc.code, "stage": exc.stage, "message": str(exc)},
            ) from exc
        return profile.to_dict()

    @router.post("/api/v1/conversation", response_model=ConversationChatResponse)
    async def conversation_chat(payload: ConversationChatRequest):
        try:
            reply = await service().chat(payload.message)
        except ConversationClosedError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return ConversationChatResponse(
            text=reply.text,
            emotion=reply.emotion,
            timestamp=reply.timestamp,
        )

    @router.get("/api/v1/conversation/history", response_model=HistoryResponse)
    async def conversation_history():
        active = service()
        messages = await active.history(limit=active.max_history * 2)
        return HistoryResponse(
            count=len(messages),
            messages=[
                {"role": item.role, "content": item.content, "emotion": item.emotion}
                for item in messages
            ],
        )

    @router.delete("/api/v1/conversation/history", response_model=HistoryClearResponse)
    async def clear_conversation_history():
        cleared = await service().clear_history()
        return HistoryClearResponse(status="ok", cleared=cleared)

    @router.get("/api/v1/llm-profile", response_model=LLMProfileResponse)
    async def get_llm_profile(request: Request):
        require_local_read(request)
        return (await service().get_profile()).to_dict()

    @router.put("/api/v1/llm-profile", response_model=LLMProfileResponse)
    async def update_llm_profile(request: Request, payload: Any = Body(...)):
        require_local_control(request)
        return await profile_update(payload)

    if include_legacy:
        @router.post("/chat", response_model=LegacyChatResponse)
        async def legacy_chat(payload: LegacyChatRequest):
            try:
                reply = await reply_for(payload.message)
            except ConversationClosedError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            audio_base64 = ""
            if payload.with_audio and audio_synthesizer is not None:
                audio = await _await_if_needed(
                    audio_synthesizer(reply.text, reply.emotion)
                )
                if isinstance(audio, bytes) and audio:
                    audio_base64 = base64.b64encode(audio).decode("ascii")
            return LegacyChatResponse(
                text=reply.text,
                emotion=reply.emotion,
                audio_base64=audio_base64,
                timestamp=reply.timestamp,
            )

        @router.post("/chat/text-only", response_model=ConversationChatResponse)
        async def legacy_text_chat(payload: LegacyChatRequest):
            try:
                reply = await reply_for(payload.message)
            except ConversationClosedError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            return ConversationChatResponse(
                text=reply.text,
                emotion=reply.emotion,
                timestamp=reply.timestamp,
            )

        @router.post("/history/clear", response_model=HistoryClearResponse)
        async def clear_legacy_history():
            cleared = await service().clear_history()
            return HistoryClearResponse(status="ok", cleared=cleared)

        @router.get("/history", response_model=HistoryResponse)
        async def legacy_history():
            active = service()
            all_messages = await active.history()
            return HistoryResponse(
                count=len(all_messages),
                messages=[
                    {"role": item.role, "content": item.content, "emotion": item.emotion}
                    for item in all_messages[-20:]
                ],
            )

        @router.get("/dashboard/llm/profile", response_model=LLMProfileResponse)
        async def legacy_get_llm_profile(request: Request):
            require_local_read(request)
            return (await service().get_profile()).to_dict()

        @router.put("/dashboard/llm/profile", response_model=LLMProfileResponse)
        async def legacy_update_llm_profile(request: Request, payload: Any = Body(...)):
            require_local_control(request)
            return await profile_update(payload)

        @router.websocket("/ws/chat")
        async def legacy_websocket_chat(websocket: WebSocket):
            await websocket.accept()
            try:
                while True:
                    payload = await websocket.receive_json()
                    message = payload.get("message", "") if isinstance(payload, dict) else ""
                    if not str(message).strip():
                        continue
                    try:
                        reply = await reply_for(str(message))
                    except ConversationClosedError:
                        await websocket.send_json({"error": "对话服务已关闭"})
                        break
                    except ValueError:
                        await websocket.send_json({"error": "消息不能为空"})
                        continue
                    except Exception:
                        await websocket.send_json({"error": "对话上下文暂时不可用"})
                        continue
                    audio_base64 = ""
                    if audio_synthesizer is not None:
                        try:
                            audio = await _await_if_needed(
                                audio_synthesizer(reply.text, reply.emotion)
                            )
                        except Exception:
                            audio = None
                        if isinstance(audio, bytes) and audio:
                            audio_base64 = base64.b64encode(audio).decode("ascii")
                    await websocket.send_json({
                        "text": reply.text,
                        "emotion": reply.emotion,
                        "audio_base64": audio_base64,
                        "timestamp": reply.timestamp,
                    })
            except WebSocketDisconnect:
                return

    return router
