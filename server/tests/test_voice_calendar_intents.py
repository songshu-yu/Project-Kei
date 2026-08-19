"""Quick checks for calendar/memo voice intent routing."""
from __future__ import annotations

import threading
import tempfile
from pathlib import Path
from unittest.mock import patch

import _path_setup  # noqa: F401
from fastapi import FastAPI

from core.calendar_contracts import calendar_summary_registry, get_calendar_summary
from features.calendar.module import (
    register as register_calendar_module,
    unregister as unregister_calendar_module,
)
from services.voice_pipeline import VoicePipeline


CASES = [
    ("今天是什么日子", True),
    ("今天几号", True),
    ("今天有什么备忘", True),
    ("看看备忘录", True),
    ("我的熟练度是多少", True),
    ("一万小时进度怎么样", True),
    ("我们聊聊天", False),
]


def main() -> int:
    failed = 0
    for text, expected in CASES:
        actual = VoicePipeline._calendar_intent(text)
        ok = actual == expected
        mark = "OK" if ok else "FAIL"
        print(f"{mark}: {text!r} -> {actual!r}")
        if not ok:
            print(f"  expected: {expected!r}")
            failed += 1
    calls = []

    def isolated_summary() -> dict:
        calls.append("called")
        return {
            "message": "今天是隔离测试日期，星期二。",
            "skills": [
                {"name": "样例甲", "total_hours": 2.5, "level": {"name": "凡人六重"}},
                {"name": "样例乙", "total_hours": 1.0, "level": {"name": "凡人三重"}},
            ],
        }

    pipeline = VoicePipeline(None, None, None, calendar_summary_provider=isolated_summary)
    reply = pipeline._calendar_reply()
    if calls != ["called"] or "隔离测试日期" not in reply or "熟练度排行" not in reply:
        print("FAIL: injected calendar summary provider was not used")
        failed += 1

    calendar_summary_registry.unregister_calendar_summary_provider()
    with patch(
        "pathlib.Path.read_text",
        side_effect=AssertionError("missing calendar provider must not read state"),
    ):
        missing = get_calendar_summary()
        missing_reply = VoicePipeline(None, None, None)._calendar_reply()
    if missing != {
        "available": False,
        "error_code": "calendar_unavailable",
        "message": "",
        "skills": [],
    } or missing_reply != "":
        print("FAIL: missing calendar did not return stable empty/unavailable summary")
        failed += 1

    class RegisteredProvider:
        def __call__(self, day=None):
            return {
                "message": f"已注册公开摘要 {day or 'today'}",
                "skills": [],
            }

    registered = RegisteredProvider()
    calendar_summary_registry.register_calendar_summary_provider(registered)
    if "已注册公开摘要" not in VoicePipeline(None, None, None)._calendar_reply():
        print("FAIL: registered calendar provider was not used")
        failed += 1
    calendar_summary_registry.unregister_calendar_summary_provider(registered)
    if get_calendar_summary()["error_code"] != "calendar_unavailable":
        print("FAIL: unregistered calendar provider remained visible")
        failed += 1

    with tempfile.TemporaryDirectory(prefix="kei-calendar-provider-") as temp_dir:
        app = FastAPI()
        app.state.calendar_state_path = Path(temp_dir) / "calendar.json"
        app.state.voice_calendar_provider_registry = calendar_summary_registry
        register_calendar_module(app)
        installed = get_calendar_summary("2030-01-02")
        if installed.get("available") is not True:
            print("FAIL: calendar package register did not publish its provider")
            failed += 1
        unregister_calendar_module(app)
        if get_calendar_summary()["error_code"] != "calendar_unavailable":
            print("FAIL: calendar package unregister did not release its provider")
            failed += 1

    observed = []
    errors = []
    observed_lock = threading.Lock()

    def reader() -> None:
        try:
            for _ in range(200):
                value = get_calendar_summary()["available"]
                with observed_lock:
                    observed.append(value)
        except Exception as exc:
            errors.append(exc)

    def writer() -> None:
        try:
            for _ in range(100):
                calendar_summary_registry.register_calendar_summary_provider(
                    registered
                )
                calendar_summary_registry.unregister_calendar_summary_provider(
                    registered
                )
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=reader) for _ in range(4)]
    threads.append(threading.Thread(target=writer))
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    calendar_summary_registry.unregister_calendar_summary_provider()
    if errors or not observed or not set(observed) <= {True, False}:
        print("FAIL: concurrent calendar registry access was not isolated")
        failed += 1

    legacy_source = (
        Path(__file__).resolve().parents[1]
        / "features"
        / "voice"
        / "legacy_pipeline.py"
    ).read_text(encoding="utf-8")
    if "features.calendar" in legacy_source or "calendar.service" in legacy_source:
        print("FAIL: voice legacy pipeline retains a static calendar dependency")
        failed += 1
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
