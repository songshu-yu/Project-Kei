"""Versioned and legacy HTTP routes backed by one demon-slayer service."""

from __future__ import annotations

import base64
from typing import Any, Awaitable, Callable, Optional

from fastapi import APIRouter, HTTPException

from .models import (
    CheckinRequest,
    GoalCreateRequest,
    GoalUpdateRequest,
    LegacyCheckinRequest,
    LegacyPlanRequest,
    LegacyRedeemRequest,
    RewardCreateRequest,
    RewardRedeemRequest,
)
from .repository import DemonSlayerPersistenceError, DemonSlayerStateError
from .service import DemonSlayerService


AudioSynthesizer = Callable[[str, str], Awaitable[Optional[bytes]]]


def _invoke(operation: Callable[[], Any]) -> Any:
    try:
        return operation()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="demon-slayer item was not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except DemonSlayerStateError as exc:
        raise HTTPException(status_code=500, detail="demon-slayer state is invalid") from exc
    except DemonSlayerPersistenceError as exc:
        raise HTTPException(status_code=500, detail="demon-slayer state could not be saved") from exc


async def _invoke_async(operation: Callable[[], Awaitable[Any]]) -> Any:
    try:
        return await operation()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="demon-slayer item was not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except DemonSlayerStateError as exc:
        raise HTTPException(status_code=500, detail="demon-slayer state is invalid") from exc
    except DemonSlayerPersistenceError as exc:
        raise HTTPException(status_code=500, detail="demon-slayer state could not be saved") from exc


def create_demon_slayer_router(
    service: DemonSlayerService,
    *,
    audio_synthesizer: Optional[AudioSynthesizer] = None,
) -> APIRouter:
    router = APIRouter(tags=["demon-slayer"])

    async def status_handler(date: Optional[str] = None) -> dict:
        return _invoke(lambda: service.get_status(date))

    async def list_goals_handler(include_inactive: bool = False) -> dict:
        goals = _invoke(lambda: service.list_goals(include_inactive=include_inactive))
        return {"goals": goals, "count": len(goals)}

    async def create_goal_handler(request: GoalCreateRequest) -> dict:
        return _invoke(lambda: service.add_goal(
            request.title,
            cadence=request.cadence,
            category=request.category,
            repeat_mode=request.repeat_mode,
            target_date=request.target_date,
        ))

    async def update_goal_handler(goal_id: str, request: GoalUpdateRequest) -> dict:
        return _invoke(lambda: service.update_goal(
            goal_id,
            title=request.title,
            cadence=request.cadence,
            category=request.category,
            repeat_mode=request.repeat_mode,
            target_date=request.target_date,
        ))

    async def delete_goal_handler(goal_id: str) -> dict:
        return _invoke(lambda: service.delete_goal(goal_id))

    async def checkin_handler(request: CheckinRequest) -> dict:
        if request.with_encouragement:
            result = await _invoke_async(lambda: service.check_in_with_encouragement(
                request.goal_id,
                day=request.date,
                done=request.done,
                note=request.note,
            ))
        else:
            result = _invoke(lambda: service.check_in(
                request.goal_id,
                day=request.date,
                done=request.done,
                note=request.note,
            ))
        return result.to_dict()

    async def review_handler(period: str, anchor: Optional[str] = None) -> dict:
        return await _invoke_async(lambda: service.review(period, anchor=anchor))

    async def create_reward_handler(request: RewardCreateRequest) -> dict:
        reward = _invoke(lambda: service.add_reward(request.title, request.cost, request.description))
        return {"status": "ok", "reward": reward}

    async def redeem_reward_handler(reward_id: str, request: Optional[RewardRedeemRequest] = None) -> dict:
        return _invoke(lambda: service.redeem_reward(
            reward_id,
            request_id=request.request_id if request else None,
        ))

    router.add_api_route("/api/v1/demon-slayer/status", status_handler, methods=["GET"], name="demon_status_versioned")
    router.add_api_route("/api/v1/demon-slayer/goals", list_goals_handler, methods=["GET"], name="demon_goals_list_versioned")
    router.add_api_route("/api/v1/demon-slayer/goals", create_goal_handler, methods=["POST"], name="demon_goal_create_versioned")
    router.add_api_route("/api/v1/demon-slayer/goals/{goal_id}", update_goal_handler, methods=["PATCH"], name="demon_goal_update_versioned")
    router.add_api_route("/api/v1/demon-slayer/goals/{goal_id}", delete_goal_handler, methods=["DELETE"], name="demon_goal_delete_versioned")
    router.add_api_route("/api/v1/demon-slayer/checkins", checkin_handler, methods=["POST"], name="demon_checkin_versioned")
    router.add_api_route("/api/v1/demon-slayer/reviews/{period}", review_handler, methods=["GET"], name="demon_review_versioned")
    router.add_api_route("/api/v1/demon-slayer/rewards", create_reward_handler, methods=["POST"], name="demon_reward_create_versioned")
    router.add_api_route("/api/v1/demon-slayer/rewards/{reward_id}/redeem", redeem_reward_handler, methods=["POST"], name="demon_reward_redeem_versioned")

    async def legacy_plan_handler(request: LegacyPlanRequest) -> dict:
        try:
            result = service.create_plan(
                request.text,
                reset_existing=request.reset_existing,
                cadence=request.cadence,
                category=request.category,
                repeat_mode=request.repeat_mode,
                target_date=request.target_date,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except DemonSlayerStateError as exc:
            raise HTTPException(status_code=500, detail="demon-slayer state is invalid") from exc
        except DemonSlayerPersistenceError as exc:
            raise HTTPException(status_code=500, detail="demon-slayer state could not be saved") from exc
        result["audio_base64"] = ""
        if request.with_audio and audio_synthesizer:
            audio = await audio_synthesizer(str(result.get("message", "")), "calm")
            if audio:
                result["audio_base64"] = base64.b64encode(audio).decode()
        return result

    async def legacy_checkin_handler(request: LegacyCheckinRequest) -> dict:
        try:
            if request.with_encouragement:
                checkin = await service.check_in_with_encouragement(
                    request.goal_id,
                    day=request.date,
                    done=request.done,
                    note=request.note,
                )
            else:
                checkin = service.check_in(
                    request.goal_id,
                    day=request.date,
                    done=request.done,
                    note=request.note,
                )
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=404, detail="Goal not found, inactive, or outside its target period") from exc
        except DemonSlayerStateError as exc:
            raise HTTPException(status_code=500, detail="demon-slayer state is invalid") from exc
        except DemonSlayerPersistenceError as exc:
            raise HTTPException(status_code=500, detail="demon-slayer state could not be saved") from exc
        result = checkin.to_dict()
        result["audio_base64"] = ""
        if request.with_audio and audio_synthesizer:
            audio = await audio_synthesizer(checkin.message, "happy" if checkin.done else "sad")
            if audio:
                result["audio_base64"] = base64.b64encode(audio).decode()
        return result

    async def legacy_reminder_handler(date: Optional[str] = None) -> dict:
        return {"date": date, "message": _invoke(lambda: service.reminder(date))}

    async def legacy_daily_review_handler(date: Optional[str] = None) -> dict:
        return await _invoke_async(lambda: service.evaluate_review(service.daily_review(date)))

    async def legacy_weekly_review_handler(week_start: Optional[str] = None) -> dict:
        return await _invoke_async(lambda: service.evaluate_review(service.weekly_review(week_start)))

    async def legacy_monthly_review_handler(month: Optional[str] = None) -> dict:
        return await _invoke_async(lambda: service.evaluate_review(service.monthly_review(month)))

    async def legacy_yearly_review_handler(year: Optional[str] = None) -> dict:
        return await _invoke_async(lambda: service.evaluate_review(service.yearly_review(year)))

    async def legacy_wish_handler(request: RewardCreateRequest) -> dict:
        reward = _invoke(lambda: service.add_reward(request.title, request.cost, request.description))
        return {"status": "ok", "wish": reward}

    async def legacy_redeem_handler(request: LegacyRedeemRequest) -> dict:
        return _invoke(lambda: service.redeem_reward(request.wish_id, request_id=request.request_id))

    async def legacy_reset_handler() -> dict:
        return {"status": "ok", "cleared": _invoke(service.reset)}

    router.add_api_route("/demon/status", status_handler, methods=["GET"], name="demon_status_legacy")
    router.add_api_route("/demon/plan", legacy_plan_handler, methods=["POST"], name="demon_plan_legacy")
    router.add_api_route("/demon/goals/{goal_id}", delete_goal_handler, methods=["DELETE"], name="demon_goal_delete_legacy")
    router.add_api_route("/demon/checkin", legacy_checkin_handler, methods=["POST"], name="demon_checkin_legacy")
    router.add_api_route("/demon/reminder", legacy_reminder_handler, methods=["GET"], name="demon_reminder_legacy")
    router.add_api_route("/demon/review/daily", legacy_daily_review_handler, methods=["GET"], name="demon_review_daily_legacy")
    router.add_api_route("/demon/review/weekly", legacy_weekly_review_handler, methods=["GET"], name="demon_review_weekly_legacy")
    router.add_api_route("/demon/review/monthly", legacy_monthly_review_handler, methods=["GET"], name="demon_review_monthly_legacy")
    router.add_api_route("/demon/review/yearly", legacy_yearly_review_handler, methods=["GET"], name="demon_review_yearly_legacy")
    router.add_api_route("/demon/wish", legacy_wish_handler, methods=["POST"], name="demon_wish_legacy")
    router.add_api_route("/demon/redeem", legacy_redeem_handler, methods=["POST"], name="demon_redeem_legacy")
    router.add_api_route("/demon/reset", legacy_reset_handler, methods=["POST"], name="demon_reset_legacy")
    return router


__all__ = ["create_demon_slayer_router"]
