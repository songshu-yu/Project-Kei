"""Legacy fitness import compatibility checks using only temporary state."""

from __future__ import annotations

import tempfile
from datetime import date, timedelta
from pathlib import Path

import _path_setup  # noqa: F401

from systems.fitness_checkin import FitnessCheckinStore, check_in, get_status, reset


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="kei-fitness-legacy-") as temp_dir:
        store = FitnessCheckinStore(Path(temp_dir) / "fitness_checkins.json")
        start = date(2026, 8, 1)
        results = [
            check_in(
                day=(start + timedelta(days=offset)).isoformat(),
                note=f"fictional fitness {offset}",
                store=store,
            )
            for offset in range(6)
        ]
        assert results[-1].streak == 6 and results[-1].reward_unlocked is True

        duplicate = check_in(day="2026-08-06", note="duplicate", store=store)
        assert duplicate.already_checked_in is True
        assert duplicate.checked_in is False and duplicate.reward_unlocked is False

        status = get_status(day="2026-08-06", store=store)
        assert status["checked_today"] is True
        assert status["streak"] == 6 and status["total_checkins"] == 6
        assert status["next_reward_in"] == 6 and len(status["rewards"]) == 1

        cleared_checkins, cleared_rewards = reset(store=store)
        assert (cleared_checkins, cleared_rewards) == (6, 1)
        empty = get_status(day="2026-08-06", store=store)
        assert empty["total_checkins"] == 0 and empty["rewards"] == []

    print("fitness legacy compatibility tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
