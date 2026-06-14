"""Тесты модуля app/services/rich_html.py."""

import pytest
from app.services.rich_html import (
    RichHtmlError,
    degrade_to_html,
    validate_rich_html,
)

# ---------------------------------------------------------------------------
# Sub-task A: теги, сущности, вложенность
# ---------------------------------------------------------------------------


class TestValidateTagsAllowed:
    def test_known_block_tags_accepted(self) -> None:
        validate_rich_html("<p>Привет</p>")

    def test_known_inline_tags_accepted(self) -> None:
        validate_rich_html("<b>bold</b> <i>italic</i> <u>under</u>")

    def test_all_inline_tags_accepted(self) -> None:
        validate_rich_html(
            "<b><strong><i><em><u><ins><s><strike><del>"
            "<code>x</code></del></strike></s></ins></u></em></i></strong></b>"
        )

    def test_void_tags_accepted(self) -> None:
        # br, hr, img — void; tg-emoji is NOT void
        validate_rich_html("<p>x<br/>y</p><hr/>")

    def test_img_void_accepted(self) -> None:
        validate_rich_html('<img src="https://example.com/a.jpg"/>')

    def test_tg_emoji_not_void(self) -> None:
        # tg-emoji has content + closing tag
        validate_rich_html('<tg-emoji emoji-id="1234">😀</tg-emoji>')

    def test_script_rejected(self) -> None:
        with pytest.raises(RichHtmlError, match="unsupported tag: script"):
            validate_rich_html("<script>alert(1)</script>")

    def test_div_rejected(self) -> None:
        with pytest.raises(RichHtmlError, match="unsupported tag: div"):
            validate_rich_html("<div>text</div>")

    def test_span_rejected(self) -> None:
        with pytest.raises(RichHtmlError, match="unsupported tag: span"):
            validate_rich_html("<span>text</span>")


class TestValidateEntities:
    def test_allowed_named_entities(self) -> None:
        validate_rich_html("&amp; &lt; &gt; &quot; &apos; &nbsp; &hellip; &mdash; &ndash;")

    def test_allowed_named_entities_quotes(self) -> None:
        validate_rich_html("&lsquo; &rsquo; &ldquo; &rdquo;")

    def test_numeric_decimal_always_allowed(self) -> None:
        validate_rich_html("&#1234; &#65;")

    def test_numeric_hex_always_allowed(self) -> None:
        validate_rich_html("&#x42; &#X1F600;")

    def test_copy_entity_rejected(self) -> None:
        with pytest.raises(RichHtmlError, match="unsupported entity: copy"):
            validate_rich_html("&copy;")

    def test_trade_entity_rejected(self) -> None:
        with pytest.raises(RichHtmlError, match="unsupported entity: trade"):
            validate_rich_html("&trade;")


class TestValidateNesting:
    def test_correct_nesting_accepted(self) -> None:
        validate_rich_html("<b><i>text</i></b>")

    def test_mismatched_close_rejected(self) -> None:
        # <b><i>x</b></i> — b закрывается раньше i
        with pytest.raises(RichHtmlError, match="mismatched"):
            validate_rich_html("<b><i>x</b></i>")

    def test_unclosed_tag_rejected(self) -> None:
        with pytest.raises(RichHtmlError, match="unclosed"):
            validate_rich_html("<b>text")

    def test_extra_close_rejected(self) -> None:
        with pytest.raises(RichHtmlError, match="mismatched"):
            validate_rich_html("<b>text</b></b>")

    def test_void_tag_no_close_needed(self) -> None:
        # void теги не требуют закрывающего тега
        validate_rich_html("<p>a<br>b</p>")

    def test_complex_nesting_accepted(self) -> None:
        validate_rich_html("<blockquote><p><b>text</b></p></blockquote>")


# ---------------------------------------------------------------------------
# Sub-task B: лимиты и src-валидация медиа
# ---------------------------------------------------------------------------


class TestValidateLimits:
    def test_text_too_long_rejected(self) -> None:
        long_text = "a" * 32769
        with pytest.raises(RichHtmlError, match=r"text.*limit|limit.*text|32768"):
            validate_rich_html(long_text)

    def test_text_exactly_at_limit_accepted(self) -> None:
        # 32768 символов — граница
        validate_rich_html("a" * 32768)

    def test_nesting_too_deep_rejected(self) -> None:
        # 17 уровней вложенности — сверх лимита 16
        html = "<p>" * 17 + "x" + "</p>" * 17
        with pytest.raises(RichHtmlError, match=r"nesting|depth|level"):
            validate_rich_html(html)

    def test_nesting_exactly_at_limit_accepted(self) -> None:
        # 16 уровней — на границе
        html = "<p>" * 16 + "x" + "</p>" * 16
        validate_rich_html(html)

    def test_too_many_columns_rejected(self) -> None:
        # 21 колонка в строке таблицы
        cells = "<td>x</td>" * 21
        html = f"<table><tr>{cells}</tr></table>"
        with pytest.raises(RichHtmlError, match=r"column|col"):
            validate_rich_html(html)

    def test_exactly_20_columns_accepted(self) -> None:
        cells = "<td>x</td>" * 20
        html = f"<table><tr>{cells}</tr></table>"
        validate_rich_html(html)

    def test_col_count_resets_between_rows(self) -> None:
        # Две строки по 20 колонок: счётчик сбрасывается на </tr>,
        # поэтому суммарно 40 td не должны трипать лимит в 20.
        cells = "<td>x</td>" * 20
        html = f"<table><tr>{cells}</tr><tr>{cells}</tr></table>"
        validate_rich_html(html)

    def test_too_many_media_rejected(self) -> None:
        # 51 img элемент
        imgs = "".join(f'<img src="https://x.com/{i}.jpg"/>' for i in range(51))
        with pytest.raises(RichHtmlError, match="media"):
            validate_rich_html(imgs)

    def test_exactly_50_media_accepted(self) -> None:
        imgs = "".join(f'<img src="https://x.com/{i}.jpg"/>' for i in range(50))
        validate_rich_html(imgs)

    def test_too_many_blocks_rejected(self) -> None:
        # 501 блоков (p элементов)
        html = "".join(f"<p>x{i}</p>" for i in range(501))
        with pytest.raises(RichHtmlError, match="block"):
            validate_rich_html(html)

    def test_exactly_500_blocks_accepted(self) -> None:
        html = "".join(f"<p>x{i}</p>" for i in range(500))
        validate_rich_html(html)


class TestValidateMediaSrc:
    def test_img_http_accepted(self) -> None:
        validate_rich_html('<img src="http://example.com/a.jpg"/>')

    def test_img_https_accepted(self) -> None:
        validate_rich_html('<img src="https://example.com/a.jpg"/>')

    def test_img_file_id_rejected(self) -> None:
        # Telegram file_id — не http/https
        with pytest.raises(RichHtmlError, match=r"src|url|http"):
            validate_rich_html('<img src="AgACfileid"/>')

    def test_video_http_accepted(self) -> None:
        validate_rich_html('<video src="https://example.com/v.mp4"/>')

    def test_audio_http_accepted(self) -> None:
        validate_rich_html('<audio src="https://example.com/a.ogg"/>')

    def test_video_file_id_rejected(self) -> None:
        with pytest.raises(RichHtmlError, match=r"src|url|http"):
            validate_rich_html('<video src="BQACfileid"/>')

    def test_img_no_src_rejected(self) -> None:
        with pytest.raises(RichHtmlError, match=r"src|url|http"):
            validate_rich_html("<img/>")

    def test_bare_img_counted_as_media(self) -> None:
        # Bare <img> (без слеша) тоже должны считаться — проверяем handle_starttag path
        imgs = "".join(f'<img src="https://x.com/{i}.jpg">' for i in range(51))
        with pytest.raises(RichHtmlError, match="media"):
            validate_rich_html(imgs)


# ---------------------------------------------------------------------------
# Sub-task C: degrade_to_html
# ---------------------------------------------------------------------------


class TestDegradeToHtml:
    def test_heading_becomes_bold_with_newline(self) -> None:
        result = degrade_to_html("<h2>Title</h2>")
        assert result == "<b>Title</b>\n"

    def test_h1_becomes_bold(self) -> None:
        result = degrade_to_html("<h1>Header</h1>")
        assert result == "<b>Header</b>\n"

    def test_h6_becomes_bold(self) -> None:
        result = degrade_to_html("<h6>Small</h6>")
        assert result == "<b>Small</b>\n"

    def test_supported_inline_preserved_b(self) -> None:
        result = degrade_to_html("<b>bold</b>")
        assert "<b>bold</b>" in result

    def test_supported_inline_preserved_i(self) -> None:
        result = degrade_to_html("<i>italic</i>")
        assert "<i>italic</i>" in result

    def test_strong_maps_to_b(self) -> None:
        result = degrade_to_html("<strong>text</strong>")
        assert "<b>text</b>" in result

    def test_em_maps_to_i(self) -> None:
        result = degrade_to_html("<em>text</em>")
        assert "<i>text</i>" in result

    def test_ins_maps_to_u(self) -> None:
        result = degrade_to_html("<ins>text</ins>")
        assert "<u>text</u>" in result

    def test_strike_maps_to_s(self) -> None:
        result = degrade_to_html("<strike>text</strike>")
        assert "<s>text</s>" in result

    def test_del_maps_to_s(self) -> None:
        result = degrade_to_html("<del>text</del>")
        assert "<s>text</s>" in result

    def test_tg_emoji_preserved(self) -> None:
        result = degrade_to_html('<tg-emoji emoji-id="1234">😀</tg-emoji>')
        assert '<tg-emoji emoji-id="1234">😀</tg-emoji>' in result

    def test_unordered_list(self) -> None:
        result = degrade_to_html("<ul><li>a</li><li>b</li></ul>")
        assert "• a\n" in result
        assert "• b\n" in result

    def test_ordered_list(self) -> None:
        result = degrade_to_html("<ol><li>first</li><li>second</li></ol>")
        assert "1. first\n" in result
        assert "2. second\n" in result

    def test_ul_li_exact(self) -> None:
        result = degrade_to_html("<ul><li>a</li><li>b</li></ul>")
        assert result == "• a\n• b\n"

    def test_figure_drops_img_keeps_caption(self) -> None:
        html = '<figure><img src="https://x/a.jpg"/><figcaption>Cap</figcaption></figure>'
        result = degrade_to_html(html)
        assert "Cap" in result
        assert "img" not in result
        assert "https://x/a.jpg" not in result

    def test_mark_stripped_text_kept(self) -> None:
        result = degrade_to_html("<mark>hi</mark>")
        assert "hi" in result
        assert "<mark>" not in result

    def test_sup_stripped_text_kept(self) -> None:
        result = degrade_to_html("<sup>2</sup>")
        assert "2" in result
        assert "<sup>" not in result

    def test_mark_and_sup_combined(self) -> None:
        result = degrade_to_html("<mark>hi</mark> <sup>2</sup>")
        assert result == "hi 2"

    def test_br_becomes_newline(self) -> None:
        result = degrade_to_html("a<br/>b")
        assert result == "a\nb"

    def test_br_open_tag_becomes_newline(self) -> None:
        result = degrade_to_html("a<br>b")
        assert result == "a\nb"

    def test_hr_becomes_separator(self) -> None:
        result = degrade_to_html("<hr/>")
        assert "———" in result

    def test_a_keeps_href(self) -> None:
        result = degrade_to_html('<a href="https://example.com">link</a>')
        assert '<a href="https://example.com">link</a>' in result

    def test_code_preserved(self) -> None:
        result = degrade_to_html("<code>x = 1</code>")
        assert "<code>x = 1</code>" in result

    def test_pre_preserved(self) -> None:
        result = degrade_to_html("<pre>code block</pre>")
        assert "<pre>code block</pre>" in result

    def test_tg_spoiler_preserved(self) -> None:
        result = degrade_to_html("<tg-spoiler>secret</tg-spoiler>")
        assert "<tg-spoiler>secret</tg-spoiler>" in result

    def test_blockquote_preserved(self) -> None:
        result = degrade_to_html("<blockquote>quote</blockquote>")
        assert "<blockquote>quote</blockquote>" in result

    def test_aside_becomes_blockquote(self) -> None:
        result = degrade_to_html("<aside>aside text</aside>")
        assert "<blockquote>aside text</blockquote>" in result

    def test_img_dropped_entirely(self) -> None:
        result = degrade_to_html('<img src="https://x.com/a.jpg"/>')
        assert "img" not in result
        assert "https://x.com/a.jpg" not in result

    def test_video_dropped_entirely(self) -> None:
        result = degrade_to_html('<video src="https://x.com/v.mp4"/>')
        assert "video" not in result

    def test_tg_math_wraps_in_code(self) -> None:
        result = degrade_to_html("<tg-math>x^2</tg-math>")
        assert "<code>x^2</code>" in result

    def test_tg_math_block_wraps_in_code(self) -> None:
        result = degrade_to_html("<tg-math-block>x^2</tg-math-block>")
        assert "<code>x^2</code>" in result

    def test_p_adds_double_newline(self) -> None:
        result = degrade_to_html("<p>text</p>")
        assert "text\n\n" in result

    def test_sub_stripped_text_kept(self) -> None:
        result = degrade_to_html("<sub>2</sub>")
        assert "2" in result
        assert "<sub>" not in result

    def test_video_with_body_dropped_entirely(self) -> None:
        # <video> с содержимым (non-self-closing) — suppress-путь;
        # тело тоже не должно попасть в вывод
        result = degrade_to_html("<video>body</video>")
        assert "video" not in result
        assert "body" not in result
        assert result == ""

    def test_entity_amp_preserved(self) -> None:
        result = degrade_to_html("&amp;")
        assert result == "&amp;"

    def test_charref_zws_preserved(self) -> None:
        result = degrade_to_html("&#8203;")
        assert result == "&#8203;"


# ---------------------------------------------------------------------------
# Регрессионные тесты: баг 1 — bare <img>/<hr> не должны подавлять вывод
# ---------------------------------------------------------------------------


class TestDegradeBareVoidMedia:
    def test_bare_img_does_not_eat_following_text(self) -> None:
        # <img> без слеша — void-элемент, suppress_depth не должен расти
        result = degrade_to_html('<img src="https://x/a.jpg">after text')
        assert "after text" in result
        assert "https://x/a.jpg" not in result
        assert "img" not in result

    def test_bare_img_url_not_in_output(self) -> None:
        result = degrade_to_html('<img src="https://x/a.jpg">hello')
        assert "https://x/a.jpg" not in result

    def test_bare_hr_produces_separator(self) -> None:
        # bare <hr> (без слеша) должен давать разделитель, не теряться
        result = degrade_to_html("before<hr>after")
        assert "———" in result

    def test_figure_bare_img_keeps_caption(self) -> None:
        # <figure><img ...><figcaption>Cap</figcaption></figure>
        html = '<figure><img src="https://x/a.jpg"><figcaption>Cap</figcaption></figure>'
        result = degrade_to_html(html)
        assert "Cap" in result
        assert "https://x/a.jpg" not in result


# ---------------------------------------------------------------------------
# Регрессионные тесты: баг 2 — вложенные <li> не должны терять внешний контент
# ---------------------------------------------------------------------------


class TestDegradeNestedLists:
    def test_nested_ul_in_ul_keeps_outer_item(self) -> None:
        html = "<ul><li>outer<ul><li>inner</li></ul></li></ul>"
        result = degrade_to_html(html)
        assert "outer" in result
        assert "inner" in result

    def test_nested_ol_in_ul_keeps_outer_item(self) -> None:
        html = "<ul><li>a<ol><li>nested</li></ol></li></ul>"
        result = degrade_to_html(html)
        assert "a" in result
        assert "nested" in result

    def test_nested_list_markers(self) -> None:
        html = "<ul><li>a<ol><li>nested</li></ol></li></ul>"
        result = degrade_to_html(html)
        # внешний элемент — bullet, внутренний — нумерованный
        assert "• " in result
        assert "1. " in result
