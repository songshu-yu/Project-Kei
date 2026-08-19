"""OpenAI-compatible HTTP client with bounded, credential-safe failures."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Mapping, Sequence

import httpx

from .models import VALID_EMOTIONS
from .provider.contracts import LLMUpstreamError


class LLMEngine:
    """Low-level provider client retained under the historical class name."""

    VALID_EMOTIONS = set(VALID_EMOTIONS)

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o-mini",
        system_prompt_path: str | Path | None = None,
        request_options: dict | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.request_options = dict(request_options or {})
        self.system_prompt = self._load_system_prompt(system_prompt_path)
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=timeout,
            trust_env=transport is None,
            transport=transport,
        )

    @staticmethod
    def _load_system_prompt(path: str | Path | None = None) -> str:
        prompt_paths = (
            (Path(path),)
            if path
            else (
                Path(__file__).resolve().with_name("kei_system.txt"),
                Path(__file__).resolve().parents[2] / "prompts" / "kei_system.txt",
            )
        )
        for prompt_path in prompt_paths:
            try:
                text = prompt_path.read_text(encoding="utf-8").strip()
            except OSError:
                continue
            if text:
                print(f"[LLM] role prompt loaded: {prompt_path.name}")
                return text
        print("[LLM] role prompt unavailable; using built-in fallback")
        return "你是天童 Kei，冷静、温柔而认真。回复开头用 [emotion:标签] 标注情绪。"

    @staticmethod
    def parse_emotion(text: str) -> tuple[str, str]:
        value = str(text or "")
        match = re.match(r"\[emotion:([A-Za-z0-9_]+)\]\s*", value)
        if not match:
            return "calm", value.strip()
        emotion = match.group(1).lower()
        clean = value[match.end():].strip()
        return (emotion if emotion in VALID_EMOTIONS else "calm"), clean

    async def chat_completion(
        self,
        messages: Sequence[Mapping[str, str]],
        *,
        max_tokens: int,
        temperature: float,
        presence_penalty: float | None = None,
    ) -> str:
        payload: dict = {
            "model": self.model,
            "messages": [dict(message) for message in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if presence_penalty is not None:
            payload["presence_penalty"] = presence_penalty
        payload.update(self.request_options)
        try:
            response = await self.client.post("/chat/completions", json=payload)
        except httpx.TimeoutException as exc:
            raise LLMUpstreamError("timeout", "模型服务响应超时") from exc
        except httpx.ConnectError as exc:
            raise LLMUpstreamError("connection_failed", "无法连接模型服务") from exc
        except httpx.RequestError as exc:
            raise LLMUpstreamError("request_failed", "模型服务请求失败") from exc

        if response.status_code in {401, 403}:
            raise LLMUpstreamError("authentication_failed", "模型服务拒绝了凭证", status_code=response.status_code)
        if response.status_code == 429:
            raise LLMUpstreamError("rate_limited", "模型服务当前请求过多", status_code=429)
        if response.status_code >= 500:
            raise LLMUpstreamError("upstream_unavailable", "模型服务暂时不可用", status_code=response.status_code)
        if response.status_code >= 400:
            raise LLMUpstreamError("upstream_rejected", "模型服务拒绝了请求", status_code=response.status_code)

        try:
            data = response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise LLMUpstreamError("invalid_json", "模型服务返回了无效数据") from exc
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMUpstreamError("missing_choices", "模型服务响应缺少结果") from exc
        if not isinstance(content, str) or not content.strip():
            raise LLMUpstreamError("empty_response", "模型服务返回了空回复")
        return content.strip()

    async def complete(
        self,
        system_prompt: str,
        user_input: str,
        *,
        max_tokens: int = 512,
        temperature: float = 0.6,
    ) -> str:
        return await self.chat_completion(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
        )

    async def test(self) -> None:
        await self.chat_completion(
            [{"role": "user", "content": "Reply with OK."}],
            max_tokens=8,
            temperature=0,
        )

    async def close(self) -> None:
        await self.client.aclose()
