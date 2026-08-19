"""Small deterministic text helpers owned by the voice orchestration layer."""

from __future__ import annotations

import re


_KEI_VARIANTS = (
    "凯怡",
    "凯伊",
    "凯依",
    "凯一",
    "凱怡",
    "凱伊",
    "凱依",
    "開伊",
    "开伊",
)


def normalize_voice_text(text: str) -> str:
    fixed = str(text or "").strip()
    if not fixed:
        return ""
    fixed = re.sub(r"(?i)\b(?:kei|key)\b", "Kei", fixed)
    for variant in _KEI_VARIANTS:
        fixed = fixed.replace(variant, "Kei")
    calling_suffix = r"(什么|啥|哪个|什麼)"
    fit_suffix = r"(合适|比较好|好|可以)"
    fixed = re.sub(
        rf"(我|我该|我該|你觉得我|你覺得我)教你{calling_suffix}{fit_suffix}",
        lambda match: match.group(0).replace("教你", "叫你"),
        fixed,
    )
    return fixed


def split_text_for_tts(text: str, max_chars: int = 42) -> list[str]:
    value = re.sub(r"\s+", " ", str(text or "").strip())
    if not value:
        return []
    hard_breaks = set("。！？!?；;\n")
    soft_breaks = set("，,、~～…")
    sentences: list[str] = []
    buffer: list[str] = []
    for character in value:
        buffer.append(character)
        if character in hard_breaks:
            part = "".join(buffer).strip()
            if part:
                sentences.append(part)
            buffer = []
    tail = "".join(buffer).strip()
    if tail:
        sentences.append(tail)
    chunks: list[str] = []
    for sentence in sentences:
        if len(sentence) <= max_chars and not any(char in sentence for char in soft_breaks):
            chunks.append(sentence)
            continue
        buffer = []
        for character in sentence:
            buffer.append(character)
            if len(buffer) >= max_chars or (
                len(buffer) >= 12 and character in soft_breaks
            ):
                part = "".join(buffer).strip()
                if part:
                    chunks.append(part)
                buffer = []
        tail = "".join(buffer).strip()
        if tail:
            chunks.append(tail)
    return chunks or [value]


__all__ = ["normalize_voice_text", "split_text_for_tts"]
