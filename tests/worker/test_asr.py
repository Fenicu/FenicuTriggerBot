"""Tests for app/worker/asr.py — transcribe() ASR client."""

import aiohttp
import pytest

from app.worker.asr import AsrResult, transcribe


class _FakeResp:
    def __init__(self, status, payload):
        self.status = status
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def json(self):
        return self._payload

    async def text(self):
        return str(self._payload)


class _FakeSession:
    def __init__(self, resp):
        self._resp = resp

    def post(self, *a, **k):
        return self._resp


@pytest.mark.asyncio
async def test_transcribe_success(monkeypatch):
    from app.worker import asr
    monkeypatch.setattr(asr.settings, "ASR_ENABLED", True)
    monkeypatch.setattr(asr.settings.ASR_TOKEN, "get_secret_value", lambda: "tok", raising=False)
    resp = _FakeResp(200, {"transcript": "привет мир", "language": "ru", "duration": 1.5})

    async def fake_get_session():
        return _FakeSession(resp)

    monkeypatch.setattr(asr, "get_session", fake_get_session)
    result = await transcribe(b"oggdata", "voice.ogg")
    assert isinstance(result, AsrResult)
    assert result.transcript == "привет мир"
    assert result.language == "ru"
    assert result.duration == 1.5


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
async def test_transcribe_disabled_returns_none(monkeypatch):
    from app.worker import asr
    monkeypatch.setattr(asr.settings, "ASR_ENABLED", False)
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
