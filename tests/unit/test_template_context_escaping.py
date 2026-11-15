import pytest
from aiogram.types import Chat, User
from markupsafe import Markup, escape

from app.services.template_service import get_render_context, render_rich_template, render_template


@pytest.mark.parametrize("rich", [False, True])
async def test_context_fields_are_escaped_once_and_mention_stays_html(rich):
    user = User(id=42, is_bot=False, first_name="<b>A & B</b>", last_name="<i>C</i>", username="x<y")
    chat = Chat(id=-100, type="supergroup", title="<b>Chat & Co</b>")
    variables = {"html": "<b>Admin HTML</b>"}
    ctx = get_render_context(user, chat, variables, timezone="UTC")
    assert isinstance(ctx["user"]["mention"], Markup)
    assert ctx["vars"] is variables
    render = render_rich_template if rich else render_template
    for field in ("full_name", "first_name", "last_name", "username"):
        expected = str(escape(getattr(user, field)))
        assert await render("{{ user." + field + " }}", ctx) == expected
    assert await render("{{ chat.title }}", ctx) == str(escape(chat.title))
    assert await render("{{ user.mention }}", ctx) == str(user.mention_html())
    if not rich:
        assert await render("{{ vars.html }}", ctx) == "<b>Admin HTML</b>"


def test_optional_context_fields_remain_none():
    ctx = get_render_context(User(id=1, is_bot=False, first_name="A"), Chat(id=1, type="private"), timezone="UTC")
    assert ctx["user"]["last_name"] is None
    assert ctx["user"]["username"] is None
    assert ctx["chat"]["title"] is None
