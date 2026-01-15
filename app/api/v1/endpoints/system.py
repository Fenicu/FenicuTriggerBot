from fastapi import APIRouter

from app.core.config import settings

router = APIRouter()


@router.get("/config")
async def get_config() -> dict[str, str | None]:
    """Получить публичную конфигурацию."""
    return {"bot_username": settings.BOT_USERNAME}
