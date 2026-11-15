from decimal import Decimal
from typing import Literal

from fluent_compiler.types import FluentType
from typing_extensions import TypeAlias

PossibleValue: TypeAlias = str | int | float | Decimal | bool | FluentType

class TranslatorRunner:
    def get(self, path: str, **kwargs: PossibleValue) -> str: ...
    lang: Lang
    trigger: Trigger
    settings: Settings
    error: Error
    ephemeral: Ephemeral
    confirm: Confirm
    action: Action
    btn: Btn
    delete: Delete
    triggers: Triggers
    add: Add
    val: Val
    moderation: Moderation
    start: Start
    mod: Mod
    anime: Anime
    chat: Chat
    args: Args
    user: User
    captcha: Captcha
    var: Var
    welcome: Welcome
    gban: Gban
    punishment: Punishment
    warns: Warns
    content: Content
    reputation: Reputation
    tag: Tag
    tags: Tags
    new: New

class LangDisplay:
    @staticmethod
    def name() -> Literal["""🇷🇺 Русский"""]: ...

class LangSelect:
    @staticmethod
    def title() -> Literal["""🌐 &lt;b&gt;Выберите язык&lt;/b&gt;"""]: ...

class Lang:
    display: LangDisplay
    select: LangSelect

class TriggerAdd:
    @staticmethod
    def error() -> Literal["""Ошибка при добавлении триггера."""]: ...

class TriggerList:
    @staticmethod
    def header(*, count: PossibleValue) -> Literal["""📂 &lt;b&gt;Список триггеров чата&lt;/b&gt; (Всего: { $count })"""]: ...
    @staticmethod
    def page(*, page: PossibleValue, total: PossibleValue) -> Literal["""Страница { $page } из { $total }"""]: ...
    @staticmethod
    def outdated() -> Literal["""Это сообщение устарело. Откройте список заново: /triggers"""]: ...
    @staticmethod
    def empty() -> Literal["""Триггеры не найдены."""]: ...

class TriggerEdit:
    @staticmethod
    def title() -> Literal["""⚙️ &lt;b&gt;Настройка триггера&lt;/b&gt;"""]: ...
    @staticmethod
    def key(*, trigger_key: PossibleValue) -> Literal["""🔑 &lt;b&gt;Ключ:&lt;/b&gt; &lt;code&gt;{ $trigger_key }&lt;/code&gt;"""]: ...
    @staticmethod
    def type(*, type: PossibleValue) -> Literal["""📄 &lt;b&gt;Тип:&lt;/b&gt; { $type }"""]: ...
    @staticmethod
    def created(*, user: PossibleValue) -> Literal["""👤 &lt;b&gt;Создал:&lt;/b&gt; { $user }"""]: ...
    @staticmethod
    def stats(*, count: PossibleValue) -> Literal["""📊 &lt;b&gt;Статистика:&lt;/b&gt; { $count } срабатываний"""]: ...
    @staticmethod
    def case(*, value: PossibleValue) -> Literal["""🔠 &lt;b&gt;Регистр:&lt;/b&gt; { $value }"""]: ...
    @staticmethod
    def template(*, value: PossibleValue) -> Literal["""📝 &lt;b&gt;Шаблон:&lt;/b&gt; { $value }"""]: ...
    @staticmethod
    def access(*, value: PossibleValue) -> Literal["""🔒 &lt;b&gt;Доступ:&lt;/b&gt; { $value }"""]: ...

class TriggerDelete:
    @staticmethod
    def error() -> Literal["""Не удалось удалить триггер."""]: ...

class TriggerValidation:
    @staticmethod
    def error(*, error: PossibleValue) -> Literal["""Ошибка валидации шаблона: { $error }"""]: ...

class Trigger:
    add: TriggerAdd
    list: TriggerList
    edit: TriggerEdit
    delete: TriggerDelete
    validation: TriggerValidation

    @staticmethod
    def added(*, trigger_key: PossibleValue) -> Literal["""Триггер «{ $trigger_key }» успешно добавлен!"""]: ...
    @staticmethod
    def duplicate(*, trigger_id: PossibleValue, trigger_key: PossibleValue) -> Literal["""Такой триггер уже есть в этом чате — ключ «{ $trigger_key }» с точно таким же содержимым (ID { $trigger_id }). Ничего не добавлено."""]: ...
    @staticmethod
    def deleted() -> Literal["""Триггер удален."""]: ...
    @staticmethod
    def missing() -> Literal["""Триггер не найден."""]: ...

class SettingsLang:
    @staticmethod
    def changed(*, lang: PossibleValue) -> Literal["""Язык изменен на { $lang }."""]: ...

class SettingsTimezone:
    @staticmethod
    def __call__(*, timezone: PossibleValue) -> Literal["""🌍 Таймзона: { $timezone }"""]: ...
    @staticmethod
    def updated(*, timezone: PossibleValue) -> Literal["""✅ Таймзона изменена на { $timezone }"""]: ...

class SettingsSelect:
    @staticmethod
    def timezone() -> Literal["""🌍 Выберите таймзону или введите название зоны (например, Europe/Moscow)"""]: ...

class SettingsEnter:
    @staticmethod
    def timezone() -> Literal["""🌍 Введите название таймзоны (например, Europe/Moscow) и отправьте сообщением."""]: ...

class SettingsCaptchaType:
    @staticmethod
    def emoji() -> Literal["""Эмодзи (Emoji)"""]: ...
    @staticmethod
    def webapp() -> Literal["""WebApp"""]: ...
    @staticmethod
    def label(*, type: PossibleValue) -> Literal["""Тип: { $type }"""]: ...

class SettingsCaptchaTimeout:
    @staticmethod
    def label(*, timeout: PossibleValue) -> Literal["""Таймаут: { $timeout }"""]: ...
    @staticmethod
    def select() -> Literal["""⏳ Выберите время на прохождение капчи:"""]: ...

class SettingsCaptchaAttempts:
    @staticmethod
    def label(*, count: PossibleValue) -> Literal["""Попытки: { $count }"""]: ...

class SettingsCaptchaBan:
    @staticmethod
    def label(*, duration: PossibleValue) -> Literal["""Бан за провал: { $duration }"""]: ...
    @staticmethod
    def select() -> Literal["""🔨 Выберите длительность бана за провал капчи:"""]: ...

class SettingsCaptcha:
    type: SettingsCaptchaType
    timeout: SettingsCaptchaTimeout
    attempts: SettingsCaptchaAttempts
    ban: SettingsCaptchaBan

    @staticmethod
    def title() -> Literal["""🧩 &lt;b&gt;Настройки капчи&lt;/b&gt;"""]: ...
    @staticmethod
    def status(*, status: PossibleValue) -> Literal["""Статус: { $status }"""]: ...

class SettingsTriggers:
    @staticmethod
    def title() -> Literal["""🎯 &lt;b&gt;Настройки триггеров&lt;/b&gt;"""]: ...
    @staticmethod
    def module(*, status: PossibleValue) -> Literal["""Модуль: { $status }"""]: ...
    @staticmethod
    def admins(*, status: PossibleValue) -> Literal["""Только админы: { $status }"""]: ...

class SettingsSummary:
    @staticmethod
    def captcha(*, status: PossibleValue) -> Literal["""🧩 Капча: { $status }"""]: ...
    @staticmethod
    def moderation(*, status: PossibleValue) -> Literal["""👮‍♂️ Модерация: { $status }"""]: ...
    @staticmethod
    def triggers(*, status: PossibleValue) -> Literal["""🎯 Триггеры: { $status }"""]: ...
    @staticmethod
    def tags(*, status: PossibleValue) -> Literal["""🏷 Теги: { $status }"""]: ...

class SettingsOpen:
    @staticmethod
    def webapp() -> Literal["""⚙️ Открыть настройки"""]: ...

class SettingsWebapp:
    @staticmethod
    def sent() -> Literal["""Нажмите кнопку ниже, чтобы открыть настройки чата."""]: ...

class SettingsNo:
    @staticmethod
    def admin() -> Literal["""Вы не являетесь администратором этого чата."""]: ...

class SettingsChat:
    @staticmethod
    def missing() -> Literal["""Чат не найден."""]: ...

class Settings:
    lang: SettingsLang
    timezone: SettingsTimezone
    select: SettingsSelect
    enter: SettingsEnter
    captcha: SettingsCaptcha
    triggers: SettingsTriggers
    summary: SettingsSummary
    open: SettingsOpen
    webapp: SettingsWebapp
    no: SettingsNo
    chat: SettingsChat

    @staticmethod
    def title() -> Literal["""⚙️ &lt;b&gt;Настройки чата&lt;/b&gt;"""]: ...
    @staticmethod
    def updated() -> Literal["""Настройки обновлены."""]: ...
    @staticmethod
    def trusted() -> Literal["""🛡 Чат является доверенным"""]: ...

class ErrorNo:
    @staticmethod
    def rights() -> Literal["""У вас нет прав."""]: ...

class ErrorPermission:
    @staticmethod
    def denied() -> Literal["""У вас нет прав на редактирование этого триггера."""]: ...

class ErrorPrivate:
    @staticmethod
    def only() -> Literal["""Эта команда доступна только в личных сообщениях."""]: ...

class ErrorInvalid:
    @staticmethod
    def timezone() -> Literal["""❌ Неверная таймзона. Попробуйте еще раз."""]: ...

class Error:
    no: ErrorNo
    permission: ErrorPermission
    private: ErrorPrivate
    invalid: ErrorInvalid

    @staticmethod
    def unknown() -> Literal["""❌ Произошла неизвестная ошибка."""]: ...

class EphemeralFallback:
    @staticmethod
    def notice() -> Literal["""Ответ отправлен в личные сообщения."""]: ...

class Ephemeral:
    fallback: EphemeralFallback

class Confirm:
    @staticmethod
    def delete(*, trigger_key: PossibleValue) -> Literal["""Вы действительно хотите удалить триггер «{ $trigger_key }»?"""]: ...
    @staticmethod
    def clear() -> Literal["""Вы действительно хотите удалить ВСЕ триггеры?"""]: ...

class Action:
    @staticmethod
    def yes() -> Literal["""✅ Да, удалить"""]: ...
    @staticmethod
    def cancel() -> Literal["""❌ Отмена"""]: ...

class BtnCase:
    @staticmethod
    def sensitive() -> Literal["""Регистр: Чувствительный"""]: ...
    @staticmethod
    def insensitive() -> Literal["""Регистр: Нечувствительный"""]: ...

class BtnMatchtype:
    @staticmethod
    def exact() -> Literal["""Тип: Точное"""]: ...
    @staticmethod
    def contains() -> Literal["""Тип: Содержит"""]: ...
    @staticmethod
    def regexp() -> Literal["""Тип: Regex"""]: ...

class BtnAccess:
    @staticmethod
    def all() -> Literal["""Доступ: Все"""]: ...
    @staticmethod
    def admins() -> Literal["""Доступ: Админы"""]: ...
    @staticmethod
    def owner() -> Literal["""Доступ: Владелец"""]: ...

class BtnTemplate:
    @staticmethod
    def true() -> Literal["""Шаблон: Вкл"""]: ...
    @staticmethod
    def false() -> Literal["""Шаблон: Выкл"""]: ...

class BtnDelete:
    @staticmethod
    def __call__() -> Literal["""🗑 Удалить"""]: ...
    @staticmethod
    def trigger() -> Literal["""💀 Удалить триггер"""]: ...

class BtnClear:
    @staticmethod
    def triggers() -> Literal["""🗑 Удалить все триггеры"""]: ...

class BtnAdminsOnly:
    @staticmethod
    def true() -> Literal["""✅ Админы (только добавление)"""]: ...
    @staticmethod
    def false() -> Literal["""❌ Админы (только добавление)"""]: ...

class BtnAdmins:
    only: BtnAdminsOnly

class BtnCaptchaBan:
    @staticmethod
    def duration(*, duration: PossibleValue) -> Literal["""🔨 Бан: { $duration }"""]: ...

class BtnCaptcha:
    ban: BtnCaptchaBan

    @staticmethod
    def true() -> Literal["""✅ Капча"""]: ...
    @staticmethod
    def false() -> Literal["""❌ Капча"""]: ...
    @staticmethod
    def settings() -> Literal["""🧩 Капча"""]: ...
    @staticmethod
    def timeout(*, timeout: PossibleValue) -> Literal["""⏳ Таймаут: { $timeout }"""]: ...
    @staticmethod
    def attempts(*, count: PossibleValue) -> Literal["""🎯 Попытки: { $count }"""]: ...

class BtnTriggers:
    @staticmethod
    def true() -> Literal["""✅ Триггеры"""]: ...
    @staticmethod
    def false() -> Literal["""❌ Триггеры"""]: ...
    @staticmethod
    def settings() -> Literal["""🎯 Триггеры"""]: ...

class BtnModeration:
    @staticmethod
    def true() -> Literal["""✅ Модерация"""]: ...
    @staticmethod
    def false() -> Literal["""❌ Модерация"""]: ...
    @staticmethod
    def warns() -> Literal["""👮‍♂️ Модерация и Варны"""]: ...

class BtnCustom:
    @staticmethod
    def timezone() -> Literal["""✏️ Ввести вручную"""]: ...

class BtnFalse:
    @staticmethod
    def alarm() -> Literal["""✅ Ложная тревога"""]: ...

class BtnBan:
    @staticmethod
    def chat() -> Literal["""☢️ Забанить чат"""]: ...

class BtnTags:
    @staticmethod
    def true() -> Literal["""✅ Теги"""]: ...
    @staticmethod
    def false() -> Literal["""❌ Теги"""]: ...

class Btn:
    case: BtnCase
    matchtype: BtnMatchtype
    access: BtnAccess
    template: BtnTemplate
    delete: BtnDelete
    clear: BtnClear
    admins: BtnAdmins
    captcha: BtnCaptcha
    triggers: BtnTriggers
    moderation: BtnModeration
    custom: BtnCustom
    false: BtnFalse
    ban: BtnBan
    tags: BtnTags

    @staticmethod
    def close() -> Literal["""🗑 Закрыть"""]: ...
    @staticmethod
    def back() -> Literal["""« Назад"""]: ...
    @staticmethod
    def verify() -> Literal["""🔐 Пройти проверку"""]: ...

class Delete:
    @staticmethod
    def usage() -> Literal["""Использование: /del &amp;lt;ключ&amp;gt;"""]: ...

class TriggersCleared:
    @staticmethod
    def __call__(*, count: PossibleValue) -> Literal["""Удалено { $count } триггеров."""]: ...
    @staticmethod
    def text(*, count: PossibleValue) -> Literal["""✅ Удалено { $count } триггеров."""]: ...

class Triggers:
    cleared: TriggersCleared

class Add:
    @staticmethod
    def usage() -> Literal["""Использование: /add &amp;lt;ключ&amp;gt; [флаги]"""]: ...

class ValCase:
    @staticmethod
    def sensitive() -> Literal["""Чувствительный"""]: ...
    @staticmethod
    def insensitive() -> Literal["""Нечувствительный"""]: ...

class ValAccess:
    @staticmethod
    def all() -> Literal["""Все"""]: ...
    @staticmethod
    def admins() -> Literal["""Админы"""]: ...
    @staticmethod
    def owner() -> Literal["""Владелец"""]: ...

class ValTemplate:
    @staticmethod
    def true() -> Literal["""Да"""]: ...
    @staticmethod
    def false() -> Literal["""Нет"""]: ...

class Val:
    case: ValCase
    access: ValAccess
    template: ValTemplate

class ModerationGban:
    @staticmethod
    def toggle(*, status: PossibleValue) -> Literal["""{ $status } Глобальный бан"""]: ...

class Moderation:
    gban: ModerationGban

    @staticmethod
    def declined(*, content_text: PossibleValue, content_type: PossibleValue, reason: PossibleValue, trigger_key: PossibleValue) -> Literal["""❌ &lt;b&gt;Триггер отклонен&lt;/b&gt;

Ключ: { $trigger_key }
Тип: { $content_type }
Содержание: { $content_text }
Причина: { $reason }"""]: ...

class Start:
    @staticmethod
    def message(*, version: PossibleValue) -> Literal["""👋 &lt;b&gt;Привет!&lt;/b&gt;

Я бот для создания триггеров, но работаю я только в групповых чатах.
Добавь меня в чат, чтобы начать пользоваться!

📚 &lt;b&gt;Команды:&lt;/b&gt;
/add ключ - создать триггер
/del ключ - удалить триггер
/triggers - список триггеров
/settings - настройки
/lang - смена языка
/ban - забанить пользователя
/mute - заглушить пользователя
/warn - выдать предупреждение
/warns - список предупреждений
/unban - разбанить пользователя
/unmute - разглушить пользователя

🤖 &lt;b&gt;Версия:&lt;/b&gt; { $version }"""]: ...

class ModUser:
    @staticmethod
    def banned(*, date: PossibleValue, reason: PossibleValue, user: PossibleValue) -> Literal["""Пользователь { $user } был забанен. Истекает: { $date }. Причина: { $reason }"""]: ...
    @staticmethod
    def muted(*, date: PossibleValue, reason: PossibleValue, user: PossibleValue) -> Literal["""Пользователь { $user } был заглушен. Истекает: { $date }. Причина: { $reason }"""]: ...
    @staticmethod
    def unbanned(*, user: PossibleValue) -> Literal["""Пользователь { $user } разбанен."""]: ...
    @staticmethod
    def unmuted(*, user: PossibleValue) -> Literal["""Пользователь { $user } разглушен."""]: ...
    @staticmethod
    def kicked(*, user: PossibleValue) -> Literal["""Пользователь { $user } был исключен."""]: ...

class ModWarn:
    @staticmethod
    def added(*, cur: PossibleValue, max: PossibleValue, reason: PossibleValue, user: PossibleValue) -> Literal["""{ $user } получил предупреждение [{ $cur }/{ $max }]. Причина: { $reason }"""]: ...
    @staticmethod
    def removed(*, cur: PossibleValue, max: PossibleValue) -> Literal["""Варн снят. Текущий счет: { $cur }/{ $max }."""]: ...
    @staticmethod
    def reset(*, punishment: PossibleValue, user: PossibleValue) -> Literal["""Лимит предупреждений превышен. { $user } получает наказание: { $punishment }."""]: ...

class ModWarns:
    @staticmethod
    def list(*, cur: PossibleValue, list: PossibleValue, max: PossibleValue, user: PossibleValue) -> Literal["""Предупреждения пользователя { $user } ({ $cur }/{ $max }):
{ $list }"""]: ...

class ModErrorNo:
    @staticmethod
    def rights() -> Literal["""У бота недостаточно прав для выполнения этой операции."""]: ...

class ModError:
    no: ModErrorNo

    @staticmethod
    def admin() -> Literal["""Я не могу наказать администратора."""]: ...

class ModSettings:
    @staticmethod
    def title() -> Literal["""👮‍♂️ Настройки системы варнов"""]: ...
    @staticmethod
    def limit(*, limit: PossibleValue) -> Literal["""Лимит варнов: { $limit }"""]: ...

class ModPunishment:
    @staticmethod
    def ban() -> Literal["""🔨 Бан"""]: ...
    @staticmethod
    def mute() -> Literal["""🔇 Мут"""]: ...
    @staticmethod
    def btn(*, punishment: PossibleValue) -> Literal["""Наказание: { $punishment }"""]: ...

class ModDuration:
    @staticmethod
    def btn(*, duration: PossibleValue) -> Literal["""⏳ Длительность: { $duration }"""]: ...
    @staticmethod
    def forever() -> Literal["""Навсегда"""]: ...
    @staticmethod
    def min(*, count: PossibleValue) -> Literal["""{ $count } мин."""]: ...
    @staticmethod
    def hour(*, count: PossibleValue) -> Literal["""{ $count } ч."""]: ...
    @staticmethod
    def day(*, count: PossibleValue) -> Literal["""{ $count } дн."""]: ...
    @staticmethod
    def week(*, count: PossibleValue) -> Literal["""{ $count } нед."""]: ...
    @staticmethod
    def tenmin() -> Literal["""10 минут"""]: ...
    @staticmethod
    def onehour() -> Literal["""1 час"""]: ...
    @staticmethod
    def oneday() -> Literal["""1 сутки"""]: ...
    @staticmethod
    def oneweek() -> Literal["""1 неделя"""]: ...

class Mod:
    user: ModUser
    warn: ModWarn
    warns: ModWarns
    error: ModError
    settings: ModSettings
    punishment: ModPunishment
    duration: ModDuration

class AnimeError:
    @staticmethod
    def __call__() -> Literal["""❌ Произошла ошибка при поиске."""]: ...
    @staticmethod
    def reply() -> Literal["""❌ Используйте эту команду в ответ на изображение, GIF или видео."""]: ...

class Anime:
    error: AnimeError

    @staticmethod
    def searching() -> Literal["""🔎 Ищу аниме..."""]: ...
    @staticmethod
    def found(*, episode: PossibleValue, similarity: PossibleValue, timecode: PossibleValue, title_english: PossibleValue, title_native: PossibleValue) -> Literal["""🎬 &lt;b&gt;Аниме найдено!&lt;/b&gt;

🇯🇵 &lt;b&gt;Название:&lt;/b&gt; { $title_native }
🇬🇧 &lt;b&gt;English:&lt;/b&gt; { $title_english }
📺 &lt;b&gt;Эпизод:&lt;/b&gt; { $episode }
⏱ &lt;b&gt;Таймкод:&lt;/b&gt; { $timecode }
📊 &lt;b&gt;Сходство:&lt;/b&gt; { $similarity }%"""]: ...
    @staticmethod
    def missing() -> Literal["""❌ Аниме не найдено."""]: ...

class ChatBecame:
    @staticmethod
    def trusted(*, user: PossibleValue) -> Literal["""🛡 Чат стал доверенным благодаря пользователю { $user }."""]: ...

class Chat:
    became: ChatBecame

class Args:
    @staticmethod
    def error() -> Literal["""❌ Ошибка в аргументах."""]: ...

class UserPromoted:
    @staticmethod
    def mod(*, user: PossibleValue) -> Literal["""✅ Пользователь { $user } назначен модератором бота."""]: ...

class UserDemoted:
    @staticmethod
    def mod(*, user: PossibleValue) -> Literal["""ℹ️ Пользователь { $user } больше не модератор бота."""]: ...

class User:
    promoted: UserPromoted
    demoted: UserDemoted

    @staticmethod
    def missing() -> Literal["""❌ Пользователь не найден."""]: ...
    @staticmethod
    def trusted(*, user: PossibleValue) -> Literal["""✅ Пользователь { $user } назначен доверенным."""]: ...
    @staticmethod
    def untrusted(*, user: PossibleValue) -> Literal["""ℹ️ Пользователь { $user } больше не доверенный."""]: ...

class CaptchaWrong:
    @staticmethod
    def user() -> Literal["""❌ Эта капча предназначена для другого пользователя."""]: ...

class CaptchaAlready:
    @staticmethod
    def completed() -> Literal["""✅ Вы уже прошли эту капчу."""]: ...

class CaptchaOpen:
    @staticmethod
    def webapp() -> Literal["""👇 Нажмите кнопку ниже, чтобы пройти проверку:"""]: ...

class CaptchaInvalid:
    @staticmethod
    def link() -> Literal["""❌ Неверная ссылка для капчи."""]: ...

class CaptchaTimeout:
    @staticmethod
    def kick() -> Literal["""❌ Время вышло. Пользователь был исключен."""]: ...
    @staticmethod
    def onemin() -> Literal["""1 минута"""]: ...
    @staticmethod
    def twomin() -> Literal["""2 минуты"""]: ...
    @staticmethod
    def fivemin() -> Literal["""5 минут"""]: ...
    @staticmethod
    def tenmin() -> Literal["""10 минут"""]: ...

class CaptchaColor:
    @staticmethod
    def danger() -> Literal["""красном"""]: ...
    @staticmethod
    def success() -> Literal["""зелёном"""]: ...
    @staticmethod
    def primary() -> Literal["""синем"""]: ...

class CaptchaAttempts:
    @staticmethod
    def left(*, count: PossibleValue) -> Literal["""Осталось попыток: { $count }"""]: ...

class CaptchaBan:
    @staticmethod
    def threedays() -> Literal["""3 суток"""]: ...

class Captcha:
    wrong: CaptchaWrong
    already: CaptchaAlready
    open: CaptchaOpen
    invalid: CaptchaInvalid
    timeout: CaptchaTimeout
    color: CaptchaColor
    attempts: CaptchaAttempts
    ban: CaptchaBan

    @staticmethod
    def verify(*, user: PossibleValue) -> Literal["""👋 { $user }, для продолжения необходимо пройти проверку. Нажмите кнопку ниже."""]: ...
    @staticmethod
    def missing() -> Literal["""❌ Сессия капчи не найдена или истекла."""]: ...
    @staticmethod
    def expired() -> Literal["""⏱ Время на прохождение капчи истекло."""]: ...
    @staticmethod
    def success() -> Literal["""✅ Проверка пройдена! Добро пожаловать."""]: ...
    @staticmethod
    def emoji(*, color: PossibleValue, emoji: PossibleValue, user: PossibleValue) -> Literal["""👋 { $user }, выберите { $emoji } в { $color } цвете, чтобы подтвердить, что вы не робот."""]: ...
    @staticmethod
    def foreign() -> Literal["""❌ Эта кнопка не для вас!"""]: ...
    @staticmethod
    def retry(*, attempts: PossibleValue) -> Literal["""❌ Неверно! Осталось попыток: { $attempts }"""]: ...
    @staticmethod
    def fail() -> Literal["""❌ Вы не прошли проверку."""]: ...

class VarList:
    @staticmethod
    def empty() -> Literal["""ℹ️ Список переменных пуст."""]: ...
    @staticmethod
    def header() -> Literal["""📋 &lt;b&gt;Переменные чата:&lt;/b&gt;"""]: ...

class VarInvalid:
    @staticmethod
    def key() -> Literal["""❌ Неверный формат ключа. Используйте только латиницу и &lt;code&gt;_&lt;/code&gt;."""]: ...

class VarUsage:
    @staticmethod
    def set() -> Literal["""ℹ️ Использование: &lt;code&gt;/setvar &amp;lt;ключ&amp;gt; &amp;lt;значение&amp;gt;&lt;/code&gt;"""]: ...
    @staticmethod
    def delete() -> Literal["""ℹ️ Использование: &lt;code&gt;/delvar &amp;lt;ключ&amp;gt;&lt;/code&gt;"""]: ...

class Var:
    list: VarList
    invalid: VarInvalid
    usage: VarUsage

    @staticmethod
    def set(*, name: PossibleValue) -> Literal["""✅ Переменная &lt;code&gt;{ $name }&lt;/code&gt; установлена."""]: ...
    @staticmethod
    def deleted(*, name: PossibleValue) -> Literal["""🗑 Переменная &lt;code&gt;{ $name }&lt;/code&gt; удалена."""]: ...
    @staticmethod
    def missing(*, name: PossibleValue) -> Literal["""❌ Переменная &lt;code&gt;{ $name }&lt;/code&gt; не найдена."""]: ...

class WelcomeSetNo:
    @staticmethod
    def reply() -> Literal["""❌ Ответьте на сообщение, которое хотите сделать приветствием."""]: ...

class WelcomeSet:
    no: WelcomeSetNo

    @staticmethod
    def success(*, timeout: PossibleValue) -> Literal["""✅ Приветствие установлено! Автоудаление через { $timeout } сек."""]: ...

class WelcomeInvalid:
    @staticmethod
    def timeout() -> Literal["""❌ Неверный формат времени. Используйте секунды (60) или 5m, 1h."""]: ...

class Welcome:
    set: WelcomeSet
    invalid: WelcomeInvalid

    @staticmethod
    def usage() -> Literal["""ℹ️ Использование:
&lt;code&gt;/welcome set [таймаут]&lt;/code&gt; (в ответ на сообщение)
&lt;code&gt;/welcome delete&lt;/code&gt; - отключить
&lt;code&gt;/welcome test&lt;/code&gt; - проверить"""]: ...
    @staticmethod
    def disabled() -> Literal["""ℹ️ Приветствие отключено."""]: ...
    @staticmethod
    def unset() -> Literal["""❌ Приветствие не установлено."""]: ...

class GbanUser:
    @staticmethod
    def banned(*, user: PossibleValue) -> Literal["""⛔️ Пользователь { $user } находится в глобальном бан-листе и был забанен."""]: ...
    @staticmethod
    def warning(*, user: PossibleValue) -> Literal["""⚠️ Пользователь { $user } находится в глобальном бан-листе!"""]: ...

class Gban:
    user: GbanUser

class PunishmentDuration:
    @staticmethod
    def select() -> Literal["""Выберите длительность наказания:"""]: ...

class Punishment:
    duration: PunishmentDuration

    @staticmethod
    def ban() -> Literal["""Бан"""]: ...
    @staticmethod
    def mute() -> Literal["""Мут"""]: ...

class WarnsNone:
    @staticmethod
    def __call__() -> Literal["""У пользователя нет предупреждений."""]: ...
    @staticmethod
    def user(*, name: PossibleValue) -> Literal["""У пользователя { $name } нет предупреждений."""]: ...

class Warns:
    none: WarnsNone

class ContentType:
    @staticmethod
    def text() -> Literal["""Текст"""]: ...
    @staticmethod
    def photo() -> Literal["""Фото"""]: ...
    @staticmethod
    def video() -> Literal["""Видео"""]: ...
    @staticmethod
    def sticker() -> Literal["""Стикер"""]: ...
    @staticmethod
    def document() -> Literal["""Документ"""]: ...
    @staticmethod
    def gif() -> Literal["""GIF"""]: ...
    @staticmethod
    def voice() -> Literal["""Голосовое"""]: ...
    @staticmethod
    def audio() -> Literal["""Аудио"""]: ...

class Content:
    type: ContentType

class ReputationGroup:
    @staticmethod
    def only() -> Literal["""Эта команда работает только в групповых чатах."""]: ...

class ReputationNo:
    @staticmethod
    def data() -> Literal["""Данные о вашей активности пока не найдены."""]: ...

class ReputationNext:
    @staticmethod
    def level(*, remaining: PossibleValue) -> Literal["""До следующего: { $remaining }"""]: ...

class ReputationMax:
    @staticmethod
    def level() -> Literal["""Максимальный уровень достигнут!"""]: ...

class Reputation:
    group: ReputationGroup
    no: ReputationNo
    next: ReputationNext
    max: ReputationMax

    @staticmethod
    def disabled() -> Literal["""Система тегов не включена в этом чате."""]: ...
    @staticmethod
    def status(*, level: PossibleValue, level_name: PossibleValue, next_info: PossibleValue, progress_bar: PossibleValue, progress_pct: PossibleValue, rank: PossibleValue, score: PossibleValue, total: PossibleValue) -> Literal["""🏷 &lt;b&gt;Статус в чате&lt;/b&gt;

Уровень: &lt;b&gt;{ $level_name }&lt;/b&gt; (Lv.{ $level })
Очки: &lt;b&gt;{ $score }&lt;/b&gt;
{ $next_info }
Позиция: #{ $rank } из { $total }

{ $progress_bar } { $progress_pct }%"""]: ...

class TagReply:
    @staticmethod
    def required() -> Literal["""Ответьте на сообщение пользователя, чтобы установить тег."""]: ...

class Tag:
    reply: TagReply

    @staticmethod
    def usage() -> Literal["""Использование: ответьте на сообщение пользователя с /tag &amp;lt;текст тега&amp;gt;"""]: ...
    @staticmethod
    def invalid() -> Literal["""❌ Тег может содержать только буквы, цифры, пробелы и дефисы."""]: ...
    @staticmethod
    def set(*, tag: PossibleValue, user: PossibleValue) -> Literal["""✅ Тег для { $user } установлен: &lt;b&gt;{ $tag }&lt;/b&gt;"""]: ...
    @staticmethod
    def cleared(*, user: PossibleValue) -> Literal["""ℹ️ Ручной тег для { $user } снят. Восстановлен автоматический."""]: ...

class TagsBotNo:
    @staticmethod
    def admin() -> Literal["""Бот должен быть администратором чата для управления тегами."""]: ...
    @staticmethod
    def permission() -> Literal["""У бота нет права «Управление тегами» (can_manage_tags). Выдайте это право в настройках чата."""]: ...

class TagsBot:
    no: TagsBotNo

class Tags:
    bot: TagsBot

class NewTriggerGroupEntry:
    @staticmethod
    def body() -> Literal["""Создание триггера выполняется в личных сообщениях с ботом, чтобы содержимое не было видно участникам чата до его срабатывания."""]: ...
    @staticmethod
    def button() -> Literal["""Создать в личных сообщениях"""]: ...

class NewTriggerGroup:
    entry: NewTriggerGroupEntry

class NewTriggerLobbyPage:
    @staticmethod
    def indicator(*, page: PossibleValue, total: PossibleValue) -> Literal["""{ $page }/{ $total }"""]: ...

class NewTriggerLobby:
    page: NewTriggerLobbyPage

    @staticmethod
    def title() -> Literal["""В каком чате создаём триггер?"""]: ...
    @staticmethod
    def empty() -> Literal["""У вас нет чатов, где бот установлен и где вам разрешено создавать триггеры."""]: ...

class NewTriggerContentCommand:
    @staticmethod
    def warning() -> Literal["""Это похоже на команду. Использовать её как контент триггера?"""]: ...

class NewTriggerContentWrong:
    @staticmethod
    def type() -> Literal["""Ожидается сообщение-контент. Отправьте текст, фото, видео, GIF, стикер, документ или голосовое сообщение."""]: ...

class NewTriggerContent:
    command: NewTriggerContentCommand
    wrong: NewTriggerContentWrong

    @staticmethod
    def prompt(*, title: PossibleValue) -> Literal["""Чат: { $title }

Отправьте сообщение, которое бот будет присылать в ответ на триггер. Поддерживаются любые типы: текст, фото, видео, анимация, стикер, документ, голосовое сообщение."""]: ...
    @staticmethod
    def saved() -> Literal["""Сообщение сохранено."""]: ...

class NewTriggerKeyToo:
    @staticmethod
    def long(*, limit: PossibleValue) -> Literal["""Ключ слишком длинный (максимум { $limit } символов)."""]: ...

class NewTriggerKeyWrong:
    @staticmethod
    def type() -> Literal["""Ожидается текст ключа. Отправьте текстовое сообщение."""]: ...

class NewTriggerKey:
    too: NewTriggerKeyToo
    wrong: NewTriggerKeyWrong

    @staticmethod
    def prompt() -> Literal["""Укажите текст, на который должен срабатывать триггер.

Точное совпадение: «привет»
Регулярное выражение: «^(привет|hi)\b»"""]: ...
    @staticmethod
    def empty() -> Literal["""Ключ не может быть пустым."""]: ...

class NewTriggerFlagsCase:
    @staticmethod
    def on() -> Literal["""Учитывать регистр"""]: ...

class NewTriggerFlagsAccess:
    @staticmethod
    def all() -> Literal["""Все участники"""]: ...
    @staticmethod
    def admins() -> Literal["""Только администраторы"""]: ...
    @staticmethod
    def owner() -> Literal["""Только владелец"""]: ...

class NewTriggerFlagsTemplate:
    @staticmethod
    def __call__() -> Literal["""Шаблон ( переменные )"""]: ...
    @staticmethod
    def invalid(*, error: PossibleValue) -> Literal["""Ошибка в шаблоне: { $error }"""]: ...

class NewTriggerFlagsRegex:
    @staticmethod
    def invalid(*, error: PossibleValue) -> Literal["""Регулярное выражение некорректно: { $error }"""]: ...

class NewTriggerFlagsWrong:
    @staticmethod
    def input() -> Literal["""На этом шаге используйте кнопки. Отправьте /cancel для отмены."""]: ...

class NewTriggerFlags:
    case: NewTriggerFlagsCase
    access: NewTriggerFlagsAccess
    template: NewTriggerFlagsTemplate
    regex: NewTriggerFlagsRegex
    wrong: NewTriggerFlagsWrong

    @staticmethod
    def title(*, phrase: PossibleValue) -> Literal["""Ключ: «{ $phrase }»"""]: ...

class NewTriggerConfirmModeration:
    @staticmethod
    def pending() -> Literal["""Триггер отправлен на модерацию, начнёт работать после проверки."""]: ...

class NewTriggerConfirm:
    moderation: NewTriggerConfirmModeration

    @staticmethod
    def summary(*, access: PossibleValue, case_mode: PossibleValue, chat_title: PossibleValue, match_type: PossibleValue, phrase: PossibleValue, template: PossibleValue) -> Literal["""Предпросмотр ответа триггера.

Ключ: «{ $phrase }»
Тип: { $match_type }, { $case_mode }
Доступ: { $access }
Шаблон: { $template }
Чат: { $chat_title }"""]: ...
    @staticmethod
    def created() -> Literal["""Триггер создан."""]: ...

class NewTriggerConflictBody:
    @staticmethod
    def __call__() -> Literal["""Незавершённый процесс будет сброшен. Продолжить?"""]: ...
    @staticmethod
    def foreign() -> Literal["""У вас есть незавершённое действие. Сбросить?"""]: ...

class NewTriggerConflict:
    body: NewTriggerConflictBody

    @staticmethod
    def keep() -> Literal["""Вернуться к текущему"""]: ...

class NewTriggerPermission:
    @staticmethod
    def denied() -> Literal["""У вас нет прав на создание триггеров в этом чате."""]: ...
    @staticmethod
    def lost() -> Literal["""Ваши права в чате изменились. Создание отменено."""]: ...

class NewTriggerCancel:
    @staticmethod
    def done() -> Literal["""Создание триггера отменено."""]: ...

class NewTriggerSendCopyRetry:
    @staticmethod
    def after(*, seconds: PossibleValue) -> Literal["""Telegram попросил подождать { $seconds } сек. Попробуйте ещё раз."""]: ...

class NewTriggerSendCopy:
    retry: NewTriggerSendCopyRetry

    @staticmethod
    def failed() -> Literal["""Не удалось показать предпросмотр этого сообщения. Отправьте контент заново."""]: ...

class NewTriggerSend:
    copy: NewTriggerSendCopy

class NewTriggerSession:
    @staticmethod
    def expired() -> Literal["""Сессия истекла. Начните /newtrigger заново."""]: ...

class NewTriggerSave:
    @staticmethod
    def busy() -> Literal["""Сохранение уже выполняется."""]: ...

class NewTriggerPreviewEntities:
    @staticmethod
    def warning() -> Literal["""Не удалось разобрать форматирование контента. Премиум-эмодзи и шрифты могут не отобразиться."""]: ...

class NewTriggerPreview:
    entities: NewTriggerPreviewEntities

class NewTriggerCreate:
    @staticmethod
    def failed(*, error: PossibleValue) -> Literal["""Не удалось сохранить триггер: { $error }. Попробуйте ещё раз."""]: ...

class NewTriggerBtnUse:
    @staticmethod
    def this() -> Literal["""Использовать это"""]: ...

class NewTriggerBtnSend:
    @staticmethod
    def another() -> Literal["""Прислать другое"""]: ...

class NewTriggerBtnBackTo:
    @staticmethod
    def chat() -> Literal["""‹ Сменить чат"""]: ...
    @staticmethod
    def key() -> Literal["""‹ Изменить ключ"""]: ...
    @staticmethod
    def flags() -> Literal["""‹ Изменить параметры"""]: ...

class NewTriggerBtnBack:
    to: NewTriggerBtnBackTo

class NewTriggerBtn:
    use: NewTriggerBtnUse
    send: NewTriggerBtnSend
    back: NewTriggerBtnBack

    @staticmethod
    def cancel() -> Literal["""✕ Отмена"""]: ...
    @staticmethod
    def next() -> Literal["""Далее: предпросмотр ›"""]: ...
    @staticmethod
    def save() -> Literal["""✓ Сохранить"""]: ...
    @staticmethod
    def again() -> Literal["""Создать ещё один в этом чате"""]: ...
    @staticmethod
    def finish() -> Literal["""Завершить"""]: ...
    @staticmethod
    def restart() -> Literal["""Сбросить и начать заново"""]: ...
    @staticmethod
    def keep() -> Literal["""Вернуться к текущему"""]: ...

class NewTrigger:
    group: NewTriggerGroup
    lobby: NewTriggerLobby
    content: NewTriggerContent
    key: NewTriggerKey
    flags: NewTriggerFlags
    confirm: NewTriggerConfirm
    conflict: NewTriggerConflict
    permission: NewTriggerPermission
    cancel: NewTriggerCancel
    send: NewTriggerSend
    session: NewTriggerSession
    save: NewTriggerSave
    preview: NewTriggerPreview
    create: NewTriggerCreate
    btn: NewTriggerBtn

    @staticmethod
    def duplicate(*, trigger_id: PossibleValue) -> Literal["""Такой триггер уже есть в этом чате (ID { $trigger_id }): тот же ключ и то же содержимое. Измените текст ответа или ключ."""]: ...

class New:
    trigger: NewTrigger
