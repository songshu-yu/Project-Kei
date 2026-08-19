"""Quick checks for demon slayer voice intent routing."""
from __future__ import annotations

import _path_setup  # noqa: F401

from services.voice_pipeline import VoicePipeline


CASES = [
    ("Kei，今天还有什么妖怪没斩？", "reminder"),
    ("提醒我一下今天还有什么没做", "reminder"),
    ("给我做今日复盘", "daily_review"),
    ("今天做得怎么样", "daily_review"),
    ("本周复盘一下", "weekly_review"),
    ("做一下本月复盘", "monthly_review"),
    ("给我年度复盘", "yearly_review"),
    ("我现在有多少积分", "status"),
    ("能兑换什么愿望", "status"),
    ("我们随便聊聊天", ""),
]


def main() -> int:
    failed = 0
    for text, expected in CASES:
        actual = VoicePipeline._demon_intent(text)
        ok = actual == expected
        mark = "OK" if ok else "FAIL"
        print(f"{mark}: {text!r} -> {actual!r}")
        if not ok:
            print(f"  expected: {expected!r}")
            failed += 1
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
