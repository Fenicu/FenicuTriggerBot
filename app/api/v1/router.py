from fastapi import APIRouter

from app.api.v1.endpoints import auth, captcha, chats, media, preview, stats, system, triggers, users, welcome

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(chats.router, prefix="/chats", tags=["chats"])
api_router.include_router(triggers.router, prefix="/triggers", tags=["triggers"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(stats.router, prefix="/stats", tags=["stats"])
api_router.include_router(system.router, prefix="/system", tags=["system"])
api_router.include_router(media.router, prefix="/media", tags=["media"])
api_router.include_router(captcha.router, prefix="/captcha", tags=["captcha"])
api_router.include_router(welcome.router, prefix="/chats", tags=["welcome"])
api_router.include_router(preview.router, prefix="/triggers", tags=["preview"])
