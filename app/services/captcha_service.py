import random
import secrets
import uuid
from enum import StrEnum

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from fluentogram import TranslatorRunner
from pydantic import BaseModel, Field
from yarl import URL

from app.core.config import settings
from app.core.valkey import valkey

ANIMALS = [
    "🐶",
    "🐱",
    "🐭",
    "🐹",
    "🐰",
    "🦊",
    "🐻",
    "🐼",
    "🐨",
    "🐯",
    "🦁",
    "🐮",
    "🐷",
    "🐸",
    "🐵",
    "🐔",
    "🐧",
    "🐦",
    "🐤",
    "🦆",
    "🦅",
    "🦉",
    "🦇",
    "🐺",
    "🐗",
    "🐴",
    "🦄",
    "🐝",
    "🐛",
    "🦋",
]

FOOD = [
    "🍏",
    "🍎",
    "🍐",
    "🍊",
    "🍋",
    "🍌",
    "🍉",
    "🍇",
    "🍓",
    "🍈",
    "🍒",
    "🍑",
    "🍍",
    "🥭",
    "🥥",
    "🥝",
    "🍅",
    "🍆",
    "🥑",
    "🥦",
    "🥬",
    "🥒",
    "🌶",
    "🌽",
    "🥕",
    "🧄",
    "🧅",
    "🥔",
    "🍠",
    "🥐",
]

TRANSPORT = [
    "🚗",
    "🚕",
    "🚙",
    "🚌",
    "🚎",
    "🏎️",
    "🚓",
    "🚑",
    "🚒",
    "🚐",
    "🚚",
    "🚛",
    "🚜",
    "🏍️",
    "🛵",
    "🚲",
    "🛴",
    "🛺",
    "🚔",
    "🚍",
    "🚘",
    "🚖",
    "🚡",
    "🚠",
    "🚟",
    "🚃",
    "🚋",
    "🚞",
    "🚝",
    "🚄",
]

SPORT = [
    "⚽",
    "🏀",
    "🏈",
    "⚾",
    "🥎",
    "🎾",
    "🏐",
    "🏉",
    "🥏",
    "🎱",
    "🪀",
    "🏓",
    "🏸",
    "🏒",
    "🏑",
    "🥍",
    "🏏",
    "🥅",
    "⛳",
    "🪁",
    "🏹",
    "🎣",
    "🤿",
    "🥊",
    "🥋",
    "🎽",
    "🛹",
    "🛼",
    "🛷",
    "⛸️",
]

ALL_EMOJIS = ANIMALS + FOOD + TRANSPORT + SPORT

STYLES = ["danger", "success", "primary"]


def webapp_captcha_url(token: str) -> str:
    """
    Строит URL Mini App капчи, привязанный к конкретной сессии по token.

    Единственная точка сборки — учитывает `settings.URL_PREFIX` так же, как раньше
    делали по месту `app/bot/handlers/common.py` и debug-пути (`admin.py`, `api/captcha.py`).
    Token уходит в query-строку фрагмента (`#/captcha?token=...`) — фронтенд на HashRouter
    читает его через обычный `useSearchParams()`.
    """
    url = URL(settings.WEBAPP_URL)
    if settings.URL_PREFIX:
        url = url / settings.URL_PREFIX.strip("/")
    url = url / "webapp"
    url = url.with_fragment(f"/captcha?token={token}")
    return str(url)


def captcha_fallback_delay(captcha_timeout: int) -> int | None:
    """
    Задержка публичного дубля капчи для чата с таким `captcha_timeout`.

    Дубль позже кика бессмыслен, поэтому настроенная задержка ужимается до половины
    окна: человеку остаётся ровно столько же времени, сколько было потрачено впустую.
    None -- окно настолько мало, что дублировать нечем (публиковать сразу же значит
    показать капчу дважды одновременно).

    :param captcha_timeout: Окно на прохождение капчи в секундах
    :return: Задержка в секундах или None, если дубль не нужен
    """
    delay = min(settings.CAPTCHA_FALLBACK_DELAY, captcha_timeout // 2)
    return delay if delay >= 1 else None


class CaptchaResult(StrEnum):
    """Результат проверки капчи."""

    SUCCESS = "success"
    FAIL = "fail"
    RETRY = "retry"


class CaptchaButton(BaseModel):
    """Модель кнопки капчи."""

    emoji: str
    code: str
    style: str


class CaptchaData(BaseModel):
    """Данные сгенерированной капчи для отправки пользователю."""

    target_emoji: str
    target_style: str
    buttons: list[CaptchaButton]


class CaptchaSessionData(BaseModel):
    """Данные сессии капчи для хранения в Redis."""

    correct_code: str
    target_emoji: str
    attempts_left: int
    # Раскладка нужна, чтобы публичный дубль показывал ТУ ЖЕ капчу: перегенерация
    # сделала бы отставшее эфемерное сообщение ловушкой со списанием попытки.
    # Дефолты -- ради сессий, созданных до появления полей.
    target_style: str = ""
    buttons: list[CaptchaButton] = Field(default_factory=list)


def build_captcha_keyboard(user_id: int, buttons: list[CaptchaButton]) -> InlineKeyboardMarkup:
    """
    Собирает сетку 4x4 из кнопок капчи.

    :param user_id: ID проверяемого пользователя (уходит в callback_data)
    :param buttons: Кнопки капчи
    :return: Клавиатура капчи
    """
    keyboard = [
        InlineKeyboardButton(text=btn.emoji, callback_data=f"cap:{user_id}:{btn.code}", style=btn.style)
        for btn in buttons
    ]
    return InlineKeyboardMarkup(inline_keyboard=[keyboard[i : i + 4] for i in range(0, len(keyboard), 4)])


def captcha_emoji_text(i18n: TranslatorRunner, user_mention: str, target_emoji: str, target_style: str) -> str:
    """
    Текст emoji-капчи с названием целевого цвета на языке чата.

    :param i18n: Переводчик
    :param user_mention: HTML-упоминание пользователя
    :param target_emoji: Целевой эмодзи
    :param target_style: Стиль правильной кнопки
    :return: Готовый HTML-текст
    """
    colors = {
        "danger": i18n.captcha.color.danger(),
        "success": i18n.captcha.color.success(),
        "primary": i18n.captcha.color.primary(),
    }
    return i18n.captcha.emoji(user=user_mention, emoji=target_emoji, color=colors[target_style])


class CaptchaService:
    """Сервис для работы с Emoji капчей."""

    @staticmethod
    def _get_redis_key(chat_id: int, user_id: int) -> str:
        """
        Генерирует ключ для Redis.

        :param chat_id: ID чата
        :param user_id: ID пользователя
        :return: Строка ключа
        """
        return f"captcha:session:{chat_id}:{user_id}"

    @staticmethod
    def _generate_captcha_buttons() -> tuple[str, str, str, list[CaptchaButton]]:
        """
        Генерирует кнопки капчи.

        :return: (target_emoji, target_style, correct_code, buttons)
        """
        selected_emojis = random.sample(ALL_EMOJIS, 15)
        target_emoji = selected_emojis[0]

        target_style = secrets.choice(STYLES)
        decoy_style = secrets.choice([s for s in STYLES if s != target_style])

        correct_code = str(uuid.uuid4())
        buttons: list[CaptchaButton] = [
            CaptchaButton(emoji=target_emoji, code=correct_code, style=target_style),
            CaptchaButton(emoji=target_emoji, code=str(uuid.uuid4()), style=decoy_style),
        ]

        buttons.extend(
            CaptchaButton(emoji=emoji, code=str(uuid.uuid4()), style=secrets.choice(STYLES))
            for emoji in selected_emojis[1:]
        )

        random.shuffle(buttons)

        correct_index = next(i for i, b in enumerate(buttons) if b.code == correct_code)
        if correct_index == 0:
            buttons[0], buttons[1] = buttons[1], buttons[0]
        elif correct_index == 15:
            buttons[15], buttons[14] = buttons[14], buttons[15]

        return target_emoji, target_style, correct_code, buttons

    @classmethod
    async def create_session(
        cls, chat_id: int, user_id: int, session_ttl: int = 300, max_attempts: int = 3
    ) -> CaptchaData:
        """
        Создает новую сессию капчи, генерирует эмодзи и сохраняет в Redis.

        Целевой эмодзи появляется дважды — в правильном и обманном цвете.
        Пользователь должен выбрать эмодзи именно в указанном цвете.

        :param chat_id: ID чата
        :param user_id: ID пользователя
        :param session_ttl: Время жизни сессии в секундах
        :param max_attempts: Максимальное количество попыток
        :return: Данные капчи для отображения
        """
        target_emoji, target_style, correct_code, buttons = cls._generate_captcha_buttons()

        session_data = CaptchaSessionData(
            correct_code=correct_code,
            target_emoji=target_emoji,
            attempts_left=max_attempts,
            target_style=target_style,
            buttons=buttons,
        )

        key = cls._get_redis_key(chat_id, user_id)
        await valkey.set(key, session_data.model_dump_json(), ex=session_ttl)

        return CaptchaData(target_emoji=target_emoji, target_style=target_style, buttons=buttons)

    @classmethod
    async def regenerate_session(cls, chat_id: int, user_id: int) -> CaptchaData | None:
        """
        Перегенерирует кнопки капчи, сохраняя оставшееся количество попыток и TTL.

        :param chat_id: ID чата
        :param user_id: ID пользователя
        :return: Новые данные капчи или None, если сессия не найдена
        """
        key = cls._get_redis_key(chat_id, user_id)
        data_json = await valkey.get(key)

        if not data_json:
            return None

        old_session = CaptchaSessionData.model_validate_json(data_json)
        remaining_ttl = await valkey.ttl(key)

        target_emoji, target_style, correct_code, buttons = cls._generate_captcha_buttons()

        session_data = CaptchaSessionData(
            correct_code=correct_code,
            target_emoji=target_emoji,
            attempts_left=old_session.attempts_left,
            target_style=target_style,
            buttons=buttons,
        )

        await valkey.set(key, session_data.model_dump_json(), ex=max(remaining_ttl, 1))

        return CaptchaData(target_emoji=target_emoji, target_style=target_style, buttons=buttons)

    @classmethod
    async def verify_attempt(cls, chat_id: int, user_id: int, code: str) -> CaptchaResult:
        """
        Проверяет попытку ввода капчи.

        :param chat_id: ID чата
        :param user_id: ID пользователя
        :param code: Код нажатой кнопки
        :return: Результат проверки (SUCCESS, FAIL, RETRY)
        """
        key = cls._get_redis_key(chat_id, user_id)
        data_json = await valkey.get(key)

        if not data_json:
            return CaptchaResult.FAIL

        session_data = CaptchaSessionData.model_validate_json(data_json)

        if code == session_data.correct_code:
            await valkey.delete(key)
            return CaptchaResult.SUCCESS

        session_data.attempts_left -= 1

        if session_data.attempts_left <= 0:
            await valkey.delete(key)
            return CaptchaResult.FAIL

        remaining_ttl = await valkey.ttl(key)
        await valkey.set(key, session_data.model_dump_json(), ex=max(remaining_ttl, 1))
        return CaptchaResult.RETRY

    @classmethod
    async def get_session(cls, chat_id: int, user_id: int) -> CaptchaSessionData | None:
        """
        Получает данные текущей сессии.

        :param chat_id: ID чата
        :param user_id: ID пользователя
        :return: Данные сессии или None
        """
        key = cls._get_redis_key(chat_id, user_id)
        data_json = await valkey.get(key)

        if not data_json:
            return None

        return CaptchaSessionData.model_validate_json(data_json)
