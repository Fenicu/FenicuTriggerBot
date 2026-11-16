from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_authenticated_user
from app.api.v1.endpoints import welcome
from app.core.database import get_db


async def request_upload(body, headers, *, authorized=True, chat_admin=True):
    app = FastAPI()
    app.include_router(welcome.router)

    async def auth():
        if not authorized:
            raise HTTPException(401, "Unauthorized")
        return MagicMock()

    app.dependency_overrides[get_authenticated_user] = auth
    app.dependency_overrides[get_db] = lambda: None
    rights = AsyncMock(side_effect=None if chat_admin else HTTPException(403, "Forbidden"))
    with patch.object(welcome, "require_chat_admin", rights):
        async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
            return await client.post("/1/welcome-media", content=body, headers=headers)


async def test_auth_happens_before_body_read():
    async def unreadable():
        pytest.fail("Unauthenticated request body was consumed")
        yield b""

    response = await request_upload(unreadable(), {"content-type": "multipart/form-data; boundary=x"}, authorized=False)
    assert response.status_code == 401


async def test_content_length_checked_before_body_read():
    async def unreadable():
        pytest.fail("Oversized request body was consumed")
        yield b""

    response = await request_upload(
        unreadable(),
        {"content-type": "multipart/form-data; boundary=x", "content-length": str(12 * 1024 * 1024)},
    )
    assert response.status_code == 400
    assert "too large" in response.json()["detail"].lower()


async def test_chunked_upload_stops_reading_at_limit(monkeypatch):
    monkeypatch.setattr(welcome, "MAX_FILE_SIZE", 64)
    reads = 0

    async def chunks():
        nonlocal reads
        yield b'--x\r\nContent-Disposition: form-data; name="file"; filename="a.jpg"\r\nContent-Type: image/jpeg\r\n\r\n'
        for _ in range(100):
            reads += 1
            yield b"a" * 65536
        yield b"\r\n--x--\r\n"

    response = await request_upload(chunks(), {"content-type": "multipart/form-data; boundary=x"})
    assert response.status_code == 400
    assert "too large" in response.json()["detail"].lower()
    assert reads <= 2


async def test_chat_permissions_checked_before_body_read():
    async def unreadable():
        pytest.fail("Forbidden request body was consumed")
        yield b""

    response = await request_upload(unreadable(), {"content-type": "multipart/form-data; boundary=x"}, chat_admin=False)
    assert response.status_code == 403


async def test_uploaded_file_read_is_bounded(monkeypatch):
    monkeypatch.setattr(welcome, "MAX_FILE_SIZE", 64)
    file = MagicMock(content_type="image/jpeg")
    file.read = AsyncMock(return_value=b"x" * 65)
    with pytest.raises(HTTPException) as exc:
        await welcome._upload_welcome_file(file)
    assert exc.value.status_code == 400
    file.read.assert_awaited_once_with(65)


@pytest.mark.parametrize("size,status", [(64, 200), (65, 400)])
async def test_multipart_file_size_boundary(monkeypatch, size, status):
    monkeypatch.setattr(welcome, "MAX_FILE_SIZE", 64)
    body = (
        b'--x\r\nContent-Disposition: form-data; name="file"; filename="a.jpg"\r\nContent-Type: image/jpeg\r\n\r\n'
        + b"\xff\xd8\xff"
        + b"x" * (size - 3)
        + b"\r\n--x--\r\n"
    )
    bot = AsyncMock()
    bot.send_photo.return_value = MagicMock(photo=[MagicMock(file_id="stored")], message_id=1)
    with patch.object(welcome, "bot", bot):
        response = await request_upload(body, {"content-type": "multipart/form-data; boundary=x"})
    assert response.status_code == status
    if status == 200:
        assert response.json() == {"file_id": "stored", "file_type": "photo"}
    else:
        bot.send_photo.assert_not_awaited()
