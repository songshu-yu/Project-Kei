"""Legacy Python-call compatibility backed by the fitness service."""

from __future__ import annotations

from typing import Optional, Tuple

from .models import FitnessCheckinResult
from .repository import FitnessRepository
from .service import FitnessService


def _service(store: Optional[FitnessRepository]) -> FitnessService:
    return FitnessService(store or FitnessRepository())


def get_status(day: Optional[str] = None, store: Optional[FitnessRepository] = None) -> dict:
    return _service(store).get_status(day)


def check_in(
    day: Optional[str] = None,
    note: str = "",
    store: Optional[FitnessRepository] = None,
) -> FitnessCheckinResult:
    return _service(store).check_in(day, note)


def reset(store: Optional[FitnessRepository] = None) -> Tuple[int, int]:
    return _service(store).reset()


__all__ = ["check_in", "get_status", "reset"]
