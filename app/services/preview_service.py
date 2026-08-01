import base64
import hashlib
import hmac
import html
import json
import logging
import re
import time

from aiogram.types import Message

from app.core.config import settings
from app.db.models.trigger import Trigger

logger = logging.getLogger(__name__)

_FILE_TYPE_KEYS = ("photo", "video", "video_note", "animation", "document", "sticker", "voice", "audio")

SAFE_TAGS = {"b", "i", "u", "s", "code", "pre", "a", "tg-spoiler", "blockquote"}
SAFE_PROTOCOLS = {"http", "https", "tg"}

# Карточка модерации живёт в канале долго (пока модератор не дойдёт до неё),
# поэтому срок токена превью — неделя, а не часы.
PREVIEW_TOKEN_TTL_SECONDS = 7 * 24 * 60 * 60


def generate_preview_token(trigger_id: int, ttl_seconds: int = PREVIEW_TOKEN_TTL_SECONDS) -> str:
    """Генерирует подписанный токен превью с ограниченным сроком годности."""
    payload = json.dumps(
        {"tid": trigger_id, "exp": int(time.time()) + ttl_seconds},
        separators=(",", ":"),
    )
    encoded = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")
    signature = hmac.new(settings.BOT_TOKEN.encode(), encoded.encode(), hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}"


def verify_preview_token(trigger_id: int, token: str) -> bool:
    """Проверяет токен превью: подпись, привязку к trigger_id и срок годности."""
    parts = token.split(".")
    if len(parts) != 2:
        return False

    encoded, signature = parts
    expected_signature = hmac.new(settings.BOT_TOKEN.encode(), encoded.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected_signature):
        return False

    padded = encoded + "=" * (-len(encoded) % 4)
    try:
        payload = json.loads(base64.urlsafe_b64decode(padded))
    except (ValueError, UnicodeDecodeError):
        return False

    if payload.get("tid") != trigger_id:
        return False

    return payload.get("exp", 0) >= time.time()


def generate_preview_url(trigger_id: int) -> str:
    """Generate full preview URL for a trigger."""
    token = generate_preview_token(trigger_id)
    base = settings.WEBAPP_URL.rstrip("/")
    prefix = settings.URL_PREFIX
    return f"{base}{prefix}{settings.API_V1_STR}/triggers/{trigger_id}/preview?token={token}"


def _sanitize_url(url: str) -> str:
    """Allow only safe URL protocols."""
    protocol = url.split(":", 1)[0].lower() if ":" in url else ""
    if protocol in SAFE_PROTOCOLS:
        return url
    return "#"


def _sanitize_html(text: str) -> str:
    """Sanitize HTML: allow only safe tags, strip all attributes except href on <a>."""

    def replace_tag(match: re.Match) -> str:
        full = match.group(0)
        tag_name = match.group(1).lower().strip("/")
        is_closing = full.startswith("</")
        if tag_name not in SAFE_TAGS:
            return html.escape(full)
        # Closing tags: strip attributes
        if is_closing:
            return f"</{tag_name}>"
        # <a> tag: keep only href with safe protocol
        if tag_name == "a":
            href_match = re.search(r"""href=["']([^"']*)["']""", full)
            if href_match:
                safe_url = _sanitize_url(href_match.group(1))
                return f'<a href="{html.escape(safe_url)}">'
            return "<a>"
        # All other safe tags: strip all attributes
        return f"<{tag_name}>"

    return re.sub(r"<(/?\w[\w-]*)[^>]*>", replace_tag, text)


def render_trigger_text(trigger: Trigger) -> str:
    """Convert trigger content to sanitized HTML text."""
    content = trigger.content
    if not isinstance(content, dict):
        return ""

    try:
        msg_data = dict(content)
        if "message_id" not in msg_data:
            msg_data["message_id"] = 0
        if "date" not in msg_data:
            msg_data["date"] = 0
        if "chat" not in msg_data:
            msg_data["chat"] = {"id": 0, "type": "private"}

        msg = Message.model_validate(msg_data)

        if msg.text:
            return _sanitize_html(msg.html_text)
        if msg.caption:
            raw = msg.caption
            if msg.caption_entities:
                from aiogram.utils.text_decorations import html_decoration  # noqa: PLC0415

                raw = html_decoration.unparse(msg.caption, msg.caption_entities)
            return _sanitize_html(raw)
    except Exception:
        logger.debug("Failed to deserialize trigger %d content as Message, using fallback", trigger.id)

    raw_text = content.get("text") or content.get("caption") or ""
    if not raw_text:
        return ""
    return html.escape(raw_text)


def _get_file_info(content: dict) -> tuple[str | None, str | None]:
    """Extract file_id and file_type from trigger content."""
    for key in _FILE_TYPE_KEYS:
        if content.get(key):
            if key == "photo":
                return content["photo"][-1]["file_id"], key
            return content[key]["file_id"], key
    return None, None


def get_media_info(trigger: Trigger) -> dict | None:
    """Extract media info for template rendering."""
    content = trigger.content
    if not isinstance(content, dict):
        return None
    file_id, file_type = _get_file_info(content)
    if not file_id:
        return None

    info: dict = {"file_id": file_id, "type": file_type}

    if file_type == "document":
        doc = content.get("document", {})
        info["file_name"] = doc.get("file_name", "Unknown")
        info["file_size"] = doc.get("file_size")

    if file_type == "sticker":
        sticker = content.get("sticker", {})
        if sticker.get("is_animated"):
            info["is_tgs"] = True

    return info


def get_buttons_info(trigger: Trigger) -> list[list[dict]] | None:
    """Extract inline keyboard buttons for template rendering."""
    if not isinstance(trigger.content, dict):
        return None
    reply_markup = trigger.content.get("reply_markup")
    if not reply_markup:
        return None

    keyboard = reply_markup.get("inline_keyboard")
    if not keyboard:
        return None

    rows: list[list[dict]] = []
    for row in keyboard:
        buttons: list[dict] = []
        for btn in row:
            button: dict = {"text": btn.get("text", "")}
            if btn.get("url"):
                button["url"] = _sanitize_url(btn["url"])
            elif btn.get("callback_data"):
                button["callback_data"] = btn["callback_data"]
            buttons.append(button)
        if buttons:
            rows.append(buttons)

    return rows or None


def get_dice_info(trigger: Trigger) -> dict | None:
    """Extract dice info for template rendering."""
    if not isinstance(trigger.content, dict):
        return None
    dice = trigger.content.get("dice")
    if not dice:
        return None
    return {"emoji": dice.get("emoji", "\U0001f3b2"), "value": dice.get("value", "?")}
