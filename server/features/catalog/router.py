"""Read-only feature discovery routes."""

from fastapi import APIRouter

from .models import ModuleCatalogResponse
from .service import get_module_catalog


router = APIRouter(prefix="/api/v1", tags=["modules"])


@router.get("/modules", response_model=ModuleCatalogResponse)
async def list_modules() -> dict:
    return get_module_catalog()
