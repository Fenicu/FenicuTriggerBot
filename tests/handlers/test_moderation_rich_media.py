"""Тесты Task 11 — медиа внутри rich-карточек алертов модерации (все 5 embeddable-типов + legacy)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    InputMediaAnimation,
    InputMediaAudio,
    InputMediaPhoto,
    InputMediaVideo,
    InputMediaVoiceNote,
    InputRichMessage,
    RichMessage,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.trigger import ModerationStatus
from app.services.rich_html import RichHtmlError, validate_rich_html
from app.services.trigger_service import get_file_info_from_content
from tests.factories import create_chat, create_trigger, create_user
from tests.handlers.conftest import _make_callback

# Import the handler module at module level BEFORE autouse mocks take effect,
# so that the real broker.subscriber decorator is applied (not a MagicMock).
from app.bot.handlers.moderation import (
    ban_chat as _ban_chat,
    build_alert_media,
    delete_trigger as _delete_trigger,
    handle_moderation_alert as _handle_moderation_alert,
    mark_safe as _mark_safe,
    update_moderation_message as _update_moderation_message,
)

# ── Fixtures/helpers ─────────────────────────────────────────────────────────

_EMBEDDABLE_CASES = [
    pytest.param("photo", InputMediaPhoto, "img", "tg://photo?id=", id="photo"),
    pytest.param("video", InputMediaVideo, "video", "tg://video?id=", id="video"),
    pytest.param("animation", InputMediaAnimation, "video", "tg://video?id=", id="animation"),
    pytest.param("audio", InputMediaAudio, "audio", "tg://audio?id=", id="audio"),
    pytest.param("voice", InputMediaVoiceNote, "audio", "tg://audio?id=", id="voice"),
]

# media_type -> (bot method name, kwarg name)
_LEGACY_SEND = {
    "document": ("send_document", "document"),
    "sticker": ("send_sticker", "sticker"),
    "video_note": ("send_video_note", "video_note"),
}


def _content_for(media_type: str, file_id: str) -> dict:
    """Собрать минимальный content триггера для конкретного типа медиа."""
    if media_type == "photo":
        return {"photo": [{"file_id": file_id, "file_unique_id": "u", "width": 100, "height": 100}]}
    if media_type == "video":
        return {"video": {"file_id": file_id, "file_unique_id": "u", "width": 100, "height": 100, "duration": 5}}
    if media_type == "animation":
        return {"animation": {"file_id": file_id, "file_unique_id": "u", "width": 100, "height": 100, "duration": 5}}
    if media_type == "audio":
        return {"audio": {"file_id": file_id, "file_unique_id": "u", "duration": 5}}
    if media_type == "voice":
        return {"voice": {"file_id": file_id, "file_unique_id": "u", "duration": 5}}
    if media_type == "document":
        return {"document": {"file_id": file_id, "file_unique_id": "u"}}
    if media_type == "sticker":
        return {"sticker": {"file_id": file_id, "file_unique_id": "u", "type": "regular", "width": 512, "height": 512}}
    if media_type == "video_note":
        return {"video_note": {"file_id": file_id, "file_unique_id": "u", "length": 240, "duration": 5}}
    raise ValueError(media_type)


def _make_bot_mock() -> MagicMock:
    """Создать MagicMock с AsyncMock-методами для Bot."""
    m = MagicMock()
    m.send_message = AsyncMock()
    m.send_rich_message = AsyncMock()
    m.send_photo = AsyncMock()
    m.send_video = AsyncMock()
    m.send_sticker = AsyncMock()
    m.send_animation = AsyncMock()
    m.send_document = AsyncMock()
    m.send_voice = AsyncMock()
    m.send_audio = AsyncMock()
    m.send_video_note = AsyncMock()
    m.leave_chat = AsyncMock()
    return m


def _rich_message(text: str = "alert body") -> RichMessage:
    return RichMessage.model_validate({"blocks": [{"type": "paragraph", "text": text}]})


@pytest.fixture(autouse=True)
async def moderator_user(db_session: AsyncSession):
    """Создать модератора, совпадающего по id с дефолтным mock-юзером callback'а (user_id=42)."""
    return await create_user(db_session, id=42, first_name="Test", last_name="Mod")


@pytest.fixture
async def chat(db_session: AsyncSession):
    return await create_chat(db_session)


@pytest.fixture
async def user(db_session: AsyncSession):
    return await create_user(db_session)


async def _run_alert(db_session: AsyncSession, trigger, chat, mock_bot: MagicMock) -> None:
    """Прогнать handle_moderation_alert через тестовую сессию/бот."""
    from app.schemas.moderation import ModerationAlert

    alert = ModerationAlert(
        trigger_id=trigger.id,
        chat_id=chat.id,
        category="Scam",
        confidence=0.9,
        reasoning="test",
    )

    with (
        patch("app.bot.handlers.moderation.async_session") as mock_session_maker,
        patch("app.bot.handlers.moderation.bot", mock_bot),
    ):
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=db_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session_maker.return_value = mock_ctx

        await _handle_moderation_alert(alert)


# ── build_alert_media ─────────────────────────────────────────────────────


class TestBuildAlertMedia:
    def test_no_content_returns_empty(self) -> None:
        media, media_html = build_alert_media(None, None)
        assert media == []
        assert media_html == ""

    def test_text_only_content_returns_empty(self) -> None:
        file_id, media_type = get_file_info_from_content({"text": "hello"})
        media, media_html = build_alert_media(file_id, media_type)
        assert media == []
        assert media_html == ""

    @pytest.mark.parametrize("media_type,input_media_cls,tag,scheme", _EMBEDDABLE_CASES)
    def test_embeddable_type_produces_media_and_html(
        self, media_type: str, input_media_cls: type, tag: str, scheme: str
    ) -> None:
        content = _content_for(media_type, "FILEID123")
        file_id, resolved_type = get_file_info_from_content(content)
        media, media_html = build_alert_media(file_id, resolved_type)

        assert len(media) == 1
        assert isinstance(media[0].media, input_media_cls)
        # id — синтетическая константа "m0", не сам file_id (см. test_media_id_is_always_m0_*)
        assert media[0].id == "m0"
        assert media[0].media.media == "FILEID123"
        # img — void tag (no closing tag); video/audio — closed
        if tag == "img":
            assert media_html == f'<{tag} src="{scheme}m0">'
            assert "</img>" not in media_html
        else:
            assert media_html == f'<{tag} src="{scheme}m0"></{tag}>'
        validate_rich_html(media_html)

    @pytest.mark.parametrize("media_type", ["document", "sticker", "video_note"])
    def test_legacy_type_produces_no_media(self, media_type: str) -> None:
        content = _content_for(media_type, "FILEID456")
        file_id, resolved_type = get_file_info_from_content(content)
        media, media_html = build_alert_media(file_id, resolved_type)
        assert media == []
        assert media_html == ""

    @pytest.mark.parametrize("media_type,input_media_cls,tag,scheme", _EMBEDDABLE_CASES)
    def test_media_id_is_always_m0_regardless_of_file_id(
        self, media_type: str, input_media_cls: type, tag: str, scheme: str
    ) -> None:
        """id в InputRichMessageMedia/tg://-src — синтетическая константа "m0": реальные Telegram
        file_id часто длиннее 64 символов и вне алфавита [A-Za-z0-9_-] (см. _TG_SRC_RE) — как
        id/src их использовать нельзя."""
        long_file_id = "A" * 80 + "_-" + "b" * 20  # 102 символа, вне лимита {1,64} anchored-regex
        media, media_html = build_alert_media(long_file_id, media_type)

        assert media[0].id == "m0"
        assert media[0].media.media == long_file_id  # сам file_id по-прежнему уходит в InputMedia*
        assert long_file_id not in media_html
        expected_src = f"{scheme}m0"
        if tag == "img":
            assert media_html == f'<{tag} src="{expected_src}">'
        else:
            assert media_html == f'<{tag} src="{expected_src}"></{tag}>'
        validate_rich_html(media_html)


# ── handle_moderation_alert: embeddable types ──────────────────────────────


class TestHandleModerationAlertEmbeddable:
    @pytest.mark.parametrize("media_type,input_media_cls,tag,scheme", _EMBEDDABLE_CASES)
    async def test_embeds_media_in_rich_message(
        self,
        db_session: AsyncSession,
        chat,
        user,
        media_type: str,
        input_media_cls: type,
        tag: str,
        scheme: str,
    ) -> None:
        """Эмбеддируемое медиа уходит внутри rich-сообщения — отдельный send_<type> НЕ вызывается."""
        trigger = await create_trigger(
            db_session,
            chat_id=chat.id,
            user_id=user.id,
            content=_content_for(media_type, "FILEID789"),
            moderation_status=ModerationStatus.FLAGGED,
        )
        mock_bot = _make_bot_mock()

        await _run_alert(db_session, trigger, chat, mock_bot)

        legacy_method, _ = _LEGACY_SEND.get(media_type, (None, None))
        # send_<type> отдельным сообщением НЕ должен вызываться для эмбеддируемых типов
        for attr in ("send_photo", "send_video", "send_animation", "send_audio", "send_voice"):
            getattr(mock_bot, attr).assert_not_awaited()

        mock_bot.send_rich_message.assert_awaited_once()
        call_kwargs = mock_bot.send_rich_message.call_args.kwargs
        rich_message = call_kwargs["rich_message"]
        assert isinstance(rich_message, InputRichMessage)
        assert rich_message.media is not None
        assert len(rich_message.media) == 1
        assert rich_message.media[0].id == "m0"
        assert isinstance(rich_message.media[0].media, input_media_cls)
        assert rich_message.media[0].media.media == "FILEID789"
        assert f"{scheme}m0" in rich_message.html
        assert "FILEID789" not in rich_message.html
        validate_rich_html(rich_message.html)


# ── handle_moderation_alert: legacy types ──────────────────────────────────


class TestHandleModerationAlertLegacy:
    @pytest.mark.parametrize("media_type", ["document", "sticker", "video_note"])
    async def test_sends_media_separately_no_embed(
        self, db_session: AsyncSession, chat, user, media_type: str
    ) -> None:
        """Legacy-типы (document/sticker/video_note) уходят отдельным сообщением, без tg:// в rich-html."""
        trigger = await create_trigger(
            db_session,
            chat_id=chat.id,
            user_id=user.id,
            content=_content_for(media_type, "LEGACYFILE1"),
            moderation_status=ModerationStatus.FLAGGED,
        )
        mock_bot = _make_bot_mock()

        await _run_alert(db_session, trigger, chat, mock_bot)

        method_name, kwarg_name = _LEGACY_SEND[media_type]
        getattr(mock_bot, method_name).assert_awaited_once()
        sent_kwargs = getattr(mock_bot, method_name).call_args.kwargs
        assert sent_kwargs.get(kwarg_name) == "LEGACYFILE1"

        mock_bot.send_rich_message.assert_awaited_once()
        call_kwargs = mock_bot.send_rich_message.call_args.kwargs
        rich_message = call_kwargs["rich_message"]
        assert rich_message.media is None
        assert "tg://" not in rich_message.html


# ── Fallback: rich-send with media fails ───────────────────────────────────


class TestHandleModerationAlertFallback:
    async def test_fallback_sends_media_separately_and_rich_without_media(
        self, db_session: AsyncSession, chat, user
    ) -> None:
        """Ошибка первой (rich+media) отправки -> старый двухшаговый путь: отдельный
        send_photo + rich БЕЗ media и БЕЗ tg://-фрагмента в html."""
        trigger = await create_trigger(
            db_session,
            chat_id=chat.id,
            user_id=user.id,
            content=_content_for("photo", "FALLBACKFILE1"),
            moderation_status=ModerationStatus.FLAGGED,
        )
        mock_bot = _make_bot_mock()
        mock_bot.send_rich_message = AsyncMock(side_effect=[Exception("rich send boom"), None])

        await _run_alert(db_session, trigger, chat, mock_bot)

        mock_bot.send_photo.assert_awaited_once()
        assert mock_bot.send_photo.call_args.kwargs.get("photo") == "FALLBACKFILE1"

        assert mock_bot.send_rich_message.await_count == 2
        fallback_kwargs = mock_bot.send_rich_message.call_args_list[1].kwargs
        fallback_rich_message = fallback_kwargs["rich_message"]
        assert fallback_rich_message.media is None
        assert "tg://" not in fallback_rich_message.html
        validate_rich_html(fallback_rich_message.html)

    async def test_fallback_not_triggered_when_rich_send_succeeds(
        self, db_session: AsyncSession, chat, user
    ) -> None:
        """Happy path: успешная rich-отправка не должна вызывать fallback-логику повторно."""
        trigger = await create_trigger(
            db_session,
            chat_id=chat.id,
            user_id=user.id,
            content=_content_for("video", "OKFILE1"),
            moderation_status=ModerationStatus.FLAGGED,
        )
        mock_bot = _make_bot_mock()

        await _run_alert(db_session, trigger, chat, mock_bot)

        mock_bot.send_video.assert_not_awaited()
        assert mock_bot.send_rich_message.await_count == 1


# ── update_moderation_message: media preserved across moderator actions ────


class TestStatusUpdatePreservesMedia:
    @pytest.mark.parametrize("media_type,input_media_cls,tag,scheme", _EMBEDDABLE_CASES)
    async def test_mark_safe_preserves_media(
        self, db_session: AsyncSession, chat, user, media_type: str, input_media_cls: type, tag: str, scheme: str
    ) -> None:
        trigger = await create_trigger(
            db_session,
            chat_id=chat.id,
            user_id=user.id,
            content=_content_for(media_type, "SAFEFILE1"),
            moderation_status=ModerationStatus.FLAGGED,
            moderation_reason="Flagged by AI",
        )
        callback = _make_callback(f"mod_safe:{trigger.id}")
        callback.message.rich_message = _rich_message()

        await _mark_safe(callback, db_session)

        call_kwargs = callback.message.edit_text.call_args.kwargs
        sent = call_kwargs["rich_message"]
        assert isinstance(sent, InputRichMessage)
        assert sent.media is not None and len(sent.media) == 1
        assert sent.media[0].id == "m0"
        assert isinstance(sent.media[0].media, input_media_cls)
        assert sent.media[0].media.media == "SAFEFILE1"
        assert f"{scheme}m0" in sent.html
        assert "SAFEFILE1" not in sent.html
        validate_rich_html(sent.html)

    @pytest.mark.parametrize("media_type,input_media_cls,tag,scheme", _EMBEDDABLE_CASES)
    async def test_delete_trigger_preserves_media(
        self, db_session: AsyncSession, chat, user, media_type: str, input_media_cls: type, tag: str, scheme: str
    ) -> None:
        trigger = await create_trigger(
            db_session,
            chat_id=chat.id,
            user_id=user.id,
            content=_content_for(media_type, "DELFILE1"),
            moderation_status=ModerationStatus.FLAGGED,
            moderation_reason="Flagged by AI",
        )
        callback = _make_callback(f"mod_del:{trigger.id}")
        callback.message.rich_message = _rich_message()
        mock_bot = _make_bot_mock()

        with patch("app.bot.handlers.moderation.bot", mock_bot):
            await _delete_trigger(callback, db_session)

        call_kwargs = callback.message.edit_text.call_args.kwargs
        sent = call_kwargs["rich_message"]
        assert isinstance(sent, InputRichMessage)
        assert sent.media is not None and len(sent.media) == 1
        assert sent.media[0].id == "m0"
        assert isinstance(sent.media[0].media, input_media_cls)
        assert sent.media[0].media.media == "DELFILE1"
        assert f"{scheme}m0" in sent.html
        assert "DELFILE1" not in sent.html
        validate_rich_html(sent.html)

    @pytest.mark.parametrize("media_type,input_media_cls,tag,scheme", _EMBEDDABLE_CASES)
    async def test_ban_chat_preserves_media(
        self, db_session: AsyncSession, chat, user, media_type: str, input_media_cls: type, tag: str, scheme: str
    ) -> None:
        trigger = await create_trigger(
            db_session,
            chat_id=chat.id,
            user_id=user.id,
            content=_content_for(media_type, "BANFILE1"),
            moderation_status=ModerationStatus.FLAGGED,
            moderation_reason="Flagged by AI",
        )
        callback = _make_callback(f"mod_ban:{chat.id}:{trigger.id}")
        callback.message.rich_message = _rich_message()
        mock_bot = _make_bot_mock()

        with patch("app.bot.handlers.moderation.bot", mock_bot):
            await _ban_chat(callback, db_session)

        call_kwargs = callback.message.edit_text.call_args.kwargs
        sent = call_kwargs["rich_message"]
        assert isinstance(sent, InputRichMessage)
        assert sent.media is not None and len(sent.media) == 1
        assert sent.media[0].id == "m0"
        assert isinstance(sent.media[0].media, input_media_cls)
        assert sent.media[0].media.media == "BANFILE1"
        assert f"{scheme}m0" in sent.html
        assert "BANFILE1" not in sent.html
        validate_rich_html(sent.html)

    async def test_legacy_media_not_restored_on_status_update(
        self, db_session: AsyncSession, chat, user
    ) -> None:
        """Legacy-типы (например sticker) не встраиваются в rich-карточку даже после апдейта статуса."""
        trigger = await create_trigger(
            db_session,
            chat_id=chat.id,
            user_id=user.id,
            content=_content_for("sticker", "STICKERFILE1"),
            moderation_status=ModerationStatus.FLAGGED,
            moderation_reason="Flagged by AI",
        )
        callback = _make_callback(f"mod_safe:{trigger.id}")
        callback.message.rich_message = _rich_message()

        await _mark_safe(callback, db_session)

        call_kwargs = callback.message.edit_text.call_args.kwargs
        sent = call_kwargs["rich_message"]
        assert sent.media is None
        assert "tg://" not in sent.html


# ── update_moderation_message: fallback when rich-edit with media fails ────


class TestUpdateModerationMessageFallback:
    async def test_edit_failure_retries_without_media(self) -> None:
        """Первый edit_text (с media) кидает TelegramBadRequest -> повторный edit_text
        без media и без tg://-фрагмента в html; фолбэк должен пройти успешно."""
        message = MagicMock()
        message.rich_message = _rich_message()
        message.edit_text = AsyncMock(
            side_effect=[TelegramBadRequest(method=MagicMock(), message="RICH_MEDIA_INVALID"), None]
        )

        content = _content_for("photo", "BADMEDIAFILE1")

        await _update_moderation_message(message, "✅ Marked SAFE by <b>admin</b>", content)

        assert message.edit_text.await_count == 2
        first_kwargs = message.edit_text.call_args_list[0].kwargs
        first_rich = first_kwargs["rich_message"]
        assert first_rich.media is not None
        assert "tg://photo?id=m0" in first_rich.html

        second_kwargs = message.edit_text.call_args_list[1].kwargs
        second_rich = second_kwargs["rich_message"]
        assert second_rich.media is None
        assert "tg://" not in second_rich.html
        assert "alert body" in second_rich.html
        assert "Marked SAFE" in second_rich.html
        validate_rich_html(second_rich.html)

    async def test_both_edits_fail_logs_and_does_not_raise(self) -> None:
        """Если и фолбэк-edit тоже упал — функция логирует и не пробрасывает исключение."""
        message = MagicMock()
        message.rich_message = _rich_message()
        message.edit_text = AsyncMock(
            side_effect=[
                TelegramBadRequest(method=MagicMock(), message="RICH_MEDIA_INVALID"),
                TelegramBadRequest(method=MagicMock(), message="MESSAGE_NOT_MODIFIED"),
            ]
        )

        content = _content_for("video", "BADMEDIAFILE2")

        await _update_moderation_message(message, "💀 Deleted by <b>admin</b>", content)

        assert message.edit_text.await_count == 2


# ── tg:// src regex edge cases (via validate_rich_html) ────────────────────


class TestTgSrcValidation:
    @pytest.mark.parametrize(
        "tag,scheme",
        [("img", "tg://photo?id="), ("video", "tg://video?id="), ("audio", "tg://audio?id=")],
    )
    def test_valid_tg_reference_accepted(self, tag: str, scheme: str) -> None:
        body = f'<{tag} src="{scheme}abcDEF123_-">' if tag == "img" else f'<{tag} src="{scheme}abcDEF123_-"></{tag}>'
        validate_rich_html(body)

    @pytest.mark.parametrize(
        "tag,scheme",
        [("img", "tg://photo?id="), ("video", "tg://video?id="), ("audio", "tg://audio?id=")],
    )
    def test_empty_id_rejected(self, tag: str, scheme: str) -> None:
        body = f'<{tag} src="{scheme}">'
        with pytest.raises(RichHtmlError):
            validate_rich_html(body)

    @pytest.mark.parametrize(
        "tag,scheme",
        [("img", "tg://photo?id="), ("video", "tg://video?id="), ("audio", "tg://audio?id=")],
    )
    def test_id_over_64_chars_rejected(self, tag: str, scheme: str) -> None:
        body = f'<{tag} src="{scheme}{"a" * 65}">'
        with pytest.raises(RichHtmlError):
            validate_rich_html(body)

    @pytest.mark.parametrize(
        "tag,scheme",
        [("img", "tg://photo?id="), ("video", "tg://video?id="), ("audio", "tg://audio?id=")],
    )
    def test_id_exactly_64_chars_accepted(self, tag: str, scheme: str) -> None:
        body_tag = f'<{tag} src="{scheme}{"a" * 64}">'
        if tag != "img":
            body_tag = f'<{tag} src="{scheme}{"a" * 64}"></{tag}>'
        validate_rich_html(body_tag)

    @pytest.mark.parametrize(
        "tag,scheme",
        [("img", "tg://photo?id="), ("video", "tg://video?id="), ("audio", "tg://audio?id=")],
    )
    def test_extra_query_param_rejected(self, tag: str, scheme: str) -> None:
        body = f'<{tag} src="{scheme}abc123&extra=1">'
        with pytest.raises(RichHtmlError):
            validate_rich_html(body)

    def test_wrong_type_for_tag_rejected(self) -> None:
        """img обязан ссылаться на tg://photo, а не на tg://video/tg://audio (типизированный regex)."""
        with pytest.raises(RichHtmlError):
            validate_rich_html('<img src="tg://video?id=abc123">')
        with pytest.raises(RichHtmlError):
            validate_rich_html('<video src="tg://photo?id=abc123"></video>')
        with pytest.raises(RichHtmlError):
            validate_rich_html('<audio src="tg://photo?id=abc123"></audio>')

    def test_file_id_style_src_still_rejected(self) -> None:
        """Голый Telegram file_id (не http/https, не tg://<type>) по-прежнему отклоняется."""
        with pytest.raises(RichHtmlError):
            validate_rich_html('<img src="AgACfileid">')
