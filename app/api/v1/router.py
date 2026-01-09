from fastapi import APIRouter

from app.api.v1.endpoints import chats, users

api_router = APIRouter()


@api_router.get("", tags=["status"])
async def api_status() -> dict[str, str]:
    """Статус API."""
    return {"status": "ok"}


api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(chats.router, prefix="/chats", tags=["chats"])
