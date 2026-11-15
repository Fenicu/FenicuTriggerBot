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


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("user.full_name | html | html", "Tom &amp; &lt;Jerry&gt;"),
        ("chat.title | upper", "TOM &amp; &lt;JERRY&gt;"),
        ("user.full_name[:6]", "Tom &amp; "),
        ("user.full_name | truncate(7, true)", "Tom ..."),
        ("user.full_name | replace('&', '+')", "Tom + &lt;Jerry&gt;"),
        ("user.full_name ~ ' & ' ~ chat.title", "Tom &amp; &lt;Jerry&gt; &amp; Tom &amp; &lt;Jerry&gt;"),
        ("user.full_name + ' & ' + chat.title", "Tom &amp; &lt;Jerry&gt; &amp; Tom &amp; &lt;Jerry&gt;"),
        ("user.full_name | bold", "<b>Tom &amp; &lt;Jerry&gt;</b>"),
        ("user.full_name | italic", "<i>Tom &amp; &lt;Jerry&gt;</i>"),
        ("user.full_name | code", "<code>Tom &amp; &lt;Jerry&gt;</code>"),
        ("user.username | mention", '<a href="https://t.me/x&lt;y&amp;">x&lt;y&amp;</a>'),
    ],
)
async def test_plain_filters_escape_after_string_operations(expression, expected):
    ctx = get_render_context(
        User(id=42, is_bot=False, first_name="Tom & <Jerry>", username="x<y&"),
        Chat(id=-100, type="supergroup", title="Tom & <Jerry>"),
        timezone="UTC",
    )
    assert await render_template("{{ " + expression + " }}", ctx) == expected


@pytest.mark.parametrize(
    "expression",
    [
        "vars.html",
        "vars.nested.html",
        "vars.choices | random",
        "vars.nested.choices | random",
        "vars.lines.split('\\n') | random",
    ],
)
async def test_admin_html_is_preserved_recursively(expression):
    raw = "<b>Admin & HTML</b>"
    variables = {"html": raw, "nested": {"html": raw, "choices": [raw]}, "choices": [raw], "lines": raw}
    assert await render_template("<p>{{ " + expression + " }}</p>", {"vars": variables}) == "<p>" + raw + "</p>"
    assert type(variables["html"]) is str
    assert type(variables["nested"]["html"]) is str
    assert type(variables["choices"][0]) is str


async def test_plain_safe_filter_cannot_bypass_escaping():
    from jinja2 import TemplateAssertionError

    with pytest.raises(TemplateAssertionError):
        await render_template("{{ name | safe }}", {"name": "<b>unsafe</b>"})


def test_context_keeps_raw_fields_for_string_filters():
    ctx = get_render_context(
        User(id=42, is_bot=False, first_name="&<first>", last_name="&<last>", username="&<user>"),
        Chat(id=-100, type="supergroup", title="&<title>"),
        timezone="UTC",
    )
    for field in ("first_name", "last_name", "full_name", "username"):
        assert type(ctx["user"][field]) is str
        assert "&<" in ctx["user"][field]
    assert ctx["chat"]["title"] == "&<title>"
