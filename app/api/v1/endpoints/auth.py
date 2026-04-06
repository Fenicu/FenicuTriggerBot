"""Аутентификация через Telegram OIDC."""

import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
from urllib.parse import quote

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from starlette.requests import Request
from starlette.responses import RedirectResponse

from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

# Хранилище одноразовых кодов: {code: {"token": ..., "name": ..., "expires": ...}}
_pending_codes: dict[str, dict] = {}
_CODE_TTL = 60  # секунд

# === Токены ===


def create_auth_token(user_id: int, ttl_seconds: int = 7 * 86400) -> str:
    """Создаёт подписанный токен. Формат: base64(payload).hmac_signature."""
    payload = json.dumps({"uid": user_id, "exp": int(time.time()) + ttl_seconds}, separators=(",", ":"))
    encoded = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")
    signature = hmac.new(settings.BOT_TOKEN.encode(), encoded.encode(), hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}"


def verify_auth_token(token: str) -> int | None:
    """Проверяет подписанный токен. Возвращает user_id или None."""
    parts = token.split(".")
    if len(parts) != 2:
        return None

    encoded, signature = parts
    expected = hmac.new(settings.BOT_TOKEN.encode(), encoded.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None

    padded = encoded + "=" * (4 - len(encoded) % 4)
    try:
        payload = json.loads(base64.urlsafe_b64decode(padded))
    except (json.JSONDecodeError, Exception):
        return None

    if payload.get("exp", 0) < time.time():
        return None

    return payload.get("uid")


# === OAuth клиент ===

oauth = OAuth()

if settings.TELEGRAM_OIDC_CLIENT_ID:
    oauth.register(
        name="telegram",
        client_id=settings.TELEGRAM_OIDC_CLIENT_ID,
        client_secret=settings.TELEGRAM_OIDC_CLIENT_SECRET,
        server_metadata_url="https://oauth.telegram.org/.well-known/openid-configuration",
        client_kwargs={
            "scope": "openid profile telegram:bot_access",
            "code_challenge_method": "S256",
        },
    )


# === Эндпоинты ===


@router.get("/telegram-oidc/login")
async def telegram_oidc_login(request: Request) -> RedirectResponse:
    """Начать Telegram OIDC авторизацию."""
    if not settings.TELEGRAM_OIDC_CLIENT_ID:
        raise HTTPException(status_code=503, detail="Telegram OIDC не настроен")
    redirect_uri = settings.TELEGRAM_OIDC_REDIRECT_URI
    return await oauth.telegram.authorize_redirect(request, redirect_uri)


@router.get("/telegram-oidc/callback")
async def telegram_oidc_callback(request: Request) -> RedirectResponse:
    """Callback от Telegram OIDC."""
    token = await oauth.telegram.authorize_access_token(request)
    userinfo = token.get("userinfo") or {}

    telegram_id = userinfo.get("id")
    if not telegram_id:
        raise HTTPException(status_code=400, detail="Telegram OIDC: отсутствует id в токене")
    telegram_id = int(telegram_id)

    name = userinfo.get("name", "")
    username = userinfo.get("preferred_username", "")

    logger.info("Telegram OIDC login: id=%d name=%s username=%s", telegram_id, name, username)

    auth_token = create_auth_token(telegram_id)

    code = secrets.token_urlsafe(32)
    _pending_codes[code] = {"token": auth_token, "name": name or "", "expires": time.time() + _CODE_TTL}

    # Webapp живёт на /webapp, роутинг через HashRouter
    webapp_url = settings.WEBAPP_URL.rstrip("/")
    return RedirectResponse(url=f"{webapp_url}/webapp/?oidc_code={code}&oidc_name={quote(name or '', safe='')}#/login")


class OidcExchangeRequest(BaseModel):
    """Запрос на обмен одноразового кода на токен."""

    code: str


@router.post("/oidc/exchange")
async def oidc_exchange(req: OidcExchangeRequest) -> dict:
    """Обменять одноразовый код на токен авторизации."""
    now = time.time()
    expired = [k for k, v in _pending_codes.items() if v["expires"] < now]
    for k in expired:
        del _pending_codes[k]

    entry = _pending_codes.pop(req.code, None)
    if not entry:
        raise HTTPException(status_code=403, detail="Invalid or expired code")

    return {"token": entry["token"], "name": entry["name"]}
