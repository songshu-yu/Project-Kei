"""Fitness module public surface."""

from .compatibility import check_in, get_status, reset
from .module import register, unregister
from .models import FitnessCheckinResult
from .repository import (
    DEFAULT_STORE,
    FitnessCheckinStore,
    FitnessPersistenceError,
    FitnessRepository,
    FitnessStateError,
)
from .router import create_fitness_router
from .security import FitnessOriginGuardMiddleware, default_local_control_guard
from .service import KEI_REWARDS, REWARD_STREAK_DAYS, FitnessService

__all__ = [
    "DEFAULT_STORE",
    "FitnessCheckinResult",
    "FitnessCheckinStore",
    "FitnessOriginGuardMiddleware",
    "FitnessPersistenceError",
    "FitnessRepository",
    "FitnessService",
    "FitnessStateError",
    "KEI_REWARDS",
    "REWARD_STREAK_DAYS",
    "check_in",
    "create_fitness_router",
    "default_local_control_guard",
    "get_status",
    "register",
    "reset",
    "unregister",
]
