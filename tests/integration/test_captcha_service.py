"""Tests for app/services/captcha_service.py — captcha generation and verification."""

import json
from collections import Counter, defaultdict

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from app.services.captcha_service import (
    ALL_EMOJIS,
    BUTTON_COUNT,
    MAX_DUPLICATE_PAIRS,
    MIN_DUPLICATE_PAIRS,
    STYLES,
    CaptchaData,
    CaptchaResult,
    CaptchaService,
    CaptchaSessionData,
)


def _duplicated_emojis(buttons) -> set[str]:
    return {emoji for emoji, count in Counter(b.emoji for b in buttons).items() if count > 1}


@pytest.fixture
def mock_valkey():
    """Patch the module-level valkey used by captcha_service."""
    with patch("app.services.captcha_service.valkey") as m:
        m.get = AsyncMock(return_value=None)
        m.set = AsyncMock()
        m.delete = AsyncMock()
        m.ttl = AsyncMock(return_value=250)
        m.sismember = AsyncMock(return_value=False)
        yield m


# ── Redis key generation ─────────────────────────────────────────────────────


class TestRedisKey:
    def test_key_format(self):
        key = CaptchaService._get_redis_key(chat_id=-100, user_id=42)
        assert key == "captcha:session:-100:42"

    def test_key_uniqueness(self):
        k1 = CaptchaService._get_redis_key(1, 2)
        k2 = CaptchaService._get_redis_key(2, 1)
        assert k1 != k2


# ── Button generation ────────────────────────────────────────────────────────


class TestGenerateCaptchaButtons:
    def test_returns_16_buttons(self):
        target_emoji, target_style, correct_code, buttons = CaptchaService._generate_captcha_buttons()
        # 1 correct + 1 decoy + 14 others = 16
        assert len(buttons) == 16

    def test_target_emoji_in_all_emojis(self):
        target_emoji, _, _, _ = CaptchaService._generate_captcha_buttons()
        assert target_emoji in ALL_EMOJIS

    def test_target_style_is_valid(self):
        _, target_style, _, _ = CaptchaService._generate_captcha_buttons()
        assert target_style in STYLES

    def test_correct_button_has_correct_code(self):
        target_emoji, target_style, correct_code, buttons = CaptchaService._generate_captcha_buttons()
        correct_buttons = [b for b in buttons if b.code == correct_code]
        assert len(correct_buttons) == 1
        assert correct_buttons[0].emoji == target_emoji
        assert correct_buttons[0].style == target_style

    def test_decoy_button_exists(self):
        """Target emoji appears twice — once correct, once decoy (different style)."""
        target_emoji, target_style, correct_code, buttons = CaptchaService._generate_captcha_buttons()
        target_buttons = [b for b in buttons if b.emoji == target_emoji]
        assert len(target_buttons) == 2
        styles = {b.style for b in target_buttons}
        assert len(styles) == 2  # Two different styles

    def test_correct_button_not_first_or_last(self):
        """The correct button should not be at index 0 or 15."""
        for _ in range(20):  # Run multiple times due to randomness
            _, _, correct_code, buttons = CaptchaService._generate_captcha_buttons()
            correct_idx = next(i for i, b in enumerate(buttons) if b.code == correct_code)
            assert correct_idx != 0
            assert correct_idx != 15

    def test_target_is_never_the_only_duplicated_emoji(self):
        """Раньше повтор был один и указывал на ответ: найти пару = решить капчу за 50%."""
        for _ in range(200):
            target_emoji, _, _, buttons = CaptchaService._generate_captcha_buttons()
            duplicated = _duplicated_emojis(buttons)
            assert duplicated != {target_emoji}
            assert len(duplicated) >= MIN_DUPLICATE_PAIRS

    def test_emoji_frequency_does_not_reveal_target(self):
        """По частоте цель не вычислить: у всех дублей она одна и та же -- ровно два."""
        for _ in range(200):
            target_emoji, _, _, buttons = CaptchaService._generate_captcha_buttons()
            counts = Counter(b.emoji for b in buttons)
            duplicated = _duplicated_emojis(buttons)
            assert counts[target_emoji] == 2
            assert {counts[emoji] for emoji in duplicated} == {2}

    def test_duplicate_pair_count_is_unpredictable(self):
        """Само число пар не должно быть константой, по которой строят стратегию."""
        seen = {len(_duplicated_emojis(CaptchaService._generate_captcha_buttons()[3])) for _ in range(200)}
        assert len(seen) >= 2
        assert seen <= set(range(MIN_DUPLICATE_PAIRS, MAX_DUPLICATE_PAIRS + 1))

    def test_every_duplicated_pair_has_distinct_styles(self):
        """Одинаковые эмодзи в одном стиле -- две неотличимые кнопки, человек угадывает вслепую."""
        for _ in range(50):
            _, _, _, buttons = CaptchaService._generate_captcha_buttons()
            styles_by_emoji = defaultdict(list)
            for button in buttons:
                styles_by_emoji[button.emoji].append(button.style)
            for styles in styles_by_emoji.values():
                assert len(styles) == len(set(styles))

    def test_button_count_stays_16(self):
        """Сетка 4x4 не меняется ни при каком числе пар."""
        for _ in range(50):
            _, _, _, buttons = CaptchaService._generate_captcha_buttons()
            assert len(buttons) == BUTTON_COUNT

    def test_exactly_one_button_carries_correct_code(self):
        """Цветовая пара цели и любые другие дубли -- неверные кнопки."""
        for _ in range(50):
            _, _, correct_code, buttons = CaptchaService._generate_captcha_buttons()
            assert sum(1 for b in buttons if b.code == correct_code) == 1
            assert len({b.code for b in buttons}) == BUTTON_COUNT

    def test_correct_position_is_uniform_over_allowed_slots(self):
        """Защита от краёв не должна сама выдавать ответ, сгущая его на позициях 1 и 14."""
        runs = 4000
        positions = Counter()
        for _ in range(runs):
            _, _, correct_code, buttons = CaptchaService._generate_captcha_buttons()
            positions[next(i for i, b in enumerate(buttons) if b.code == correct_code)] += 1

        allowed = set(range(1, BUTTON_COUNT - 1))
        assert set(positions) <= allowed
        expected = runs / len(allowed)
        for index in allowed:
            assert 0.6 * expected < positions[index] < 1.6 * expected

    def test_emoji_pool_covers_widest_layout(self):
        """ALL_EMOJIS хватает на раскладку с наименьшим числом пар, и в нём нет повторов."""
        assert len(set(ALL_EMOJIS)) == len(ALL_EMOJIS)
        assert len(ALL_EMOJIS) >= BUTTON_COUNT - MIN_DUPLICATE_PAIRS


# ── Session creation ─────────────────────────────────────────────────────────


class TestCreateSession:
    async def test_creates_session_and_stores_in_redis(self, mock_valkey):
        result = await CaptchaService.create_session(chat_id=-100, user_id=42)

        assert isinstance(result, CaptchaData)
        assert result.target_emoji in ALL_EMOJIS
        assert result.target_style in STYLES
        assert len(result.buttons) == 16
        mock_valkey.set.assert_awaited_once()

    async def test_session_ttl_is_respected(self, mock_valkey):
        await CaptchaService.create_session(chat_id=-100, user_id=42, session_ttl=600)

        call_kwargs = mock_valkey.set.call_args
        assert call_kwargs.kwargs.get("ex") == 600 or call_kwargs[1].get("ex") == 600


# ── Verification ─────────────────────────────────────────────────────────────


class TestVerifyAttempt:
    async def test_success_on_correct_code(self, mock_valkey):
        session_data = CaptchaSessionData(
            correct_code="abc-123",
            target_emoji="🐶",
            attempts_left=3,
        )
        mock_valkey.get = AsyncMock(return_value=session_data.model_dump_json())

        result = await CaptchaService.verify_attempt(-100, 42, "abc-123")

        assert result == CaptchaResult.SUCCESS
        mock_valkey.delete.assert_awaited_once()

    async def test_fail_when_no_session(self, mock_valkey):
        mock_valkey.get = AsyncMock(return_value=None)

        result = await CaptchaService.verify_attempt(-100, 42, "any-code")

        assert result == CaptchaResult.FAIL

    async def test_retry_on_wrong_code_with_attempts_left(self, mock_valkey):
        session_data = CaptchaSessionData(
            correct_code="abc-123",
            target_emoji="🐶",
            attempts_left=3,
        )
        mock_valkey.get = AsyncMock(return_value=session_data.model_dump_json())

        result = await CaptchaService.verify_attempt(-100, 42, "wrong-code")

        assert result == CaptchaResult.RETRY
        # Should save updated session with decremented attempts
        mock_valkey.set.assert_awaited_once()
        saved_json = mock_valkey.set.call_args[0][1]
        saved = CaptchaSessionData.model_validate_json(saved_json)
        assert saved.attempts_left == 2

    async def test_fail_on_last_attempt(self, mock_valkey):
        session_data = CaptchaSessionData(
            correct_code="abc-123",
            target_emoji="🐶",
            attempts_left=1,
        )
        mock_valkey.get = AsyncMock(return_value=session_data.model_dump_json())

        result = await CaptchaService.verify_attempt(-100, 42, "wrong-code")

        assert result == CaptchaResult.FAIL
        mock_valkey.delete.assert_awaited_once()


# ── Regeneration ─────────────────────────────────────────────────────────────


class TestRegenerateSession:
    async def test_returns_none_when_no_session(self, mock_valkey):
        mock_valkey.get = AsyncMock(return_value=None)

        result = await CaptchaService.regenerate_session(-100, 42)

        assert result is None

    async def test_regenerates_with_preserved_attempts(self, mock_valkey):
        old_session = CaptchaSessionData(
            correct_code="old-code",
            target_emoji="🐶",
            attempts_left=1,
        )
        mock_valkey.get = AsyncMock(return_value=old_session.model_dump_json())
        mock_valkey.ttl = AsyncMock(return_value=150)

        result = await CaptchaService.regenerate_session(-100, 42)

        assert isinstance(result, CaptchaData)
        # New session should be saved with old attempts_left
        saved_json = mock_valkey.set.call_args[0][1]
        saved = CaptchaSessionData.model_validate_json(saved_json)
        assert saved.attempts_left == 1

    async def test_regenerate_uses_remaining_ttl(self, mock_valkey):
        old_session = CaptchaSessionData(
            correct_code="old-code",
            target_emoji="🐶",
            attempts_left=2,
        )
        mock_valkey.get = AsyncMock(return_value=old_session.model_dump_json())
        mock_valkey.ttl = AsyncMock(return_value=100)

        await CaptchaService.regenerate_session(-100, 42)

        call_kwargs = mock_valkey.set.call_args
        assert call_kwargs.kwargs.get("ex") == 100 or call_kwargs[1].get("ex") == 100


# ── Get session ──────────────────────────────────────────────────────────────


class TestGetSession:
    async def test_returns_none_when_missing(self, mock_valkey):
        mock_valkey.get = AsyncMock(return_value=None)

        result = await CaptchaService.get_session(-100, 42)

        assert result is None

    async def test_returns_session_data(self, mock_valkey):
        session_data = CaptchaSessionData(
            correct_code="abc-123",
            target_emoji="🐶",
            attempts_left=3,
        )
        mock_valkey.get = AsyncMock(return_value=session_data.model_dump_json())

        result = await CaptchaService.get_session(-100, 42)

        assert isinstance(result, CaptchaSessionData)
        assert result.correct_code == "abc-123"
        assert result.attempts_left == 3


# ── индикатор оставшихся попыток (неактивная кнопка) ─────────────────────────


def _fake_i18n():
    """Отдаёт подпись счётчика так же, как fluentogram: с подставленным числом."""
    node = MagicMock()
    node.captcha.attempts.left = lambda count: f"Осталось попыток: {count}"
    return node


def _codes(markup) -> list[str]:
    return [b.text for row in markup.inline_keyboard for b in row]


def test_keyboard_shows_attempts_indicator():
    """Последней строкой идёт неактивная кнопка со счётчиком попыток."""
    from app.services.captcha_service import CaptchaButton, build_captcha_keyboard

    buttons = [CaptchaButton(emoji="🍎", code=f"c{i}", style="") for i in range(16)]
    markup = build_captcha_keyboard(42, buttons, attempts_left=3, i18n=_fake_i18n())

    last_row = markup.inline_keyboard[-1]
    assert len(last_row) == 1
    indicator = last_row[0]
    assert indicator.disabled is not None, "кнопка-счётчик должна быть неактивной"
    assert indicator.callback_data is None, "у счётчика не должно быть callback_data"
    assert "3" in indicator.text


def test_keyboard_without_attempts_has_no_indicator():
    """Без счётчика клавиатура прежняя: только 16 кнопок капчи."""
    from app.services.captcha_service import CaptchaButton, build_captcha_keyboard

    buttons = [CaptchaButton(emoji="🍎", code=f"c{i}", style="") for i in range(16)]
    markup = build_captcha_keyboard(42, buttons)

    assert sum(len(row) for row in markup.inline_keyboard) == 16
    assert all(b.disabled is None for row in markup.inline_keyboard for b in row)


def test_attempts_indicator_does_not_break_emoji_grid():
    """Сетка эмодзи остаётся 4x4, счётчик добавляется отдельной строкой."""
    from app.services.captcha_service import CaptchaButton, build_captcha_keyboard

    buttons = [CaptchaButton(emoji="🍎", code=f"c{i}", style="") for i in range(16)]
    markup = build_captcha_keyboard(42, buttons, attempts_left=5, i18n=_fake_i18n())

    emoji_rows = markup.inline_keyboard[:-1]
    assert len(emoji_rows) == 4
    assert all(len(row) == 4 for row in emoji_rows)
    assert all(b.callback_data is not None for row in emoji_rows for b in row)
