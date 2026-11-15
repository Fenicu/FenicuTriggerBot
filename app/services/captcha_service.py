import secrets
import uuid
from enum import StrEnum

from aiogram.types import DisabledButton, InlineKeyboardButton, InlineKeyboardMarkup
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

BUTTON_COUNT = 16
# Дублируется не только цель: раньше повтор был единственным и прямо указывал на ответ
# (50% с первой попытки, гарантированный перебор при пяти). Пар минимум шесть -- слепой
# тык по любой из 2*N дублированных кнопок даёт максимум 1/12 против 1/16 у честного
# угадывания; при восьми парах дублированы все кнопки и признак не значит вообще ничего.
# Само число пар случайно, чтобы по нему нельзя было строить стратегию.
MIN_DUPLICATE_PAIRS = 6
MAX_DUPLICATE_PAIRS = 8

# Раскладка -- защитный механизм, PRNG для неё берём криптостойкий, а не Mersenne Twister
_rng = secrets.SystemRandom()


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
    NO_SESSION = "no_session"


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


def build_captcha_keyboard(
    user_id: int,
    buttons: list[CaptchaButton],
    attempts_left: int | None = None,
    i18n: TranslatorRunner | None = None,
) -> InlineKeyboardMarkup:
    """
    Собирает сетку 4x4 из кнопок капчи.

    :param user_id: ID проверяемого пользователя (уходит в callback_data)
    :param buttons: Кнопки капчи
    :param attempts_left: Сколько попыток осталось. Если задано вместе с i18n --
        снизу добавляется неактивная кнопка-счётчик: иначе число попыток видно
        только во всплывающем алерте, который пропадает через пару секунд.
    :param i18n: Переводчик для подписи счётчика
    :return: Клавиатура капчи
    """
    keyboard = [
        InlineKeyboardButton(text=btn.emoji, callback_data=f"cap:{user_id}:{btn.code}", style=btn.style)
        for btn in buttons
    ]
    rows = [keyboard[i : i + 4] for i in range(0, len(keyboard), 4)]

    if attempts_left is not None and i18n is not None:
        # Счётчик -- украшение поверх капчи: если перевод не отдал строку, молча
        # пропускаем его, но саму проверку не роняем.
        label = i18n.captcha.attempts.left(count=attempts_left)
        if isinstance(label, str) and label:
            rows.append([InlineKeyboardButton(text=label, disabled=DisabledButton())])

    return InlineKeyboardMarkup(inline_keyboard=rows)


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

        Раскладка -- случайное число пар (`MIN_DUPLICATE_PAIRS`..`MAX_DUPLICATE_PAIRS`)
        одинаковых эмодзи плюс одиночки до 16 кнопок. Цель всегда одна из пар, и
        различает пару цвет: в этом смысл задания «нажми такое-то эмодзи такого-то
        цвета». Внутри пары стили обязательно разные -- иначе на экране две
        неотличимые кнопки. Правильный код ровно один, цветовой близнец цели и любые
        другие дубли неверны.

        :return: (target_emoji, target_style, correct_code, buttons)
        """
        pair_count = _rng.randint(MIN_DUPLICATE_PAIRS, MAX_DUPLICATE_PAIRS)
        selected_emojis = _rng.sample(ALL_EMOJIS, BUTTON_COUNT - pair_count)

        target_emoji = selected_emojis[0]
        target_style, decoy_style = _rng.sample(STYLES, 2)

        correct_code = str(uuid.uuid4())
        buttons: list[CaptchaButton] = [
            CaptchaButton(emoji=target_emoji, code=correct_code, style=target_style),
            CaptchaButton(emoji=target_emoji, code=str(uuid.uuid4()), style=decoy_style),
        ]

        for emoji in selected_emojis[1:pair_count]:
            buttons.extend(
                CaptchaButton(emoji=emoji, code=str(uuid.uuid4()), style=style) for style in _rng.sample(STYLES, 2)
            )

        buttons.extend(
            CaptchaButton(emoji=emoji, code=str(uuid.uuid4()), style=_rng.choice(STYLES))
            for emoji in selected_emojis[pair_count:]
        )

        _rng.shuffle(buttons)

        # Крайние позиции для ответа исключены, но простой обмен с соседом копил бы
        # ответ на позициях 1 и 14 (вдвое чаще прочих) -- уносим в случайную из середины
        correct_index = next(i for i, b in enumerate(buttons) if b.code == correct_code)
        if correct_index in (0, len(buttons) - 1):
            swap_index = _rng.randrange(1, len(buttons) - 1)
            buttons[correct_index], buttons[swap_index] = buttons[swap_index], buttons[correct_index]

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
        target_emoji, target_style, correct_code, buttons = cls._generate_captcha_buttons()
        layout = CaptchaSessionData(
            correct_code=correct_code,
            target_emoji=target_emoji,
            attempts_left=0,
            target_style=target_style,
            buttons=buttons,
        )
        updated = await valkey.eval(
            """
            local raw = redis.call('GET', KEYS[1])
            if not raw then return false end
            local current = cjson.decode(raw)
            local layout = cjson.decode(ARGV[1])
            layout.attempts_left = current.attempts_left
            redis.call('SET', KEYS[1], cjson.encode(layout), 'KEEPTTL')
            return true
            """,
            1,
            key,
            layout.model_dump_json(),
        )
        if not updated:
            return None
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
        result = await valkey.eval(
            """
            local raw = redis.call('GET', KEYS[1])
            if not raw then return 'no_session' end
            local data = cjson.decode(raw)
            if data.correct_code == ARGV[1] then
                redis.call('DEL', KEYS[1])
                return 'success'
            end
            local remaining = data.attempts_left - 1
            if remaining <= 0 then
                redis.call('DEL', KEYS[1])
                return 'fail'
            end
            local updated = string.gsub(raw, '"attempts_left"%s*:%s*%d+', '"attempts_left":' .. remaining, 1)
            redis.call('SET', KEYS[1], updated, 'KEEPTTL')
            return 'retry'
            """,
            1,
            key,
            code,
        )
        return CaptchaResult(result)

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
