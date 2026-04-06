from fastapi import APIRouter

from app.core.config import settings

router = APIRouter()


@router.get("/config")
async def get_config() -> dict[str, bool]:
    """Получить публичную конфигурацию авторизации."""
    return {"telegram_oidc_enabled": bool(settings.TELEGRAM_OIDC_CLIENT_ID)}
