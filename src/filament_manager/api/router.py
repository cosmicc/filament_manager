"""Compose the complete versioned API router."""

from fastapi import APIRouter

from .routes import (
    auth,
    calibrations,
    diagnostics,
    imports,
    inventory,
    notifications,
    nozzles,
    operations,
    plates,
    printing,
    profiles,
    workstations,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(imports.router)
api_router.include_router(inventory.router)
api_router.include_router(plates.router)
api_router.include_router(profiles.router)
api_router.include_router(calibrations.router)
api_router.include_router(diagnostics.router)
api_router.include_router(printing.router)
api_router.include_router(notifications.router)
api_router.include_router(nozzles.router)
api_router.include_router(operations.router)
api_router.include_router(workstations.router)
