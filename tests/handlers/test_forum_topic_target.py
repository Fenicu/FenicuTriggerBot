"""Команда в форум-топике без явного reply не должна целиться в создателя топика."""

from unittest.mock import MagicMock

from app.bot.handlers.chat_moderation import get_target_user


def _make_message(*, is_topic_service: bool) -> MagicMock:
    msg = MagicMock()
    reply = MagicMock()
    reply.forum_topic_created = MagicMock() if is_topic_service else None
    reply.from_user = MagicMock(id=777, full_name="Topic Creator")
    msg.reply_to_message = reply
    return msg


async def test_topic_service_message_is_not_a_target() -> None:
    msg = _make_message(is_topic_service=True)

    user_id, user_name = await get_target_user(msg)

    assert user_id is None
    assert user_name is None


async def test_regular_reply_in_topic_is_a_target() -> None:
    msg = _make_message(is_topic_service=False)

    user_id, user_name = await get_target_user(msg)

    assert user_id == 777
    assert user_name == "Topic Creator"
