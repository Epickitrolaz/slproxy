"""
Admin API for WebUI (/api) Contract & Stub
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api")


@router.get("/plugins")
async def get_plugins():
    return []


@router.get("/accounts")
async def get_accounts():
    return []


@router.get("/keys")
async def get_keys():
    return []


@router.get("/metrics")
async def get_metrics():
    return {}
