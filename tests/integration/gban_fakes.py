"""Общие фейки aiohttp для тестов gban-сервиса (без реальной сети)."""

from __future__ import annotations

from collections.abc import Iterable


class FakeContent:
    """Потоковое тело ответа: chunks отдаются как есть, error_after рвёт поток."""

    def __init__(self, chunks: Iterable[bytes | str], error_after: Exception | None = None) -> None:
        self._chunks = [c.encode() if isinstance(c, str) else c for c in chunks]
        self._error_after = error_after

    async def iter_chunked(self, _size: int):
        for chunk in self._chunks:
            yield chunk
        if self._error_after is not None:
            raise self._error_after


class FakeResponse:
    def __init__(
        self,
        status: int = 200,
        body: bytes | str | None = None,
        chunks: Iterable[bytes | str] | None = None,
        headers: dict[str, str] | None = None,
        error_after: Exception | None = None,
    ) -> None:
        self.status = status
        self.headers = headers or {}
        if chunks is None:
            raw = body if body is not None else b"[]"
            chunks = [raw.encode() if isinstance(raw, str) else raw]
        self.content = FakeContent(chunks, error_after=error_after)

    async def __aenter__(self) -> FakeResponse:
        return self

    async def __aexit__(self, *_args) -> bool:
        return False


class FakeSession:
    """Минимальная замена aiohttp.ClientSession: запоминает заголовки запросов."""

    def __init__(self, responses: list[FakeResponse], requests: list[dict[str, str] | None] | None = None) -> None:
        self._responses = list(responses)
        self.requests = requests if requests is not None else []

    async def __aenter__(self) -> FakeSession:
        return self

    async def __aexit__(self, *_args) -> bool:
        return False

    def get(self, _url: str, headers: dict[str, str] | None = None) -> FakeResponse:
        self.requests.append(headers)
        return self._responses.pop(0)


def session_factory(*responses: FakeResponse, requests: list[dict[str, str] | None] | None = None):
    """Возвращает callable для patch(aiohttp.ClientSession): один вызов — одна сессия."""

    def _factory(*_args, **_kwargs) -> FakeSession:
        return FakeSession(list(responses), requests=requests)

    return _factory
