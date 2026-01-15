from fastapi import APIRouter

from app.api.v1.endpoints import captcha, chats, stats, system, triggers, users

api_router = APIRouter()

api_router.include_router(chats.router, prefix="/chats", tags=["chats"])
api_router.include_router(triggers.router, prefix="/triggers", tags=["triggers"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(stats.router, prefix="/stats", tags=["stats"])
api_router.include_router(system.router, prefix="/system", tags=["system"])
api_router.include_router(captcha.router, prefix="/captcha", tags=["captcha"])
