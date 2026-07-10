"""Tests for app/worker/asr.py — transcribe() ASR client."""

import json

import aiohttp
import pytest

from app.worker.asr import AsrResult, transcribe


class _FakeResp:
    def __init__(self, status, payload=None, json_exc=None):
        self.status = status
        self._payload = payload
        self._json_exc = json_exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def json(self):
        if self._json_exc is not None:
            raise self._json_exc
        return self._payload

    async def text(self):
        return str(self._payload)


class _FakeSession:
    """Captures post() call args/kwargs so tests can inspect headers/body."""

    def __init__(self, resp):
        self._resp = resp
        self.post_call_args = None
        self.post_call_kwargs = None

    def post(self, *a, **k):
        self.post_call_args = a
        self.post_call_kwargs = k
        return self._resp


class _FakeSessionPostRaises:
    """post() raises immediately — simulates a connection-level failure."""

    def __init__(self, exc):
        self._exc = exc

    def post(self, *a, **k):
        raise self._exc


@pytest.mark.asyncio
async def test_transcribe_success(monkeypatch):
    from app.worker import asr
    monkeypatch.setattr(asr.settings, "ASR_ENABLED", True)
    monkeypatch.setattr(asr.settings.ASR_TOKEN, "get_secret_value", lambda: "tok", raising=False)
    resp = _FakeResp(200, {"transcript": "привет мир", "language": "ru", "duration": 1.5})
    session = _FakeSession(resp)

    async def fake_get_session():
        return session

    monkeypatch.setattr(asr, "get_session", fake_get_session)
    result = await transcribe(b"oggdata", "voice.ogg")
    assert isinstance(result, AsrResult)
    assert result.transcript == "привет мир"
    assert result.language == "ru"
    assert result.duration == 1.5

    headers = session.post_call_kwargs["headers"]
    assert headers["Authorization"] == "Bearer tok"
    form = session.post_call_kwargs["data"]
    assert isinstance(form, aiohttp.FormData)
    field_name = form._fields[0][0]["name"]
    assert field_name == "file"


@pytest.mark.asyncio
async def test_transcribe_server_error_returns_none(monkeypatch):
    from app.worker import asr
    monkeypatch.setattr(asr.settings, "ASR_ENABLED", True)
    resp = _FakeResp(503, {"detail": "loading"})

    async def fake_get_session():
        return _FakeSession(resp)

    monkeypatch.setattr(asr, "get_session", fake_get_session)
    assert await transcribe(b"x", "voice.ogg") is None


@pytest.mark.asyncio
async def test_transcribe_skipped_413_returns_none(monkeypatch):
    from app.worker import asr
    monkeypatch.setattr(asr.settings, "ASR_ENABLED", True)
    resp = _FakeResp(413, {"transcript": "", "skipped": "too_large"})

    async def fake_get_session():
        return _FakeSession(resp)

    monkeypatch.setattr(asr, "get_session", fake_get_session)
    assert await transcribe(b"x", "voice.ogg") is None


@pytest.mark.asyncio
async def test_transcribe_disabled_no_network_call(monkeypatch):
    """ASR_ENABLED=False должен вернуть None, не дойдя до get_session()/post()."""
    from app.worker import asr
    monkeypatch.setattr(asr.settings, "ASR_ENABLED", False)

    async def fake_get_session():
        raise AssertionError("get_session() must not be called when ASR_ENABLED=False")

    monkeypatch.setattr(asr, "get_session", fake_get_session)
    assert await transcribe(b"x", "voice.ogg") is None


@pytest.mark.asyncio
async def test_transcribe_empty_transcript(monkeypatch):
    from app.worker import asr
    monkeypatch.setattr(asr.settings, "ASR_ENABLED", True)
    resp = _FakeResp(200, {"transcript": "", "language": "ru", "duration": 0.5})

    async def fake_get_session():
        return _FakeSession(resp)

    monkeypatch.setattr(asr, "get_session", fake_get_session)
    result = await transcribe(b"x", "voice.ogg")
    assert result is not None
    assert result.transcript == ""


@pytest.mark.asyncio
async def test_transcribe_connection_error_returns_none(monkeypatch):
    """session.post() бросает сетевую ошибку → transcribe() должен вернуть None,
    а не пробросить исключение (контракт: transcribe никогда не raise-ит)."""
    from app.worker import asr
    monkeypatch.setattr(asr.settings, "ASR_ENABLED", True)

    async def fake_get_session():
        return _FakeSessionPostRaises(aiohttp.ClientConnectionError("connection refused"))

    monkeypatch.setattr(asr, "get_session", fake_get_session)
    assert await transcribe(b"x", "voice.ogg") is None


@pytest.mark.asyncio
async def test_transcribe_json_decode_error_returns_none(monkeypatch):
    """resp.json() бросает на 200-ответе (битый body) → transcribe() возвращает None."""
    from app.worker import asr
    monkeypatch.setattr(asr.settings, "ASR_ENABLED", True)
    resp = _FakeResp(200, json_exc=json.JSONDecodeError("Expecting value", "", 0))

    async def fake_get_session():
        return _FakeSession(resp)

    monkeypatch.setattr(asr, "get_session", fake_get_session)
    assert await transcribe(b"x", "voice.ogg") is None
