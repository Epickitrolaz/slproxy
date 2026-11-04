"""
Router API (/routerapi) Contract & Stub
"""

from fastapi import APIRouter

router = APIRouter(prefix="/routerapi")


@router.get("/health")
async def health_check():
    return {"status": "ok", "service": "SLProxy Router API"}


@router.get("/v1/models")
async def list_models():
    return {"object": "list", "data": []}


@router.post("/v1/chat/completions")
async def chat_completions():
    raise NotImplementedError


@router.post("/v1/messages")
async def anthropic_messages():
    raise NotImplementedError
