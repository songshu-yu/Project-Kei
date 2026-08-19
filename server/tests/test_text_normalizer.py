"""Quick checks for voice input text normalization."""
from __future__ import annotations

import _path_setup  # noqa: F401

from services.text_normalizer import normalize_voice_text


CASES = [
    ("你好, Key, 我回来了", "你好, Kei, 我回来了"),
    ("你好凯怡，我是老师", "你好Kei，我是老师"),
    ("那你觉得我教你什么合适呢?", "那你觉得我叫你什么合适呢?"),
    ("我教你什么比较好", "我叫你什么比较好"),
    ("我該教你什麼好", "我該叫你什麼好"),
]


def main() -> int:
    failed = 0
    for raw, expected in CASES:
        actual = normalize_voice_text(raw)
        ok = actual == expected
        mark = "OK" if ok else "FAIL"
        print(f"{mark}: {raw!r} -> {actual!r}")
        if not ok:
            print(f"  expected: {expected!r}")
            failed += 1
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
