"""Atomic persistence for the non-secret local LLM profile."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from .models import LLMProfile, PROFILE_PROVIDERS, THINKING_MODES


class ProfileValidationError(ValueError):
    pass


class ProfilePersistenceError(RuntimeError):
    pass


def normalize_profile(value: object, *, updated_at: str | None = None) -> LLMProfile:
    if isinstance(value, LLMProfile):
        source = value.to_dict()
    elif isinstance(value, dict):
        source = dict(value)
    else:
        raise ProfileValidationError("模型方案必须是对象")

    allowed = {"provider", "base_url", "model", "thinking_mode", "updated_at"}
    if set(source) - allowed:
        raise ProfileValidationError("模型方案包含不支持的字段")

    provider = source.get("provider")
    if not isinstance(provider, str) or provider not in PROFILE_PROVIDERS:
        raise ProfileValidationError("provider 只支持 deepseek 或 custom")

    raw_base_url = source.get("base_url", "")
    if not isinstance(raw_base_url, str):
        raise ProfileValidationError("Base URL 必须是字符串")
    base_url = raw_base_url.strip().rstrip("/")
    if not base_url or len(base_url) > 2048 or any(char.isspace() or ord(char) < 32 for char in base_url):
        raise ProfileValidationError("Base URL 不能为空且长度不能超过 2048")
    try:
        parsed = urlparse(base_url)
        port = parsed.port
    except ValueError as exc:
        raise ProfileValidationError("Base URL 不是合法 URL") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or port is None and not parsed.netloc:
        raise ProfileValidationError("Base URL 必须是绝对 HTTP(S) URL")
    if parsed.username is not None or parsed.password is not None:
        raise ProfileValidationError("Base URL 不允许包含用户名或密码")
    if parsed.query or parsed.fragment:
        raise ProfileValidationError("Base URL 不允许包含查询参数或片段")
    if parsed.path not in {"", "/"} and any(part in {".", ".."} for part in parsed.path.split("/")):
        raise ProfileValidationError("Base URL 路径不合法")

    raw_model = source.get("model", "")
    if not isinstance(raw_model, str):
        raise ProfileValidationError("模型 ID 必须是字符串")
    model = raw_model.strip()
    if not model or len(model) > 160 or any(ord(char) < 32 for char in model):
        raise ProfileValidationError("模型 ID 不能为空、不能含控制字符且长度不能超过 160")

    thinking_mode = source.get("thinking_mode", "disabled")
    if not isinstance(thinking_mode, str) or thinking_mode not in THINKING_MODES:
        raise ProfileValidationError("thinking_mode 只支持 enabled 或 disabled")
    if provider == "custom":
        thinking_mode = "disabled"

    timestamp = updated_at
    source_updated_at = source.get("updated_at")
    if timestamp is None and source_updated_at is not None:
        if not isinstance(source_updated_at, str) or len(source_updated_at) > 64:
            raise ProfileValidationError("updated_at 格式无效")
        try:
            datetime.fromisoformat(source_updated_at)
        except ValueError as exc:
            raise ProfileValidationError("updated_at 格式无效") from exc
        timestamp = source_updated_at
    return LLMProfile(
        provider=provider,
        base_url=base_url,
        model=model,
        thinking_mode=thinking_mode,
        updated_at=timestamp,
    )


class LLMProfileRepository:
    def __init__(
        self,
        path: str | Path,
        *,
        clock: Callable[[], datetime] = datetime.now,
        replace: Callable[[str | os.PathLike[str], str | os.PathLike[str]], None] = os.replace,
    ):
        self.path = Path(path)
        self._clock = clock
        self._replace = replace

    def load(self, default: LLMProfile) -> LLMProfile:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return normalize_profile(payload)
        except FileNotFoundError:
            return default
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            print("[Conversation] local LLM profile is unavailable; using safe defaults")
            return default

    def save(self, profile: LLMProfile) -> LLMProfile:
        saved = normalize_profile(
            profile,
            updated_at=self._clock().isoformat(timespec="seconds"),
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temp_path = Path(handle.name)
                json.dump(saved.to_dict(), handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            self._replace(temp_path, self.path)
            temp_path = None
            return saved
        except Exception as exc:
            raise ProfilePersistenceError("模型方案保存失败") from exc
        finally:
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    pass
