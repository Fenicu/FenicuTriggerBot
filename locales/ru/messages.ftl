lang-display-name = 🇷🇺 Русский
trigger-added = Триггер «{ $trigger_key }» успешно добавлен!
trigger-add-error = Ошибка при добавлении триггера.
trigger-deleted = Триггер удален.
trigger-missing = Триггер не найден.
trigger-list-header = 📂 <b>Список триггеров чата</b> (Всего: { $count })
trigger-list-page = Страница { $page } из { $total }
trigger-edit-title = ⚙️ <b>Настройка триггера</b>
trigger-edit-key = 🔑 <b>Ключ:</b> <code>{ $trigger_key }</code>
trigger-edit-type = 📄 <b>Тип:</b> { $type }
trigger-edit-created = 👤 <b>Создал:</b> { $user }
trigger-edit-stats = 📊 <b>Статистика:</b> { $count } срабатываний
trigger-edit-case = 🔠 <b>Регистр:</b> { $value }
trigger-edit-template = 📝 <b>Шаблон:</b> { $value }
trigger-edit-access = 🔒 <b>Доступ:</b> { $value }
settings-title = ⚙️ <b>Настройки чата</b>

# settings-admins-only = Только админы могут добавлять: { $status }


# settings-captcha = 🧩 Капча при входе: { $status }

settings-lang-changed = Язык изменен на { $lang }.
error-no-rights = У вас нет прав.
error-permission-denied = У вас нет прав на редактирование этого триггера.
error-unknown = ❌ Произошла неизвестная ошибка.
confirm-delete = Вы действительно хотите удалить триггер «{ $trigger_key }»?
confirm-clear = Вы действительно хотите удалить ВСЕ триггеры?
action-yes = ✅ Да, удалить
action-cancel = ❌ Отмена
btn-close = 🗑 Закрыть
btn-back = « Назад
btn-case-sensitive = Регистр: Чувствительный
btn-case-insensitive = Регистр: Нечувствительный
btn-matchtype-exact = Тип: Точное
btn-matchtype-contains = Тип: Содержит
btn-matchtype-regexp = Тип: Regex
btn-access-all = Доступ: Все
btn-access-admins = Доступ: Админы
btn-access-owner = Доступ: Владелец
btn-template-true = Шаблон: Вкл
btn-template-false = Шаблон: Выкл
btn-delete = 🗑 Удалить
btn-clear-triggers = 🗑 Удалить все триггеры
btn-admins-only-true = ✅ Админы (только добавление)
btn-admins-only-false = ❌ Админы (только добавление)
lang-select-title = 🌐 <b>Выберите язык</b>
trigger-list-empty = Триггеры не найдены.
delete-usage = Использование: /del &lt;ключ&gt;
trigger-delete-error = Не удалось удалить триггер.
settings-updated = Настройки обновлены.
triggers-cleared = Удалено { $count } триггеров.
triggers-cleared-text = ✅ Удалено { $count } триггеров.
add-usage = Использование: /add &lt;ключ&gt; [флаги]
val-case-sensitive = Чувствительный
val-case-insensitive = Нечувствительный
val-access-all = Все
val-access-admins = Админы
val-access-owner = Владелец
val-template-true = Да
val-template-false = Нет
moderation-alert =
    🚨 <b>Подозрительный триггер</b>
    
    Категория: { $category } (conf: { $confidence })
    Чат: { $chat_id }
    ID: { $trigger_id }
    
    Ключ: { $trigger_key }
    Тип: { $content_type }
    Содержание: { $content_text }
    Причина: { $reasoning }

# moderation-approved =
#     ✅ <b>Триггер одобрен</b>
#     
#     Ключ: { $trigger_key }
#     Тип: { $content_type }
#     Содержание: { $content_text }

moderation-declined =
    ❌ <b>Триггер отклонен</b>
    
    Ключ: { $trigger_key }
    Тип: { $content_type }
    Содержание: { $content_text }
    Причина: { $reason }
start-message =
    👋 <b>Привет!</b>
    
    Я бот для создания триггеров, но работаю я только в групповых чатах.
    Добавь меня в чат, чтобы начать пользоваться!
    
    📚 <b>Команды:</b>
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
    
    🤖 <b>Версия:</b> { $version }

mod-user-banned = Пользователь { $user } был забанен. Истекает: { DATETIME($date) }. Причина: { $reason }
mod-user-muted = Пользователь { $user } был заглушен. Истекает: { DATETIME($date) }. Причина: { $reason }

mod-user-unbanned = Пользователь { $user } разбанен.
mod-user-unmuted = Пользователь { $user } разглушен.
mod-user-kicked = Пользователь { $user } был исключен.
mod-warn-added = { $user } получил предупреждение [{ $cur }/{ $max }]. Причина: { $reason }
mod-warn-removed = Варн снят. Текущий счет: { $cur }/{ $max }.
mod-warn-reset = Лимит предупреждений превышен. { $user } получает наказание: { $punishment }.
mod-warns-list =
    Предупреждения пользователя { $user } ({ $cur }/{ $max }):
    { $list }
mod-error-no-rights = У бота недостаточно прав для выполнения этой операции.
mod-error-admin = Я не могу наказать администратора.
mod-settings-title = 👮‍♂️ Настройки системы варнов
mod-settings-limit = Лимит варнов: { $limit }

# mod-settings-punishment = Наказание: { $punishment }


# mod-settings-duration = Длительность: { $duration }

anime-searching = 🔎 Ищу аниме...
anime-found =
    🎬 <b>Аниме найдено!</b>
    
    🇯🇵 <b>Название:</b> { $title_native }
    🇬🇧 <b>English:</b> { $title_english }
    📺 <b>Эпизод:</b> { $episode }
    ⏱ <b>Таймкод:</b> { $timecode }
    📊 <b>Сходство:</b> { $similarity }%
anime-missing = ❌ Аниме не найдено.
anime-error = ❌ Произошла ошибка при поиске.
anime-error-reply = ❌ Используйте эту команду в ответ на изображение, GIF или видео.
chat-became-trusted = 🛡 Чат стал доверенным благодаря пользователю { $user }.
args-error = ❌ Ошибка в аргументах.
user-missing = ❌ Пользователь не найден.
user-promoted-mod = ✅ Пользователь { $user } назначен модератором бота.
user-demoted-mod = ℹ️ Пользователь { $user } больше не модератор бота.
user-trusted = ✅ Пользователь { $user } назначен доверенным.
user-untrusted = ℹ️ Пользователь { $user } больше не доверенный.
settings-trusted = 🛡 Чат является доверенным
error-private-only = Эта команда доступна только в личных сообщениях.
btn-captcha-true = ✅ Капча
btn-captcha-false = ❌ Капча
settings-timezone = 🌍 Таймзона: { $timezone }

# settings-triggers = 🎯 Модуль триггеров: { $status }


# settings-moderation = 👮‍♂️ Модуль модерации: { $status }

btn-triggers-true = ✅ Триггеры
btn-triggers-false = ❌ Триггеры
btn-moderation-true = ✅ Модерация
btn-moderation-false = ❌ Модерация
settings-select-timezone = 🌍 Выберите таймзону или введите название зоны (например, Europe/Moscow)
btn-custom-timezone = ✏️ Ввести вручную
settings-enter-timezone = 🌍 Введите название таймзоны (например, Europe/Moscow) и отправьте сообщением.
settings-timezone-updated = ✅ Таймзона изменена на { $timezone }
error-invalid-timezone = ❌ Неверная таймзона. Попробуйте еще раз.
captcha-verify = 👋 { $user }, для продолжения необходимо пройти проверку. Нажмите кнопку ниже.
btn-verify = 🔐 Пройти проверку
captcha-missing = ❌ Сессия капчи не найдена или истекла.
captcha-wrong-user = ❌ Эта капча предназначена для другого пользователя.
captcha-already-completed = ✅ Вы уже прошли эту капчу.
captcha-expired = ⏱ Время на прохождение капчи истекло.
captcha-open-webapp = 👇 Нажмите кнопку ниже, чтобы пройти проверку:
captcha-invalid-link = ❌ Неверная ссылка для капчи.
captcha-success = ✅ Проверка пройдена! Добро пожаловать.
captcha-timeout-kick = ❌ Время вышло. Пользователь был исключен.
captcha-emoji = 👋 { $user }, выберите { $emoji } в { $color } цвете, чтобы подтвердить, что вы не робот.
captcha-color-danger = красном
captcha-color-success = зелёном
captcha-color-primary = синем
captcha-foreign = ❌ Эта кнопка не для вас!
captcha-retry = ❌ Неверно! Осталось попыток: { $attempts }
captcha-fail = ❌ Вы не прошли проверку.
var-set = ✅ Переменная <code>{ $name }</code> установлена.
var-deleted = 🗑 Переменная <code>{ $name }</code> удалена.
var-missing = ❌ Переменная <code>{ $name }</code> не найдена.
var-list-empty = ℹ️ Список переменных пуст.
var-list-header = 📋 <b>Переменные чата:</b>
var-invalid-key = ❌ Неверный формат ключа. Используйте только латиницу и <code>_</code>.
var-usage-set = ℹ️ Использование: <code>/setvar &lt;ключ&gt; &lt;значение&gt;</code>
var-usage-delete = ℹ️ Использование: <code>/delvar &lt;ключ&gt;</code>
welcome-usage =
    ℹ️ Использование:
    <code>/welcome set [таймаут]</code> (в ответ на сообщение)
    <code>/welcome delete</code> - отключить
    <code>/welcome test</code> - проверить
welcome-set-no-reply = ❌ Ответьте на сообщение, которое хотите сделать приветствием.
welcome-invalid-timeout = ❌ Неверный формат времени. Используйте секунды (60) или 5m, 1h.
welcome-set-success = ✅ Приветствие установлено! Автоудаление через { $timeout } сек.
welcome-disabled = ℹ️ Приветствие отключено.
welcome-unset = ❌ Приветствие не установлено.
settings-captcha-type-emoji = Эмодзи (Emoji)
settings-captcha-type-webapp = WebApp
gban-user-banned = ⛔️ Пользователь { $user } находится в глобальном бан-листе и был забанен.
gban-user-warning = ⚠️ Пользователь { $user } находится в глобальном бан-листе!

# btn-gban-true = ✅ Глобальный бан


# btn-gban-false = ❌ Глобальный бан


# settings-gban = 🌍 Глобальный бан-лист: { $status }


# moderation-gban-enabled = Глобальный бан: Включен


# moderation-gban-disabled = Глобальный бан: Выключен

moderation-gban-toggle = { $status } Глобальный бан

# gban-alert-text = 🚨 <b>Глобальный бан</b>


# gban-ban-button = 🔨 Забанить


# gban-banned-by-admin = Пользователь { $user } был забанен администратором.

mod-punishment-ban = 🔨 Бан
mod-punishment-mute = 🔇 Мут
mod-punishment-btn = Наказание: { $punishment }
mod-duration-btn = ⏳ Длительность: { $duration }
mod-duration-forever = Навсегда
mod-duration-min = { $count } мин.
mod-duration-hour = { $count } ч.
mod-duration-day = { $count } дн.
mod-duration-week = { $count } нед.
mod-duration-tenmin = 10 минут
mod-duration-onehour = 1 час
mod-duration-oneday = 1 сутки
mod-duration-oneweek = 1 неделя

# mod-duration-select = Выберите длительность наказания:

punishment-ban = Бан
punishment-mute = Мут
warns-none = У пользователя нет предупреждений.
warns-none-user = У пользователя { $name } нет предупреждений.
punishment-duration-select = Выберите длительность наказания:
trigger-validation-error = Ошибка валидации шаблона: { $error }
content-type-text = Текст
content-type-photo = Фото
content-type-video = Видео
content-type-sticker = Стикер
content-type-document = Документ
content-type-gif = GIF
content-type-voice = Голосовое
content-type-audio = Аудио
btn-false-alarm = ✅ Ложная тревога
btn-delete-trigger = 💀 Удалить триггер
btn-ban-chat = ☢️ Забанить чат
btn-moderation-warns = 👮‍♂️ Модерация и Варны
btn-captcha-settings = 🧩 Капча
btn-triggers-settings = 🎯 Триггеры
btn-captcha-timeout = ⏳ Таймаут: { $timeout }
settings-captcha-title = 🧩 <b>Настройки капчи</b>
settings-captcha-status = Статус: { $status }
settings-captcha-type-label = Тип: { $type }
settings-captcha-timeout-label = Таймаут: { $timeout }
settings-captcha-timeout-select = ⏳ Выберите время на прохождение капчи:
settings-triggers-title = 🎯 <b>Настройки триггеров</b>
settings-triggers-module = Модуль: { $status }
settings-triggers-admins = Только админы: { $status }
settings-summary-captcha = 🧩 Капча: { $status }
settings-summary-moderation = 👮‍♂️ Модерация: { $status }
settings-summary-triggers = 🎯 Триггеры: { $status }
captcha-timeout-onemin = 1 минута
captcha-timeout-twomin = 2 минуты
captcha-timeout-fivemin = 5 минут
captcha-timeout-tenmin = 10 минут
btn-captcha-attempts = 🎯 Попытки: { $count }
btn-captcha-ban-duration = 🔨 Бан: { $duration }
settings-captcha-attempts-label = Попытки: { $count }
settings-captcha-ban-label = Бан за провал: { $duration }
settings-captcha-ban-select = 🔨 Выберите длительность бана за провал капчи:
captcha-ban-threedays = 3 суток

# Reputation & Tags
reputation-group-only = Эта команда работает только в групповых чатах.
reputation-disabled = Система тегов не включена в этом чате.
reputation-no-data = Данные о вашей активности пока не найдены.
reputation-status =
    🏷 <b>Статус в чате</b>
    {""}
    Уровень: <b>{ $level_name }</b> (Lv.{ $level })
    Очки: <b>{ $score }</b>
    { $next_info }
    Позиция: #{ $rank } из { $total }
    {""}
    { $progress_bar } { $progress_pct }%
reputation-next-level = До следующего: { $remaining }
reputation-max-level = Максимальный уровень достигнут!
tag-usage = Использование: ответьте на сообщение пользователя с /tag &lt;текст тега&gt;
tag-invalid = ❌ Тег может содержать только буквы, цифры, пробелы и дефисы.
tag-reply-required = Ответьте на сообщение пользователя, чтобы установить тег.
tag-set = ✅ Тег для { $user } установлен: <b>{ $tag }</b>
tag-cleared = ℹ️ Ручной тег для { $user } снят. Восстановлен автоматический.
btn-tags-true = ✅ Теги
btn-tags-false = ❌ Теги
settings-summary-tags = 🏷 Теги: { $status }
tags-bot-no-admin = Бот должен быть администратором чата для управления тегами.
tags-bot-no-permission = У бота нет права «Управление тегами» (can_manage_tags). Выдайте это право в настройках чата.
settings-open-webapp = ⚙️ Открыть настройки
settings-webapp-sent = Нажмите кнопку ниже, чтобы открыть настройки чата.
settings-no-admin = Вы не являетесь администратором этого чата.
settings-chat-missing = Чат не найден.
