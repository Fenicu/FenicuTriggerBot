"""Tests for app/services/template_service.py — template validation and rendering."""

import pytest


# ---------------------------------------------------------------------------
# Individual filters
# ---------------------------------------------------------------------------


class TestMentionFilter:
    def _fn(self, value: str) -> str:
        from app.services.template_service import mention_filter

        return mention_filter(value)

    def test_numeric_id_creates_tg_user_link(self):
        result = self._fn("123456")
        assert result == '<a href="tg://user?id=123456">123456</a>'

    def test_username_creates_tme_link(self):
        result = self._fn("some_user")
        assert result == '<a href="https://t.me/some_user">some_user</a>'

    def test_mixed_string_treated_as_username(self):
        result = self._fn("user123abc")
        assert "t.me/user123abc" in result

    def test_empty_string_treated_as_username(self):
        # empty string: "".isdigit() == False
        result = self._fn("")
        assert "t.me/" in result


class TestHtmlFilter:
    def _fn(self, value: str) -> str:
        from app.services.template_service import html_filter

        return html_filter(value)

    def test_escapes_angle_brackets(self):
        assert self._fn("<script>alert(1)</script>") == "&lt;script&gt;alert(1)&lt;/script&gt;"

    def test_escapes_ampersand(self):
        assert self._fn("a & b") == "a &amp; b"

    def test_plain_text_unchanged(self):
        assert self._fn("hello world") == "hello world"


class TestBoldFilter:
    def test_wraps_in_b_tags(self):
        from app.services.template_service import bold_filter

        assert bold_filter("hello") == "<b>hello</b>"


class TestItalicFilter:
    def test_wraps_in_i_tags(self):
        from app.services.template_service import italic_filter

        assert italic_filter("hello") == "<i>hello</i>"


class TestCodeFilter:
    def test_wraps_in_code_tags(self):
        from app.services.template_service import code_filter

        assert code_filter("hello") == "<code>hello</code>"


# ---------------------------------------------------------------------------
# validate_template
# ---------------------------------------------------------------------------


class TestValidateTemplate:
    def _fn(self, template_str: str) -> None:
        from app.services.template_service import validate_template

        return validate_template(template_str)

    def test_valid_simple_template(self):
        # Should not raise
        self._fn("Hello {{ name }}!")

    def test_valid_template_with_conditional(self):
        self._fn("{% if show %}visible{% endif %}")

    def test_template_with_for_loop_raises(self):
        with pytest.raises(ValueError, match="Циклы запрещены"):
            self._fn("{% for i in items %}{{ i }}{% endfor %}")

    def test_nested_loop_inside_if_raises(self):
        template = "{% if True %}{% for x in xs %}{{ x }}{% endfor %}{% endif %}"
        with pytest.raises(ValueError, match="Циклы запрещены"):
            self._fn(template)

    def test_variable_only_template(self):
        self._fn("{{ user.full_name }}")

    def test_empty_template(self):
        self._fn("")

    def test_plain_text_template(self):
        self._fn("Just plain text, no jinja.")

    def test_filter_in_template(self):
        self._fn("{{ name | bold }}")

    def test_invalid_jinja_syntax_raises(self):
        with pytest.raises(Exception):
            self._fn("{% if %}broken{% endif %}")


# ---------------------------------------------------------------------------
# render_template
# ---------------------------------------------------------------------------


class TestRenderTemplate:
    def _fn(self, template_str: str, context: dict) -> str:
        from app.services.template_service import render_template

        return render_template(template_str, context)

    def test_basic_render(self):
        result = self._fn("Hello {{ name }}!", {"name": "World"})
        assert result == "Hello World!"

    def test_context_variables(self):
        result = self._fn("{{ a }} + {{ b }} = {{ c }}", {"a": 1, "b": 2, "c": 3})
        assert result == "1 + 2 = 3"

    def test_mention_filter(self):
        result = self._fn("{{ uid | mention }}", {"uid": "12345"})
        assert "tg://user?id=12345" in result

    def test_html_filter(self):
        result = self._fn("{{ text | html }}", {"text": "<b>bold</b>"})
        assert "&lt;b&gt;" in result

    def test_bold_filter(self):
        result = self._fn("{{ text | bold }}", {"text": "hello"})
        assert result == "<b>hello</b>"

    def test_italic_filter(self):
        result = self._fn("{{ text | italic }}", {"text": "hello"})
        assert result == "<i>hello</i>"

    def test_code_filter(self):
        result = self._fn("{{ text | code }}", {"text": "hello"})
        assert result == "<code>hello</code>"

    def test_missing_variable_renders_empty(self):
        # Jinja2 renders undefined variables as empty string by default
        result = self._fn("Hello {{ missing }}!", {})
        assert result == "Hello !"

    def test_loop_in_render_raises(self):
        with pytest.raises(ValueError, match="Циклы запрещены"):
            self._fn("{% for i in items %}{{ i }}{% endfor %}", {"items": [1, 2, 3]})

    def test_nested_variable_access(self):
        ctx = {"user": {"name": "Alice", "id": 42}}
        result = self._fn("{{ user.name }} ({{ user.id }})", ctx)
        assert result == "Alice (42)"

    def test_conditional_rendering(self):
        result = self._fn("{% if show %}visible{% else %}hidden{% endif %}", {"show": True})
        assert result == "visible"

    def test_conditional_rendering_false(self):
        result = self._fn("{% if show %}visible{% else %}hidden{% endif %}", {"show": False})
        assert result == "hidden"
