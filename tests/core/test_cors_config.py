"""Проверка конфигурации CORS в app.main — не должно быть wildcard с credentials."""

from starlette.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.main import app


def _cors_kwargs() -> dict:
    for middleware in app.user_middleware:
        if middleware.cls is CORSMiddleware:
            return middleware.kwargs
    raise AssertionError("CORSMiddleware не подключён к приложению")


def test_cors_does_not_allow_wildcard_origin():
    """allow_origins=['*'] вместе с allow_credentials=True — Starlette отражает любой Origin."""
    kwargs = _cors_kwargs()
    assert "*" not in kwargs["allow_origins"]


def test_cors_allows_webapp_url():
    """Mini App должен продолжать работать с домена WEBAPP_URL."""
    kwargs = _cors_kwargs()
    assert settings.WEBAPP_URL in kwargs["allow_origins"]


def test_cors_credentials_still_enabled():
    """allow_credentials остаётся включённым — нужен для сессии OAuth-логина."""
    kwargs = _cors_kwargs()
    assert kwargs["allow_credentials"] is True
