"""Tests for app/worker/llm.py — moderate() function and helpers."""

import asyncio
import json

import aiohttp
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.schemas.moderation import ModerationLLMResult
from app.worker.llm import (
    InferenceUnavailableError,
    VALID_CATEGORIES,
    _build_user_content,
    _extract_json_object,
    _parse_result,
    _validate_result,
    moderate,
)


# ── _build_user_content ──────────────────────────────────────────────────────


class TestBuildUserContent:
    def test_text_only(self):
        parts = _build_user_content(text="hello", caption="", image=None)
        assert len(parts) == 1
        assert parts[0]["type"] == "text"
        assert "hello" in parts[0]["text"]

    def test_text_and_caption(self):
        parts = _build_user_content(text="hello", caption="caption text", image=None)
        assert len(parts) == 1
        assert "Caption: caption text" in parts[0]["text"]

    def test_with_image(self):
        parts = _build_user_content(text="hello", caption="", image=b"\x89PNG")
        assert len(parts) == 2
        assert parts[0]["type"] == "image_url"
        assert "data:image/jpeg;base64," in parts[0]["image_url"]["url"]
        assert parts[1]["type"] == "text"

    def test_no_text_no_caption(self):
        parts = _build_user_content(text="", caption="", image=None)
        assert len(parts) == 1
        assert "Classify this trigger content." in parts[0]["text"]

    def test_image_only(self):
        parts = _build_user_content(text="", caption="", image=b"\xff\xd8\xff")
        assert len(parts) == 2
        assert parts[0]["type"] == "image_url"


# ── _extract_json_object ─────────────────────────────────────────────────────


class TestExtractJsonObject:
    def test_simple_json(self):
        text = '{"category": "Safe", "confidence": 0.9}'
        result = _extract_json_object(text)
        assert result is not None
        data = json.loads(result)
        assert data["category"] == "Safe"

    def test_json_with_prefix(self):
        text = 'Some reasoning here... {"category": "Drugs", "confidence": 0.8, "reasoning": "test"}'
        result = _extract_json_object(text)
        assert result is not None
        data = json.loads(result)
        assert data["category"] == "Drugs"

    def test_nested_braces_in_strings(self):
        text = '{"reasoning": "found {braces} inside", "category": "Safe", "confidence": 0.5}'
        result = _extract_json_object(text)
        assert result is not None
        data = json.loads(result)
        assert data["category"] == "Safe"

    def test_no_json(self):
        result = _extract_json_object("no json here at all")
        assert result is None

    def test_incomplete_json(self):
        result = _extract_json_object('{"category": "Safe"')
        assert result is None


# ── _validate_result ─────────────────────────────────────────────────────────


class TestValidateResult:
    def test_valid_result(self):
        data = {"category": "Safe", "confidence": 0.95, "reasoning": "Looks fine"}
        result = _validate_result(data)
        assert isinstance(result, ModerationLLMResult)
        assert result.category == "Safe"
        assert result.confidence == 0.95

    def test_invalid_category(self):
        data = {"category": "Unknown", "confidence": 0.5, "reasoning": "?"}
        result = _validate_result(data)
        assert result is None

    def test_confidence_clamped(self):
        data = {"category": "Drugs", "confidence": 1.5, "reasoning": "High"}
        result = _validate_result(data)
        assert result.confidence == 1.0

    def test_confidence_defaults_when_missing(self):
        data = {"category": "Scam", "reasoning": "suspicious"}
        result = _validate_result(data)
        assert result.confidence == 0.5

    def test_all_valid_categories(self):
        for cat in VALID_CATEGORIES:
            data = {"category": cat, "confidence": 0.7, "reasoning": "test"}
            result = _validate_result(data)
            assert result is not None
            assert result.category == cat


# ── _parse_result ────────────────────────────────────────────────────────────


class TestParseResult:
    def test_parses_clean_json(self):
        content = '{"category": "Safe", "confidence": 0.9, "reasoning": "ok"}'
        result = _parse_result(content)
        assert result is not None
        assert result.category == "Safe"

    def test_parses_json_embedded_in_text(self):
        content = 'Here is my analysis:\n{"category": "Porn", "confidence": 0.8, "reasoning": "explicit"}\nDone.'
        result = _parse_result(content)
        assert result is not None
        assert result.category == "Porn"

    def test_returns_none_for_garbage(self):
        result = _parse_result("I don't know what to classify this as.")
        assert result is None


# ── moderate() ───────────────────────────────────────────────────────────────


class TestModerate:
    @pytest.fixture
    def mock_response(self):
        resp = AsyncMock()
        resp.status = 200
        resp.json = AsyncMock(
            return_value={
                "choices": [
                    {
                        "message": {
                            "content": '{"category": "Safe", "confidence": 0.95, "reasoning": "Clean content"}',
                        }
                    }
                ]
            }
        )
        resp.text = AsyncMock(return_value="")
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)
        return resp

    @pytest.fixture
    def mock_session(self, mock_response):
        session = AsyncMock()
        session.post = MagicMock(return_value=mock_response)
        return session

    async def test_successful_moderation(self, mock_session):
        with patch("app.worker.llm.get_session", new_callable=AsyncMock, return_value=mock_session):
            result = await moderate(text="hello world", caption="", image=None)

        assert isinstance(result, ModerationLLMResult)
        assert result.category == "Safe"
        assert result.confidence == 0.95

    async def test_http_error_returns_none(self):
        resp = AsyncMock()
        resp.status = 500
        resp.text = AsyncMock(return_value="Internal Server Error")
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)

        session = AsyncMock()
        session.post = MagicMock(return_value=resp)

        with patch("app.worker.llm.get_session", new_callable=AsyncMock, return_value=session):
            result = await moderate(text="test", caption="", image=None)

        assert result is None

    async def test_connection_error_raises_unavailable(self):
        session = AsyncMock()
        session.post = MagicMock(side_effect=aiohttp.ClientConnectionError("refused"))

        with patch("app.worker.llm.get_session", new_callable=AsyncMock, return_value=session):
            with pytest.raises(InferenceUnavailableError):
                await moderate(text="test", caption="", image=None)

    async def test_timeout_raises_unavailable(self):
        session = AsyncMock()
        session.post = MagicMock(side_effect=aiohttp.ServerTimeoutError("timeout"))

        with patch("app.worker.llm.get_session", new_callable=AsyncMock, return_value=session):
            with pytest.raises(InferenceUnavailableError):
                await moderate(text="test", caption="", image=None)

    async def test_os_error_raises_unavailable(self):
        session = AsyncMock()
        session.post = MagicMock(side_effect=OSError("Network unreachable"))

        with patch("app.worker.llm.get_session", new_callable=AsyncMock, return_value=session):
            with pytest.raises(InferenceUnavailableError):
                await moderate(text="test", caption="", image=None)

    async def test_unexpected_error_returns_none(self):
        session = AsyncMock()
        session.post = MagicMock(side_effect=KeyError("unexpected"))

        with patch("app.worker.llm.get_session", new_callable=AsyncMock, return_value=session):
            result = await moderate(text="test", caption="", image=None)

        assert result is None

    async def test_gemma_thinking_mode_reasoning_content(self):
        """When content is empty but reasoning_content exists, parse that."""
        resp = AsyncMock()
        resp.status = 200
        resp.json = AsyncMock(
            return_value={
                "choices": [
                    {
                        "message": {
                            "content": "",
                            "reasoning_content": '{"category": "Drugs", "confidence": 0.9, "reasoning": "Drug sale detected"}',
                        }
                    }
                ]
            }
        )
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)

        session = AsyncMock()
        session.post = MagicMock(return_value=resp)

        with patch("app.worker.llm.get_session", new_callable=AsyncMock, return_value=session):
            result = await moderate(text="buy drugs", caption="", image=None)

        assert result is not None
        assert result.category == "Drugs"

    async def test_gemma_thinking_mode_with_normal_content(self):
        """When both content and reasoning_content exist, content takes priority."""
        resp = AsyncMock()
        resp.status = 200
        resp.json = AsyncMock(
            return_value={
                "choices": [
                    {
                        "message": {
                            "content": '{"category": "Safe", "confidence": 0.9, "reasoning": "ok"}',
                            "reasoning_content": '{"category": "Drugs", "confidence": 0.9, "reasoning": "wrong"}',
                        }
                    }
                ]
            }
        )
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)

        session = AsyncMock()
        session.post = MagicMock(return_value=resp)

        with patch("app.worker.llm.get_session", new_callable=AsyncMock, return_value=session):
            result = await moderate(text="hello", caption="", image=None)

        assert result is not None
        assert result.category == "Safe"  # Content wins over reasoning_content

    async def test_unparseable_response_returns_none(self):
        resp = AsyncMock()
        resp.status = 200
        resp.json = AsyncMock(
            return_value={
                "choices": [
                    {
                        "message": {
                            "content": "I cannot classify this content",
                        }
                    }
                ]
            }
        )
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)

        session = AsyncMock()
        session.post = MagicMock(return_value=resp)

        with patch("app.worker.llm.get_session", new_callable=AsyncMock, return_value=session):
            result = await moderate(text="test", caption="", image=None)

        assert result is None

    async def test_concurrent_calls_are_serialized(self):
        """Один in-flight запрос к inference: иначе llama.cpp батчит и рвёт sock-таймауты."""
        from contextlib import asynccontextmanager

        in_flight = 0
        max_in_flight = 0

        resp = AsyncMock()
        resp.status = 200
        resp.json = AsyncMock(
            return_value={
                "choices": [
                    {
                        "message": {
                            "content": '{"category": "Safe", "confidence": 0.9, "reasoning": "ok"}',
                        }
                    }
                ]
            }
        )

        @asynccontextmanager
        async def slow_post(*_args, **_kwargs):
            nonlocal in_flight, max_in_flight
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
            try:
                # Уступаем event loop, чтобы конкурент успел стартануть, если не сериализованы.
                await asyncio.sleep(0.01)
                yield resp
            finally:
                in_flight -= 1

        session = AsyncMock()
        session.post = MagicMock(side_effect=slow_post)

        with patch("app.worker.llm.get_session", new_callable=AsyncMock, return_value=session):
            results = await asyncio.gather(
                moderate(text="a", caption="", image=None),
                moderate(text="b", caption="", image=None),
                moderate(text="c", caption="", image=None),
            )

        assert max_in_flight == 1, f"Expected serial calls, got {max_in_flight} concurrent"
        assert session.post.call_count == 3
        assert all(r is not None and r.category == "Safe" for r in results)

    async def test_503_model_loading_raises_unavailable(self):
        """503 (model loading на cold-start) — retryable, не AI Error."""
        resp = AsyncMock()
        resp.status = 503
        resp.text = AsyncMock(return_value="loading model")
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)
        session = AsyncMock()
        session.post = MagicMock(return_value=resp)
        with patch("app.worker.llm.get_session", new_callable=AsyncMock, return_value=session):
            with pytest.raises(InferenceUnavailableError):
                await moderate(text="test", caption="", image=None)

    async def test_504_gateway_timeout_raises_unavailable(self):
        resp = AsyncMock()
        resp.status = 504
        resp.text = AsyncMock(return_value="gateway timeout")
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)
        session = AsyncMock()
        session.post = MagicMock(return_value=resp)
        with patch("app.worker.llm.get_session", new_callable=AsyncMock, return_value=session):
            with pytest.raises(InferenceUnavailableError):
                await moderate(text="t", caption="", image=None)

    async def test_429_too_many_requests_raises_unavailable(self):
        resp = AsyncMock()
        resp.status = 429
        resp.text = AsyncMock(return_value="busy")
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)
        session = AsyncMock()
        session.post = MagicMock(return_value=resp)
        with patch("app.worker.llm.get_session", new_callable=AsyncMock, return_value=session):
            with pytest.raises(InferenceUnavailableError):
                await moderate(text="t", caption="", image=None)

    async def test_sends_image_in_payload(self):
        resp = AsyncMock()
        resp.status = 200
        resp.json = AsyncMock(
            return_value={
                "choices": [
                    {
                        "message": {
                            "content": '{"category": "Safe", "confidence": 0.8, "reasoning": "clean image"}',
                        }
                    }
                ]
            }
        )
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)

        session = AsyncMock()
        session.post = MagicMock(return_value=resp)

        with patch("app.worker.llm.get_session", new_callable=AsyncMock, return_value=session):
            result = await moderate(text="", caption="nice photo", image=b"\x89PNG\x00\x01")

        assert result is not None
        # Verify image was included in the request
        call_kwargs = session.post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        user_content = payload["messages"][1]["content"]
        assert any(p["type"] == "image_url" for p in user_content)
