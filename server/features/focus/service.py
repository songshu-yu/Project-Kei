"""Pomodoro and focus-mode business operations."""

from __future__ import annotations

import threading
import uuid
import math
import re
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Optional, Protocol, Tuple

from .models import FocusEncouragementResponse, TimerResult
from .repository import FocusRepository


FOCUS_MODES = {
    "pomodoro": {
        "label": "番茄钟",
        "minutes": 25.0,
        "break_minutes": 5,
        "start_text": "番茄钟开始。接下来 25 分钟只做这一件事，我会陪你守住这段时间。",
        "done_text": "番茄钟完成。做得很好，现在离开屏幕休息 5 分钟，喝点水，动一动。",
    },
    "focus": {
        "label": "专注模式",
        "minutes": 50.0,
        "break_minutes": 10,
        "start_text": "专注模式开始。接下来 50 分钟，我们把世界调小一点，只留下你和这件事。",
        "done_text": "专注完成。你刚刚认真守住了一整段时间，现在可以休息一下，或者去做一件让自己开心的小事。",
    },
}
SAFE_GENERATION_CODE = re.compile(r"^[a-z][a-z0-9_]{0,47}$")


class FocusTextGenerationResult(Protocol):
    text: str
    generated: bool
    error_code: Optional[str]


class FocusTextGenerator(Protocol):
    @property
    def system_prompt(self) -> str:
        ...

    async def generate_text(
        self,
        system_instruction: str,
        user_input: str,
        *,
        max_tokens: int,
        temperature: float,
        fallback: str,
    ) -> FocusTextGenerationResult:
        ...


class FocusSessionInactiveError(RuntimeError):
    pass


def now_local() -> datetime:
    return datetime.now().replace(microsecond=0)


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value)


def format_seconds(seconds: int) -> str:
    seconds = max(seconds, 0)
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}小时{minutes}分{secs}秒"
    if minutes:
        return f"{minutes}分{secs}秒"
    return f"{secs}秒"


def mode_config(mode: str) -> Dict[str, Any]:
    if mode not in FOCUS_MODES:
        raise ValueError("mode must be 'pomodoro' or 'focus'")
    return FOCUS_MODES[mode]


def find_session(state: Dict[str, Any], session_id: Optional[str]) -> Optional[Dict[str, Any]]:
    if not session_id:
        return None
    for session in state.get("sessions", []):
        if isinstance(session, dict) and session.get("id") == session_id:
            return session
    return None


def seconds_between(start_at: str, end_at: str, now: datetime) -> Tuple[int, int]:
    start = parse_time(start_at)
    end = parse_time(end_at)
    remaining = int((end - now).total_seconds())
    elapsed = int((now - start).total_seconds())
    return max(remaining, 0), max(elapsed, 0)


def result_from_session(
    session: Optional[Dict[str, Any]],
    status: str,
    message: str,
    *,
    started: bool = False,
    already_active: bool = False,
    stopped: bool = False,
    completed: bool = False,
    now: Optional[datetime] = None,
) -> TimerResult:
    now = now or now_local()
    if not session:
        return TimerResult(
            status=status,
            active=False,
            mode="",
            label="",
            task="",
            started=started,
            already_active=already_active,
            stopped=stopped,
            completed=completed,
            session_id="",
            start_at="",
            end_at="",
            duration_minutes=0.0,
            remaining_seconds=0,
            elapsed_seconds=0,
            message=message,
        )

    remaining, elapsed = seconds_between(session["start_at"], session["end_at"], now)
    active = session.get("status") == "active" and remaining > 0
    return TimerResult(
        status=status,
        active=active,
        mode=session.get("mode", ""),
        label=session.get("label", ""),
        task=session.get("task", ""),
        started=started,
        already_active=already_active,
        stopped=stopped,
        completed=completed,
        session_id=str(session.get("id", "")),
        start_at=session.get("start_at", ""),
        end_at=session.get("end_at", ""),
        duration_minutes=float(session.get("duration_minutes", 0.0)),
        remaining_seconds=remaining,
        elapsed_seconds=elapsed,
        message=message,
    )


def refresh_active(
    state: Dict[str, Any], now: Optional[datetime] = None
) -> Tuple[Optional[Dict[str, Any]], bool]:
    now = now or now_local()
    active = find_session(state, state.get("active_id"))
    if not active:
        state["active_id"] = None
        return None, False
    if active.get("status") != "active":
        state["active_id"] = None
        return active, False
    if now >= parse_time(active["end_at"]):
        active["status"] = "completed"
        active["completed_at"] = now.isoformat()
        state["active_id"] = None
        return active, True
    return active, False


class FocusService:
    def __init__(
        self,
        repository: FocusRepository,
        *,
        clock: Callable[[], datetime] = now_local,
        id_factory: Callable[[], str] = lambda: uuid.uuid4().hex,
    ):
        self.repository = repository
        self.clock = clock
        self.id_factory = id_factory
        self._lock = threading.RLock()

    def status(self, *, now: Optional[datetime] = None) -> TimerResult:
        with self._lock:
            current = now or self.clock()
            state = self.repository.load()
            active, just_completed = refresh_active(state, current)
            self.repository.save(state)
            if active and just_completed:
                message = active.get("done_text") or FOCUS_MODES[active["mode"]]["done_text"]
                return result_from_session(
                    active, "completed", message, completed=True, now=current
                )
            if active and active.get("status") == "active":
                remaining, _ = seconds_between(active["start_at"], active["end_at"], current)
                message = f"{active.get('label')}进行中，还剩 {format_seconds(remaining)}。"
                return result_from_session(active, "active", message, now=current)
            return result_from_session(
                None, "idle", "现在没有正在进行的番茄钟或专注模式。", now=current
            )

    def start(
        self,
        mode: str = "pomodoro",
        minutes: Optional[float] = None,
        task: str = "",
        force: bool = False,
        *,
        now: Optional[datetime] = None,
    ) -> TimerResult:
        with self._lock:
            current = now or self.clock()
            config = mode_config(mode)
            state = self.repository.load()
            active, _ = refresh_active(state, current)
            if active and active.get("status") == "active" and not force:
                remaining, _ = seconds_between(active["start_at"], active["end_at"], current)
                message = f"已经有一个{active.get('label')}在进行中，还剩 {format_seconds(remaining)}。"
                self.repository.save(state)
                return result_from_session(
                    active,
                    "active",
                    message,
                    already_active=True,
                    now=current,
                )
            if active and active.get("status") == "active" and force:
                active["status"] = "stopped"
                active["stopped_at"] = current.isoformat()
                active["stop_reason"] = "replaced"

            duration = float(minutes) if minutes and minutes > 0 else float(config["minutes"])
            end = current + timedelta(minutes=duration)
            session = {
                "id": self.id_factory(),
                "mode": mode,
                "label": config["label"],
                "task": task.strip(),
                "duration_minutes": duration,
                "start_at": current.isoformat(),
                "end_at": end.isoformat(),
                "status": "active",
                "start_text": config["start_text"],
                "done_text": config["done_text"],
                "created_at": current.isoformat(),
            }
            state["sessions"].append(session)
            state["active_id"] = session["id"]
            self.repository.save(state)
            task_part = f" 任务：{session['task']}" if session["task"] else ""
            message = f"{config['start_text']} 时长 {format_seconds(int(duration * 60))}。{task_part}"
            return result_from_session(
                session, "active", message, started=True, now=current
            )

    def stop(self, *, now: Optional[datetime] = None) -> TimerResult:
        with self._lock:
            current = now or self.clock()
            state = self.repository.load()
            active, just_completed = refresh_active(state, current)
            if active and just_completed:
                self.repository.save(state)
                message = active.get("done_text") or FOCUS_MODES[active["mode"]]["done_text"]
                return result_from_session(
                    active, "completed", message, completed=True, now=current
                )
            if not active or active.get("status") != "active":
                self.repository.save(state)
                return result_from_session(
                    None, "idle", "现在没有正在进行的计时。", now=current
                )
            active["status"] = "stopped"
            active["stopped_at"] = current.isoformat()
            state["active_id"] = None
            self.repository.save(state)
            return result_from_session(
                active,
                "stopped",
                "计时已经停止。没关系，重新开始也算继续照顾自己。",
                stopped=True,
                now=current,
            )

    def reset(self) -> int:
        with self._lock:
            state = self.repository.load()
            count = len(state.get("sessions", []))
            self.repository.save(self.repository.empty_state())
            return count

    def encouragement_snapshot(
        self,
        *,
        session_id: str,
        start_at: str,
        now: Optional[datetime] = None,
    ) -> TimerResult:
        result = self.status(now=now)
        if (
            not result.active
            or result.session_id != session_id
            or result.start_at != start_at
        ):
            raise FocusSessionInactiveError("focus_session_inactive")
        return result


class FocusEncouragementService:
    """Purpose-bound PK-200 generation consumer; it never writes chat history."""

    def __init__(
        self,
        focus_service: FocusService,
        text_generator_provider: Callable[[], Optional[FocusTextGenerator]],
    ):
        self.focus_service = focus_service
        self.text_generator_provider = text_generator_provider

    @staticmethod
    def _safe_code(value: object, fallback: str = "generation_failed") -> str:
        candidate = str(value or "").strip().lower()
        return candidate if SAFE_GENERATION_CODE.fullmatch(candidate) else fallback

    @staticmethod
    def _clean_text(value: object) -> str:
        text = re.sub(r"\[emotion:[^\]]+\]\s*", "", str(value or ""), flags=re.IGNORECASE)
        return " ".join(text.split())[:180].strip()

    async def generate(
        self,
        *,
        session_id: str,
        start_at: str,
    ) -> FocusEncouragementResponse:
        snapshot = self.focus_service.encouragement_snapshot(
            session_id=session_id,
            start_at=start_at,
        )
        elapsed_minutes = max(0, min(240, snapshot.elapsed_seconds // 60))
        remaining_minutes = max(0, min(240, math.ceil(snapshot.remaining_seconds / 60)))
        mode = snapshot.mode if snapshot.mode in FOCUS_MODES else "pomodoro"
        user = (
            f"模式：{mode}；已专注：{elapsed_minutes} 分钟；"
            f"剩余：{remaining_minutes} 分钟。请给出一次继续专注的鼓励。"
        )
        try:
            generator = self.text_generator_provider()
            if generator is None:
                return FocusEncouragementResponse(
                    eligible=True,
                    generated=False,
                    error_code="generator_unavailable",
                )
            system = (
                f"{generator.system_prompt}\n\n"
                "你正在为仍在进行中的专注会话生成一次鼓励，不是普通聊天。"
                "只输出一到两句简短中文，不要 Markdown、标题、emoji、情绪标签或解释。"
                "语气保持天童 Kei 的冷静、轻微嘴硬与关心，不要提及系统、模型、计时器或接口。"
            )
            result = await generator.generate_text(
                system,
                user,
                max_tokens=90,
                temperature=0.8,
                fallback="",
            )
        except Exception:
            return FocusEncouragementResponse(
                eligible=True,
                generated=False,
                error_code="generation_failed",
            )
        text = self._clean_text(result.text)
        generated = bool(result.generated and text)
        return FocusEncouragementResponse(
            eligible=True,
            generated=generated,
            text=text if generated else "",
            error_code=None if generated else self._safe_code(result.error_code),
        )


_DEFAULT_SERVICE = FocusService(FocusRepository())


def get_default_service() -> FocusService:
    return _DEFAULT_SERVICE


def get_status(
    store: Optional[FocusRepository] = None, now: Optional[datetime] = None
) -> TimerResult:
    return (FocusService(store) if store else _DEFAULT_SERVICE).status(now=now)


def start_timer(
    mode: str = "pomodoro",
    minutes: Optional[float] = None,
    task: str = "",
    force: bool = False,
    store: Optional[FocusRepository] = None,
    now: Optional[datetime] = None,
) -> TimerResult:
    return (FocusService(store) if store else _DEFAULT_SERVICE).start(
        mode=mode, minutes=minutes, task=task, force=force, now=now
    )


def stop_timer(
    store: Optional[FocusRepository] = None, now: Optional[datetime] = None
) -> TimerResult:
    return (FocusService(store) if store else _DEFAULT_SERVICE).stop(now=now)


def reset(store: Optional[FocusRepository] = None) -> int:
    return (FocusService(store) if store else _DEFAULT_SERVICE).reset()
