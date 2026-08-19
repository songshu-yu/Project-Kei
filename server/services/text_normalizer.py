"""Lightweight text normalization for voice dialogue input."""
from __future__ import annotations

import re


_KEI_VARIANTS = (
    "\u51ef\u6021",  # 凯怡
    "\u51ef\u4f0a",  # 凯伊
    "\u51ef\u4f9d",  # 凯依
    "\u51ef\u4e00",  # 凯一
    "\u51f1\u6021",  # 凱怡
    "\u51f1\u4f0a",  # 凱伊
    "\u51f1\u4f9d",  # 凱依
    "\u958b\u4f0a",  # 開伊
    "\u5f00\u4f0a",  # 开伊
)


def normalize_voice_text(text: str) -> str:
    """Fix common ASR confusions before sending text to the dialogue model."""
    fixed = str(text or "").strip()
    if not fixed:
        return fixed

    fixed = _normalize_kei_name(fixed)
    fixed = _normalize_calling_phrases(fixed)
    return fixed


def _normalize_kei_name(text: str) -> str:
    fixed = text
    fixed = re.sub(r"(?i)\bkei\b", "Kei", fixed)
    fixed = re.sub(r"(?i)\bkey\b", "Kei", fixed)
    for variant in _KEI_VARIANTS:
        fixed = fixed.replace(variant, "Kei")
    return fixed


def _normalize_calling_phrases(text: str) -> str:
    fixed = text

    # In short companion-dialogue turns, "teach you what to..." is often a
    # Mandarin ASR confusion for "call you what to...".
    calling_suffix = r"(\u4ec0\u4e48|\u5565|\u54ea\u4e2a|\u4ec0\u9ebc)"
    fit_suffix = r"(\u5408\u9002|\u6bd4\u8f83\u597d|\u597d|\u53ef\u4ee5)"
    fixed = re.sub(
        rf"(\u6211|\u6211\u8be5|\u4f60\u89c9\u5f97\u6211)\u6559\u4f60{calling_suffix}{fit_suffix}",
        lambda m: m.group(0).replace("\u6559\u4f60", "\u53eb\u4f60"),
        fixed,
    )
    fixed = re.sub(
        rf"(\u6211|\u6211\u8a72|\u4f60\u89ba\u5f97\u6211)\u6559\u4f60{calling_suffix}{fit_suffix}",
        lambda m: m.group(0).replace("\u6559\u4f60", "\u53eb\u4f60"),
        fixed,
    )

    return fixed
