"""Регрессия пересчёта тегов: пропуск неизменившихся тегов и батчевые коммиты."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.tag_recalculation import _COMMIT_BATCH, recalculate_chat_tags


@pytest.fixture(autouse=True)
def _allow_tag_calls():
    """Кэш прав не должен влиять на юнит-тесты пересчёта."""
    with patch("app.services.tag_recalculation.tag_calls_blocked", new_callable=AsyncMock, return_value=False):
        yield


def _chat():
    chat = MagicMock()
    chat.tags_enabled = True
    chat.tags_preset = "neutral"
    chat.tags_custom = None
    chat.language_code = "ru"
    chat.tags_thresholds = None
    return chat


def _user_chat(**overrides):
    uc = MagicMock()
    uc.tag_is_manual = False
    uc.reputation_score = 0
    uc.reputation_level = 0
    uc.tag = None
    uc.user_id = 42
    uc.is_active = True
    for key, value in overrides.items():
        setattr(uc, key, value)
    return uc


def _session(chat, user_chats):
    result = MagicMock()
    result.scalars.return_value.all.return_value = user_chats

    session = AsyncMock()
    session.get = AsyncMock(return_value=chat)
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock()

    factory = AsyncMock()
    factory.__aenter__ = AsyncMock(return_value=session)
    factory.__aexit__ = AsyncMock(return_value=False)
    return factory, session


async def test_zero_level_with_empty_tag_settles():
    """Уровень 0 даёт пустое имя тега, а в БД лежит NULL — это одно и то же."""
    chat = _chat()
    uc = _user_chat(reputation_level=0, tag=None)
    factory, session = _session(chat, [uc])

    with (
        patch("app.services.tag_recalculation.async_session", return_value=factory),
        patch("app.services.tag_recalculation._set_tag_with_retry", new_callable=AsyncMock) as mock_set,
        patch("app.services.tag_recalculation.asyncio.sleep", new_callable=AsyncMock),
    ):
        await recalculate_chat_tags(chat_id=-100)

    mock_set.assert_not_awaited()
    session.commit.assert_awaited()


async def test_unchanged_tag_does_not_call_api():
    """Совпадающий тег при том же уровне не должен дёргать Telegram API."""
    chat = _chat()
    uc = _user_chat(reputation_score=100, reputation_level=1, tag="Участник")
    factory, session = _session(chat, [uc])

    with (
        patch("app.services.tag_recalculation.async_session", return_value=factory),
        patch("app.services.tag_recalculation._set_tag_with_retry", new_callable=AsyncMock) as mock_set,
        patch("app.services.tag_recalculation.asyncio.sleep", new_callable=AsyncMock),
    ):
        await recalculate_chat_tags(chat_id=-100)

    mock_set.assert_not_awaited()


async def test_commits_in_batches():
    """Транзакция не должна висеть на весь цикл вызовов Telegram API."""
    chat = _chat()
    user_chats = [
        _user_chat(user_id=i, reputation_score=100, reputation_level=1, tag="Участник")
        for i in range(_COMMIT_BATCH * 2 + 5)
    ]
    factory, session = _session(chat, user_chats)
    changed = [
        _user_chat(user_id=i, reputation_score=100, reputation_level=0, tag=None)
        for i in range(_COMMIT_BATCH * 2 + 5)
    ]
    session.execute = AsyncMock(return_value=MagicMock(**{"scalars.return_value.all.return_value": changed}))

    with (
        patch("app.services.tag_recalculation.async_session", return_value=factory),
        patch("app.services.tag_recalculation._set_tag_with_retry", new_callable=AsyncMock, return_value=True),
        patch("app.services.tag_recalculation.asyncio.sleep", new_callable=AsyncMock),
    ):
        await recalculate_chat_tags(chat_id=-100)

    # По коммиту на каждые _COMMIT_BATCH пользователей плюс финальный
    assert session.commit.await_count >= 3
