from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.exceptions import TelegramRetryAfter
from aiogram.methods import SendMessage
from faststream.exceptions import NackMessage

from app.bot.handlers import moderation
from app.schemas.moderation import ModerationAlert
from tests.factories import create_chat, create_trigger


def _retry_after():
    return TelegramRetryAfter(method=SendMessage(chat_id=1, text="test"), message="Flood limit", retry_after=7)


@pytest.mark.parametrize("fallback", [False, True])
async def test_alert_waits_and_retries_same_payload(db_session, fallback):
    chat = await create_chat(db_session)
    trigger = await create_trigger(db_session, chat.id)
    await db_session.commit()
    bot = MagicMock()
    bot.send_rich_message = AsyncMock(
        side_effect=([RuntimeError("media rejected")] if fallback else []) + [_retry_after(), None]
    )
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=db_session)
    session.__aexit__ = AsyncMock(return_value=False)
    with (
        patch.object(moderation, "async_session", return_value=session),
        patch.object(moderation, "bot", bot),
        patch.object(moderation, "build_chat_deeplink", AsyncMock(return_value=None)),
        patch("asyncio.sleep", new_callable=AsyncMock) as sleep,
    ):
        await moderation.handle_moderation_alert(
            ModerationAlert(trigger_id=trigger.id, chat_id=chat.id, category="Scam")
        )
    sleep.assert_awaited_once_with(7)
    calls = bot.send_rich_message.call_args_list
    assert len(calls) == (3 if fallback else 2)
    assert calls[-1] == calls[-2]


@pytest.mark.parametrize("fallback", [False, True])
async def test_repeated_rate_limit_requeues_alert(db_session, fallback):
    chat = await create_chat(db_session)
    trigger = await create_trigger(db_session, chat.id)
    await db_session.commit()
    bot = MagicMock()
    bot.send_rich_message = AsyncMock(
        side_effect=([RuntimeError("media rejected")] if fallback else []) + [_retry_after(), _retry_after()]
    )
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=db_session)
    session.__aexit__ = AsyncMock(return_value=False)
    with (
        patch.object(moderation, "async_session", return_value=session),
        patch.object(moderation, "bot", bot),
        patch.object(moderation, "build_chat_deeplink", AsyncMock(return_value=None)),
        patch("asyncio.sleep", new_callable=AsyncMock) as sleep,
        pytest.raises(NackMessage) as error,
    ):
        await moderation.handle_moderation_alert(
            ModerationAlert(trigger_id=trigger.id, chat_id=chat.id, category="Scam")
        )
    sleep.assert_awaited_once_with(7)
    assert error.value.extra_options == {"requeue": True}
    assert bot.send_rich_message.await_count == (3 if fallback else 2)
