import logging
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import settings
from app.core.database import engine
from app.db.models.trigger import Trigger
from app.services.preview_service import (
    get_buttons_info,
    get_dice_info,
    get_media_info,
    render_trigger_text,
    verify_preview_token,
)

router = APIRouter()
logger = logging.getLogger(__name__)
templates = Jinja2Templates(directory="app/templates")

async_session = async_sessionmaker(engine, expire_on_commit=False)


@router.get("/{trigger_id}/preview", response_class=HTMLResponse)
async def trigger_preview(request: Request, trigger_id: int, token: str = "") -> HTMLResponse:
    """Render trigger content preview page with HMAC verification."""
    if not token or not verify_preview_token(trigger_id, token):
        raise HTTPException(status_code=403, detail="Forbidden")

    async with async_session() as session:
        trigger = await session.get(Trigger, trigger_id)
        if not trigger or trigger.is_deleted:
            raise HTTPException(status_code=404, detail="Not found")

        # Format created_at using project timezone
        created_at = "—"
        if trigger.created_at:
            try:
                dt = trigger.created_at
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=ZoneInfo("UTC"))
                tz = ZoneInfo(settings.BOT_TIMEZONE)
                created_at = dt.astimezone(tz).strftime("%d.%m.%Y %H:%M")
            except Exception:
                created_at = str(trigger.created_at)

        # Build API prefix for media URLs in template
        api_prefix = f"{settings.URL_PREFIX}{settings.API_V1_STR}"

        return templates.TemplateResponse(
            request=request,
            name="trigger_preview.html",
            context={
                "trigger": trigger,
                "created_at": created_at,
                "text_html": render_trigger_text(trigger),
                "media": get_media_info(trigger),
                "buttons": get_buttons_info(trigger),
                "dice": get_dice_info(trigger),
                "api_prefix": api_prefix,
            },
        )
