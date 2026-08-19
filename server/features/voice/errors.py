"""Structured and deliberately sanitized voice errors."""
from __future__ import annotations


class VoiceError(RuntimeError):
    def __init__(
        self,
        *,
        stage: str,
        code: str,
        message: str,
        status_code: int = 502,
        retryable: bool = False,
    ):
        super().__init__(message)
        self.stage = stage
        self.code = code
        self.status_code = status_code
        self.retryable = retryable

    def to_public_dict(self) -> dict:
        return {
            "stage": self.stage,
            "code": self.code,
            "message": str(self),
            "retryable": self.retryable,
        }


class VoiceRequestCancelled(VoiceError):
    def __init__(self):
        super().__init__(
            stage="request",
            code="request_cancelled",
            message="语音请求已取消",
            status_code=499,
        )


def unavailable(stage: str) -> VoiceError:
    names = {"asr": "语音识别", "conversation": "对话", "tts": "语音合成", "voice_pack": "Voice Pack"}
    return VoiceError(
        stage=stage,
        code=f"{stage}_unavailable",
        message=f"{names.get(stage, stage)}服务不可用",
        status_code=503,
        retryable=True,
    )


def timed_out(stage: str) -> VoiceError:
    return VoiceError(
        stage=stage,
        code=f"{stage}_timeout",
        message=f"{stage} 阶段超时",
        status_code=504,
        retryable=True,
    )


def failed(stage: str) -> VoiceError:
    return VoiceError(
        stage=stage,
        code=f"{stage}_failed",
        message=f"{stage} 阶段失败",
        status_code=502,
        retryable=False,
    )
