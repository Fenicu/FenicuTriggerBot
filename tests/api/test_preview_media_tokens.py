import html
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from urllib.parse import parse_qs, urlsplit

import pytest

from app.api.v1.endpoints import media, preview
from app.services.preview_service import PREVIEW_TOKEN_TTL_SECONDS, generate_preview_token
from tests.factories import create_chat, create_trigger


@pytest.mark.parametrize("media_type", ["photo", "sticker", "video", "animation", "voice", "audio"])
async def test_preview_proxy_url_has_valid_bound_token(api_client, db_session, monkeypatch, media_type):
    file_id = "telegram+file/id&name=?value#fragment"
    payload = {"file_id": file_id}
    content = {media_type: [payload] if media_type == "photo" else payload}
    chat = await create_chat(db_session)
    trigger = await create_trigger(db_session, chat.id, content=content)
    await db_session.commit()
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=db_session)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(preview, "async_session", factory)
    now = 1_800_000_000
    monkeypatch.setattr(media, "time", SimpleNamespace(time=lambda: now))
    response = await api_client.get(f"/api/v1/triggers/{trigger.id}/preview?token={generate_preview_token(trigger.id)}")
    assert response.status_code == 200
    proxy_urls = re.findall(r'src="([^"]*/media/proxy\?[^"]+)"', response.text)
    assert len(proxy_urls) == 1
    query = parse_qs(urlsplit(html.unescape(proxy_urls[0])).query)
    assert query["file_id"] == [file_id]
    token = query.get("token", [""])[0]
    assert media.verify_media_token(file_id, token)
    assert not media.verify_media_token("another-file", token)
    monkeypatch.setattr(media.time, "time", lambda: now + PREVIEW_TOKEN_TTL_SECONDS - 1)
    assert media.verify_media_token(file_id, token)
    monkeypatch.setattr(media.time, "time", lambda: now + PREVIEW_TOKEN_TTL_SECONDS + 1)
    assert not media.verify_media_token(file_id, token)
