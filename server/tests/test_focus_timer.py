"""Side-effect-free regression checks for the focus timer service."""

from __future__ import annotations

import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import _path_setup  # noqa: F401

from features.focus.repository import FocusRepository, FocusStateError
from features.focus.service import FocusService
from systems.focus_timer import FocusTimerStore, get_status, reset, start_timer, stop_timer


def check_service_lifecycle() -> None:
    with tempfile.TemporaryDirectory(prefix="kei-focus-service-") as temp_dir:
        state_path = Path(temp_dir) / "focus_timer.json"
        repository = FocusRepository(state_path)
        start_at = datetime(2026, 7, 21, 9, 0, 0)
        service = FocusService(repository, id_factory=lambda: "session-one")

        idle = service.status(now=start_at)
        assert idle.status == "idle" and not idle.active
        started = service.start(
            mode="pomodoro", minutes=10, task="isolated task", now=start_at
        )
        assert started.started and started.active and started.remaining_seconds == 600
        assert started.session_id == "session-one"

        duplicate = service.start(
            mode="focus", minutes=20, task="ignored", now=start_at + timedelta(minutes=1)
        )
        assert duplicate.already_active and duplicate.mode == "pomodoro"
        assert duplicate.remaining_seconds == 540

        restarted_service = FocusService(repository)
        restored = restarted_service.status(now=start_at + timedelta(minutes=2))
        assert restored.active and restored.remaining_seconds == 480
        stopped = restarted_service.stop(now=start_at + timedelta(minutes=3))
        assert stopped.stopped and stopped.status == "stopped" and not stopped.active

        short_start = restarted_service.start(
            mode="focus", minutes=0.1, task="completion fixture", now=start_at + timedelta(minutes=4)
        )
        assert short_start.active
        after_restart = FocusService(repository).status(
            now=start_at + timedelta(minutes=4, seconds=7)
        )
        assert after_restart.completed and after_restart.status == "completed"
        assert after_restart.remaining_seconds == 0

        idle_after_completion = FocusService(repository).status(
            now=start_at + timedelta(minutes=4, seconds=8)
        )
        assert idle_after_completion.status == "idle"
        assert restarted_service.reset() == 2
        assert FocusService(repository).status(now=start_at + timedelta(minutes=5)).status == "idle"


def check_legacy_systems_compatibility() -> None:
    with tempfile.TemporaryDirectory(prefix="kei-focus-legacy-") as temp_dir:
        store = FocusTimerStore(Path(temp_dir) / "focus_timer.json")
        current = datetime(2026, 7, 21, 10, 0, 0)
        started = start_timer(
            mode="focus", minutes=5, task="legacy fixture", store=store, now=current
        )
        assert started.started and started.to_dict()["mode"] == "focus"
        assert get_status(store=store, now=current + timedelta(seconds=30)).active
        assert stop_timer(store=store, now=current + timedelta(seconds=31)).stopped
        assert reset(store=store) == 1


def check_validation() -> None:
    with tempfile.TemporaryDirectory(prefix="kei-focus-validation-") as temp_dir:
        service = FocusService(FocusRepository(Path(temp_dir) / "focus_timer.json"))
        try:
            service.start(mode="unsupported")
        except ValueError as exc:
            assert "pomodoro" in str(exc) and "focus" in str(exc)
        else:
            raise AssertionError("unsupported focus mode was accepted")


def check_corrupt_state_is_not_overwritten() -> None:
    with tempfile.TemporaryDirectory(prefix="kei-focus-corrupt-") as temp_dir:
        state_path = Path(temp_dir) / "focus_timer.json"
        old_bytes = b'{"active_id":"broken","sessions":'
        state_path.write_bytes(old_bytes)
        service = FocusService(FocusRepository(state_path))
        for operation in (service.status, service.stop):
            try:
                operation()
            except FocusStateError:
                pass
            else:
                raise AssertionError("corrupt focus state was accepted")
            assert state_path.read_bytes() == old_bytes


def main() -> int:
    check_service_lifecycle()
    check_legacy_systems_compatibility()
    check_validation()
    check_corrupt_state_is_not_overwritten()
    print("focus timer tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
