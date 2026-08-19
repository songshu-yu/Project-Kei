"""PK-150 dashboard rendering checks with temporary state and fake API facts."""

from __future__ import annotations

import json
import subprocess
import tempfile
from datetime import date, datetime, time
from pathlib import Path

import _path_setup  # noqa: F401

from features.demon_slayer.repository import DemonSlayerStore
from features.demon_slayer.service import DemonSlayerService


SERVER_ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_MODULE = (
    SERVER_ROOT / "features" / "demon_slayer" / "package_source" / "dashboard" / "index.js"
)


class FakeTime:
    def __init__(self, current: date):
        self.current = current

    def today(self) -> date:
        return self.current

    def now(self) -> datetime:
        return datetime.combine(self.current, time(9, 30))


def render_fake_status(goals: list[dict]) -> str:
    source = DASHBOARD_MODULE.read_text(encoding="utf-8")
    assert "export function formatGoalStatistics" in source
    script = """
import {pathToFileURL} from 'node:url';
const module = await import(pathToFileURL(process.argv[1]).href);
const goals = JSON.parse(process.argv[2]);
process.stdout.write(goals.map(goal =>
  `<div class="demon-goal-statistics">${module.formatGoalStatistics(goal)}</div>`
).join(''));
"""
    completed = subprocess.run(
        [
            "node",
            "--input-type=module",
            "-e",
            script,
            str(DASHBOARD_MODULE),
            json.dumps(goals, ensure_ascii=False),
        ],
        cwd=SERVER_ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )
    if completed.returncode:
        raise AssertionError(completed.stderr or completed.stdout)
    return completed.stdout


def check_service_contract_uses_temporary_state(path: Path) -> None:
    fake_time = FakeTime(date(2026, 7, 28))
    service = DemonSlayerService(
        DemonSlayerStore(path),
        clock=fake_time.today,
        timestamp=fake_time.now,
    )
    for cadence in ("daily", "weekly", "monthly", "yearly"):
        service.add_goal(f"{cadence} dashboard target", cadence=cadence)
    service.add_goal(
        "once dashboard target",
        cadence="daily",
        repeat_mode="once",
        target_date="2026-07-28",
    )
    before = path.read_bytes()
    status = service.get_status("2026-07-28")
    assert path.read_bytes() == before, "status must remain read-only"
    assert len(status["goals"]) == 5
    for goal in status["goals"]:
        assert {
            "active_since",
            "active_days",
            "current_streak",
            "longest_streak",
            "streak_unit",
            "completed",
        } <= goal.keys()


def check_dashboard_renders_fake_api_facts_without_side_effects(path: Path) -> None:
    fake_goals = [
        {
            "id": "daily",
            "title": "每日目标",
            "cadence": "daily",
            "rank": "小妖",
            "demon": "学业妖",
            "repeat_mode": "recurring",
            "points": 10,
            "active_since": "2026-07-17",
            "active_days": 12,
            "current_streak": 3,
            "longest_streak": 8,
            "streak_unit": "day",
            "completed": True,
        },
        {
            "id": "weekly",
            "title": "每周目标",
            "cadence": "weekly",
            "rank": "大妖",
            "demon": "迷雾妖",
            "repeat_mode": "recurring",
            "points": 35,
            "active_since": "2026-07-28",
            "active_days": 0,
            "current_streak": 0,
            "longest_streak": 0,
            "streak_unit": "week",
            "completed": False,
        },
        {
            "id": "monthly",
            "title": "每月目标",
            "cadence": "monthly",
            "rank": "大大妖",
            "demon": "迷雾妖",
            "repeat_mode": "recurring",
            "points": 120,
            "active_since": None,
            "active_days": None,
            "current_streak": None,
            "longest_streak": None,
            "streak_unit": "month",
            "completed": False,
        },
        {
            "id": "yearly",
            "title": "每年目标",
            "cadence": "yearly",
            "rank": "妖王",
            "demon": "迷雾妖",
            "repeat_mode": "recurring",
            "points": 500,
            "active_since": "2024-01-01",
            "active_days": 940,
            "current_streak": 2,
            "longest_streak": 4,
            "streak_unit": "year",
            "completed": False,
        },
        {
            "id": "once",
            "title": "临时目标",
            "cadence": "daily",
            "rank": "小妖",
            "demon": "迷雾妖",
            "repeat_mode": "once",
            "target_date": "2026-07-28",
            "points": 10,
            "active_since": None,
            "active_days": None,
            "current_streak": 0,
            "longest_streak": 0,
            "streak_unit": "day",
            "completed": False,
        },
    ]
    path.write_bytes(b"PK-030 dashboard sentinel")
    before = path.read_bytes()
    rendered = render_fake_status(fake_goals)
    assert path.read_bytes() == before, "pure dashboard rendering must not write the temporary store"
    assert "启用起点 2026-07-17 · 已启用 12 天 · 当前连续 3 天 · 历史最长 8 天" in rendered
    assert "已启用 0 天 · 当前连续 0 周 · 历史最长 0 周" in rendered
    assert "启用起点 未知 · 已启用 未知 · 当前连续 0 月 · 历史最长 0 月" in rendered
    assert "当前连续 2 年 · 历史最长 4 年" in rendered
    assert "临时目标不累计启用天数 · 当前连续 0 天 · 历史最长 0 天" in rendered
    assert "undefined" not in rendered and "NaN" not in rendered
    assert rendered.count("demon-goal-statistics") == len(fake_goals)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="kei-demon-dashboard-") as temp_dir:
        path = Path(temp_dir) / "demon-slayer.json"
        check_service_contract_uses_temporary_state(path)
        check_dashboard_renders_fake_api_facts_without_side_effects(path)
    print("demon slayer dashboard tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
