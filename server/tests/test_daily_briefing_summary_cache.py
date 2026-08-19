"""Focused checks for the dashboard's current-day Kei narration cache."""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.daily_briefing import DailyBriefingResult, DailyBriefingService


def result_for(day: date, script: str) -> DailyBriefingResult:
    return DailyBriefingResult(
        date=day.isoformat(),
        fetched=True,
        rewritten=True,
        text="plain briefing",
        script=script,
    )


def main() -> int:
    fixed_now = datetime(2026, 7, 22, 8, 0, tzinfo=timezone.utc)
    today = date(2026, 7, 22)
    yesterday = today - timedelta(days=1)

    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        cache_dir = root / "data" / "briefing_cache"
        cache_dir.mkdir(parents=True)
        summary_path = cache_dir / "kei_summary_today.json"
        summary_path.write_text(
            json.dumps({"date": yesterday.isoformat(), "text": "old narration"}),
            encoding="utf-8",
        )

        service = DailyBriefingService(root_dir=root, clock=lambda: fixed_now)
        assert not summary_path.exists(), "service startup must remove yesterday's narration"

        service._save_cache(result_for(today, "today narration"))
        summary = service.load_current_summary()
        assert summary["ready"] is True
        assert summary["date"] == today.isoformat()
        assert summary["text"] == "today narration"
        assert summary["updated_at"]

        service._save_cache(result_for(yesterday, "historical narration"))
        assert service.load_current_summary()["text"] == "today narration"

        summary_path.unlink()
        separated = service.load_current_summary()
        assert separated["ready"] is False, "new schema keeps narration separate from normalized items"

        # Existing pre-PK-110 caches may still embed ``script``. They remain
        # readable without rewriting the historical file in place.
        (cache_dir / f"{today.isoformat()}.json").write_text(
            json.dumps({
                "date": today.isoformat(),
                "fetched": True,
                "rewritten": True,
                "text": "legacy plain briefing",
                "script": "legacy embedded narration",
                "items": {},
                "warnings": [],
            }),
            encoding="utf-8",
        )
        migrated = service.load_current_summary()
        assert migrated["ready"] is True
        assert migrated["text"] == "legacy embedded narration"

        summary_path.write_text(
            json.dumps({"date": yesterday.isoformat(), "text": "stale again"}),
            encoding="utf-8",
        )
        cleared = service.prepare_summary_cache()
        assert cleared["ready"] is False
        assert not summary_path.exists()

    print("daily briefing summary cache tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
