"""/vars: ключи и значения экранируются перед сборкой HTML-сообщения."""

from unittest.mock import AsyncMock, MagicMock

from tests.factories import create_chat


async def test_vars_escapes_html_in_values(db_session, monkeypatch):
    from app.bot.handlers.variables import list_vars_command
    from app.services.chat_variable_service import set_var

    chat = await create_chat(db_session)
    await set_var(db_session, chat.id, "formula", "a < b && c > d")
    await set_var(db_session, chat.id, "markup", "<b>bold</b>")

    mock_bot = MagicMock()
    mock_bot.send_message = AsyncMock(return_value=MagicMock())
    monkeypatch.setattr("app.bot.handlers.variables.bot", mock_bot)

    msg = MagicMock()
    msg.chat = MagicMock(id=chat.id, type="supergroup")
    msg.sender_chat = None
    msg.from_user = MagicMock(id=456)
    msg.ephemeral_message_id = None
    msg.chat.get_member = AsyncMock(return_value=MagicMock(status="administrator"))
    i18n = MagicMock()
    i18n.var.list.header.return_value = "<b>Variables:</b>"

    await list_vars_command(msg, db_session, i18n)

    text = mock_bot.send_message.call_args.kwargs["text"]
    assert "<code>formula</code>: a &lt; b &amp;&amp; c &gt; d" in text
    assert "<code>markup</code>: &lt;b&gt;bold&lt;/b&gt;" in text
    # Заголовок из локали остаётся разметкой
    assert text.startswith("<b>Variables:</b>")


async def test_delvar_escapes_missing_key_in_reply(db_session):
    """Ключ в /delvar приходит от пользователя как есть -- в HTML-ответе он экранируется."""
    from app.bot.handlers.variables import del_var_command

    chat = await create_chat(db_session)
    msg = MagicMock()
    msg.chat = MagicMock(id=chat.id, type="supergroup")
    msg.sender_chat = None
    msg.from_user = MagicMock(id=456)
    msg.answer = AsyncMock()
    msg.chat.get_member = AsyncMock(return_value=MagicMock(status="administrator"))
    i18n = MagicMock()

    await del_var_command(msg, MagicMock(args="<b>x"), db_session, i18n)

    i18n.var.missing.assert_called_once_with(name="&lt;b&gt;x")
