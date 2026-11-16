from unittest.mock import AsyncMock, patch

import pytest

from app.services import trigger_service
from app.worker.links import build_link_context, extract_links
from tests.factories import create_chat, create_trigger, create_user


@pytest.mark.parametrize("operation", ["create", "requeue", "bulk"])
async def test_tasks_preserve_hidden_and_button_urls(db_session, operation):
    chat = await create_chat(db_session)
    user = await create_user(db_session)
    content = {
        "text": "Open",
        "entities": [{"type": "text_link", "offset": 0, "length": 4, "url": "https://hidden.example/path"}],
        "caption_entities": [{"type": "text_link", "offset": 0, "length": 4, "url": "https://caption.example"}],
        "reply_markup": {"inline_keyboard": [[{"text": "Visit", "url": "https://button.example/path"}]]},
    }
    with patch.object(trigger_service.broker, "publish", new_callable=AsyncMock) as publish:
        if operation == "create":
            await trigger_service.create_trigger(
                db_session, chat_id=chat.id, key_phrase="test", content=content, created_by=user.id
            )
        else:
            trigger = await create_trigger(db_session, chat.id, content=content)
            await db_session.commit()
            if operation == "requeue":
                await trigger_service.requeue_trigger(db_session, trigger.id)
            else:
                await trigger_service.bulk_remoderate_safe(db_session)
    task = publish.call_args.args[0]
    assert task.link_urls == ["https://hidden.example/path", "https://caption.example", "https://button.example/path"]
    assert "Visit" in task.text_content


def test_extract_links_removes_unbalanced_punctuation():
    urls, _ = extract_links("[button](https://example.com/path). https://example.com/a_(b)")
    assert urls == ["https://example.com/path", "https://example.com/a_(b)"]


async def test_explicit_urls_and_private_invites_are_analyzed_without_fetching_invites():
    with (
        patch("app.worker.links.safe_fetch", new_callable=AsyncMock) as fetch,
        patch("app.worker.links.resolve_tg", new_callable=AsyncMock) as resolve,
    ):
        fetch.return_value = None
        context, _ = await build_link_context("", "", ["https://hidden.example", "https://t.me/+secretInvite"])
    fetch.assert_awaited_once_with("https://hidden.example")
    resolve.assert_not_awaited()
    assert "https://t.me/+secretInvite" in context
    assert "приглашение" in context.lower()
