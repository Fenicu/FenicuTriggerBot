import asyncio
import json
import logging
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime

import regex

logger = logging.getLogger(__name__)

REGEX_MAX_LENGTH = 500
REGEX_MATCH_TIMEOUT = 1.0
REGEX_PROBE_TIMEOUT = 1.0


def _normalize_key(value: str) -> str:
    """NFKC-нормализация ключа триггера (запись/хранение)."""
    return unicodedata.normalize("NFKC", value)


def _normalize_for_match(value: str, *, case_sensitive: bool) -> str:
    """NFKC + опционально casefold (сравнение на матчинге)."""
    normalized = unicodedata.normalize("NFKC", value)
    return normalized if case_sensitive else normalized.casefold()


def _regex_probes(pattern: str) -> list[str]:
    """Строит нагрузочные строки из литеральных символов самого паттерна."""
    literals = "".join(dict.fromkeys(ch for ch in pattern if ch.isalnum())) or "a"
    repeated = (literals * (120 // len(literals) + 1))[:120]
    return [repeated, repeated + "!", "a" * 100, "a" * 100 + "!"]


async def validate_regex(pattern: str) -> str | None:
    """Validate a regex pattern for safety. Returns error message or None if valid."""
    if len(pattern) > REGEX_MAX_LENGTH:
        return f"Regex too long (max {REGEX_MAX_LENGTH} chars)"

    try:
        compiled = regex.compile(pattern)
    except regex.error as e:
        return f"Invalid regex: {e}"

    # regex поддерживает реальный timeout и прерывает катастрофический backtracking
    try:
        for probe in _regex_probes(pattern):
            compiled.search(probe, timeout=REGEX_PROBE_TIMEOUT)
    except TimeoutError:
        return "Regex pattern is too complex (possible ReDoS)"
    except Exception:  # noqa: S110
        pass

    return None


from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.broker import broker
from app.core.storage import storage
from app.core.valkey import valkey
from app.db.models.chat import BannedChat, Chat
from app.db.models.moderation_history import ModerationStep
from app.db.models.trigger import AccessLevel, MatchType, ModerationStatus, Trigger
from app.schemas.moderation import TriggerModerationTask
from app.services.chat_trust_service import register_false_positive
from app.services.daily_stats_service import count_trigger_usage
from app.services.moderation_history_service import add_history_step
from app.services.preview_service import generate_preview_url
from app.services.rich_html import degrade_to_html

CACHE_TTL = 3600


FILE_TYPE_KEYS = ("photo", "video", "video_note", "animation", "document", "sticker", "voice", "audio")


def get_file_id_from_content(content: dict) -> str | None:
    """Получить file_id из контента триггера."""
    for key in FILE_TYPE_KEYS:
        if content.get(key):
            if key == "photo":
                return content["photo"][-1]["file_id"]
            return content[key]["file_id"]
    return None


def get_file_type_from_content(content: dict) -> str | None:
    """Получить тип файла из контента триггера."""
    for key in FILE_TYPE_KEYS:
        if content.get(key):
            return key
    return None


def get_file_info_from_content(content: dict) -> tuple[str | None, str | None]:
    """Получить file_id и file_type из контента триггера."""
    for key in FILE_TYPE_KEYS:
        if content.get(key):
            if key == "photo":
                return content["photo"][-1]["file_id"], key
            return content[key]["file_id"], key
    return None, None


def build_moderation_task(trigger: Trigger, *, user_id: int | None, silent: bool = False) -> TriggerModerationTask:
    """Собрать задачу модерации из сохранённого контента триггера.

    URL кнопок и скрытых text_link-сущностей попадают в text_content: link_urls
    обрезается LINK_FETCH_MAX_LINKS и не используется при выключенном анализе ссылок,
    поэтому иначе часть URL никогда не доходила бы до модели.
    """
    content = trigger.content or {}
    text_content = content.get("text") or ""
    caption = content.get("caption") or ""
    if trigger.rich:
        text_content = degrade_to_html(text_content) if text_content else ""
        caption = degrade_to_html(caption) if caption else ""
    file_id, file_type = get_file_info_from_content(content)

    hidden_urls = [
        entity["url"]
        for entity in [*(content.get("entities") or []), *(content.get("caption_entities") or [])]
        if entity.get("type") == "text_link" and entity.get("url")
    ]
    link_urls = list(hidden_urls)
    if hidden_urls:
        hidden_str = "Hidden links: " + " | ".join(dict.fromkeys(hidden_urls))
        text_content = f"{text_content}\n{hidden_str}" if text_content else hidden_str

    reply_markup = content.get("reply_markup")
    if reply_markup and reply_markup.get("inline_keyboard"):
        button_parts = []
        for row in reply_markup["inline_keyboard"]:
            for btn in row:
                btn_text = btn.get("text", "")
                btn_url = btn.get("url", "")
                if btn_url:
                    link_urls.append(btn_url)
                    button_parts.append(f"[{btn_text}]({btn_url})" if btn_text else btn_url)
                elif btn_text:
                    button_parts.append(btn_text)
        if button_parts:
            buttons_str = "Buttons: " + " | ".join(button_parts)
            text_content = f"{text_content}\n{buttons_str}" if text_content else buttons_str

    return TriggerModerationTask(
        trigger_id=trigger.id,
        chat_id=trigger.chat_id,
        user_id=user_id,
        text_content=text_content,
        caption=caption,
        link_urls=list(dict.fromkeys(link_urls)),
        file_id=file_id,
        file_type=file_type,
        silent=silent,
    )


class DuplicateTriggerError(ValueError):
    """Полный клон уже существует: тот же ключ и тот же контент в этом чате."""

    def __init__(self, existing_id: int) -> None:
        super().__init__(f"trigger {existing_id} already exists")
        self.existing_id = existing_id


async def find_clone(
    session: AsyncSession,
    chat_id: int,
    key_phrase: str,
    content: dict,
    match_type: MatchType,
    is_case_sensitive: bool,
) -> Trigger | None:
    """Найти живой триггер, который сработает так же и ответит тем же."""
    stmt = select(Trigger).where(
        Trigger.chat_id == chat_id,
        Trigger.key_phrase == _normalize_key(key_phrase),
        Trigger.match_type == match_type,
        Trigger.is_case_sensitive == is_case_sensitive,
        Trigger.content == content,
        Trigger.is_deleted.is_(False),
    )
    return (await session.execute(stmt.order_by(Trigger.id).limit(1))).scalar_one_or_none()


async def create_trigger(
    session: AsyncSession,
    chat_id: int,
    key_phrase: str,
    content: dict,
    match_type: MatchType = MatchType.EXACT,
    is_case_sensitive: bool = False,
    access_level: AccessLevel = AccessLevel.ALL,
    created_by: int = 0,
    skip_moderation: bool = False,
    is_template: bool = False,
    rich: bool = False,
) -> Trigger:
    """Создать новый триггер."""
    key_phrase = _normalize_key(key_phrase)

    clone = await find_clone(session, chat_id, key_phrase, content, match_type, is_case_sensitive)
    if clone is not None:
        raise DuplicateTriggerError(clone.id)

    moderation_status = ModerationStatus.SAFE if skip_moderation else ModerationStatus.PENDING

    trigger = Trigger(
        chat_id=chat_id,
        key_phrase=key_phrase,
        content=content,
        match_type=match_type,
        is_case_sensitive=is_case_sensitive,
        access_level=access_level,
        created_by=created_by,
        moderation_status=moderation_status,
        is_template=is_template,
        rich=rich,
    )
    session.add(trigger)
    try:
        await session.flush()
    except IntegrityError as e:
        # Гонка: параллельная транзакция вставила такой же триггер между нашей
        # проверкой и flush. Ловит уникальный индекс uq_triggers_no_full_clone.
        await session.rollback()
        existing = await find_clone(session, chat_id, key_phrase, content, match_type, is_case_sensitive)
        raise DuplicateTriggerError(existing.id if existing else 0) from e
    await session.refresh(trigger)

    await add_history_step(session, trigger.id, ModerationStep.CREATED)

    await session.commit()
    await invalidate_triggers_cache(chat_id)

    if skip_moderation:
        return trigger

    # Prepare moderation task
    task = build_moderation_task(trigger, user_id=created_by)

    try:
        await set_processing_status(trigger.id)
        await broker.publish(task, "q.moderation.analyze", persist=True)
        await add_history_step(session, trigger.id, ModerationStep.QUEUED)
        await session.commit()
    except Exception as e:
        logger.error("Failed to queue trigger %d for moderation: %s", trigger.id, e)
        await session.rollback()
        await clear_processing_status(trigger.id)

    return trigger


async def set_processing_status(trigger_id: int, ttl: int = 3600) -> None:
    """Установить статус обработки триггера.

    TTL 1 час: при семафоре=1 на inference и большом backlog'е сообщение
    может ждать в очереди дольше прежних 20 мин -- иначе valkey-ключ истечёт
    раньше реальной обработки и UI пометит триггер 'застрявшим', хотя он
    нормально стоит в q.moderation.analyze.
    """
    await valkey.set(f"trigger_processing:{trigger_id}", "1", ex=ttl)


async def get_processing_status(trigger_id: int) -> bool:
    """Проверить статус обработки триггера."""
    return bool(await valkey.exists(f"trigger_processing:{trigger_id}"))


async def clear_processing_status(trigger_id: int) -> None:
    """Удалить статус обработки триггера."""
    await valkey.delete(f"trigger_processing:{trigger_id}")


async def approve_trigger(session: AsyncSession, trigger_id: int, admin_id: int) -> Trigger | None:
    """Одобрить триггер.

    Условный UPDATE (moderation_status = прежнее значение) вместо read-then-write:
    если два администратора одновременно одобряют один и тот же FLAGGED-триггер, только
    первый меняет статус и учитывает ложное срабатывание -- второй получает rowcount=0
    и не задваивает счётчик (см. defect #2 ревью).
    """
    trigger = await get_trigger_by_id(session, trigger_id)
    if not trigger:
        return None

    previous_status = trigger.moderation_status
    was_flagged = previous_status == ModerationStatus.FLAGGED
    reason = f"Manual Approve by Admin {admin_id}"

    stmt = (
        update(Trigger)
        .where(Trigger.id == trigger_id, Trigger.moderation_status == previous_status)
        .values(moderation_status=ModerationStatus.SAFE, moderation_reason=reason)
    )
    result = await session.execute(stmt)
    if result.rowcount != 1:
        # Статус сменился между чтением и записью -- отдаём актуальное состояние,
        # повторно ложное срабатывание не считаем.
        return await get_trigger_by_id(session, trigger_id)

    trigger.moderation_status = ModerationStatus.SAFE
    trigger.moderation_reason = reason
    await add_history_step(
        session,
        trigger_id,
        ModerationStep.MANUAL_APPROVED,
        details={"admin_id": admin_id},
        actor_id=admin_id,
    )

    if was_flagged:
        # register_false_positive коммитит сессию сам -- статус триггера и учёт репутации
        # уходят одной транзакцией (см. defect #4 ревью).
        try:
            await register_false_positive(session, trigger.chat_id)
        except Exception as e:
            logger.warning("Failed to register false positive for chat %s: %s", trigger.chat_id, e)
    else:
        await session.commit()

    await session.refresh(trigger)
    await invalidate_triggers_cache(trigger.chat_id)

    return trigger


async def requeue_trigger(session: AsyncSession, trigger_id: int) -> Trigger | None:
    """Отправить триггер на перепроверку."""
    trigger = await get_trigger_by_id(session, trigger_id)
    if not trigger:
        return None

    trigger.moderation_status = ModerationStatus.PENDING
    await add_history_step(session, trigger_id, ModerationStep.REQUEUED)
    await session.commit()
    await session.refresh(trigger)

    task = build_moderation_task(trigger, user_id=trigger.created_by)

    try:
        await set_processing_status(trigger.id)
        await broker.publish(task, "q.moderation.analyze", persist=True)
        await add_history_step(session, trigger_id, ModerationStep.QUEUED)
        await session.commit()
    except Exception as e:
        logger.error("Failed to queue trigger %d for remoderation: %s", trigger_id, e)
        await session.rollback()
        await clear_processing_status(trigger.id)

    return trigger


async def get_triggers_filtered(
    session: AsyncSession,
    page: int,
    limit: int,
    status: str | None = None,
    search: str | None = None,
    chat_id: int | None = None,
    created_by: int | None = None,
    sort_by: str = "created_at",
    order: str = "desc",
    active_only: bool = True,
) -> tuple[list[Trigger], int]:
    """Получить список триггеров с фильтрацией."""
    offset = (page - 1) * limit

    # Base query with LEFT OUTER JOIN for chat_title
    stmt = select(Trigger, Chat.title.label("chat_title")).outerjoin(Chat, Trigger.chat_id == Chat.id)

    if active_only:
        stmt = stmt.where(Chat.is_active.is_(True))

    # Special status filters for audit views
    if status == "deleted":
        # Show soft-deleted triggers (including from banned chats)
        stmt = stmt.where(Trigger.is_deleted.is_(True))
    elif status == "banned_chat":
        # Show all triggers from banned chats
        stmt = stmt.where(Trigger.chat_id.in_(select(BannedChat.chat_id)))
    else:
        # Normal view: exclude banned chats and soft-deleted.
        # Исключение -- явно запрошенный чат: его карточка показывает счётчик из
        # get_triggers_count (про бан не знает), и без этого список забаненного чата
        # оказывался пустым при заявленных N триггерах. Заодно это единственный способ
        # посмотреть, за что чат забанили.
        if chat_id is None:
            stmt = stmt.where(~Trigger.chat_id.in_(select(BannedChat.chat_id)))
        stmt = stmt.where(Trigger.is_deleted.is_(False))
        if status and status != "all":
            stmt = stmt.where(Trigger.moderation_status == status)

    if search:
        # Числовой запрос ищет и по точному ID, и по вхождению в key_phrase --
        # иначе триггер с числовым ключом (например, "2025") найти нельзя.
        if search.isdigit():
            stmt = stmt.where(or_(Trigger.id == int(search), Trigger.key_phrase.ilike(f"%{search}%")))
        else:
            stmt = stmt.where(Trigger.key_phrase.ilike(f"%{search}%"))

    if chat_id:
        stmt = stmt.where(Trigger.chat_id == chat_id)

    if created_by is not None:
        stmt = stmt.where(Trigger.created_by == created_by)

    # Count query
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await session.execute(count_stmt)).scalar() or 0

    # Sorting — explicit column mapping
    sort_columns = {
        "created_at": Trigger.created_at,
        "key_phrase": Trigger.key_phrase,
        "usage_count": Trigger.usage_count,
    }
    sort_col = sort_columns.get(sort_by, Trigger.created_at)
    # Trigger.id.desc() -- tie-breaker: без него строки с равным sort_col (например,
    # одинаковым created_at) отдаются в неопределённом порядке.
    stmt = stmt.order_by(sort_col.desc() if order == "desc" else sort_col.asc(), Trigger.id.desc())

    stmt = stmt.offset(offset).limit(limit)
    result = await session.execute(stmt)
    rows = result.all()

    # Attach transient attributes
    triggers = []
    for trigger, chat_title in rows:
        trigger.chat_title = chat_title
        trigger.preview_url = generate_preview_url(trigger.id)
        triggers.append(trigger)

    return triggers, total


@dataclass(frozen=True)
class UserTriggerChatStat:
    """Один чат в агрегате «где пользователь создавал триггеры» (карточка автора в админке)."""

    chat_id: int
    chat_title: str | None
    trigger_count: int
    last_created_at: datetime


async def get_user_trigger_chats(session: AsyncSession, user_id: int) -> list[UserTriggerChatStat]:
    """Получить чаты, в которых пользователь создавал триггеры.

    Забаненные чаты не исключаются -- админ смотрит историю конкретного человека,
    ему важно видеть всё, включая триггеры в чатах, которые с тех пор забанили.
    trigger_count считает только живые триггеры (is_deleted=False); last_created_at --
    дата последнего созданного триггера в чате независимо от его текущего статуса.
    """
    alive_count = func.count().filter(Trigger.is_deleted.is_(False))
    last_created = func.max(Trigger.created_at)

    stmt = (
        select(
            Trigger.chat_id,
            Chat.title.label("chat_title"),
            alive_count.label("trigger_count"),
            last_created.label("last_created_at"),
        )
        .outerjoin(Chat, Trigger.chat_id == Chat.id)
        .where(Trigger.created_by == user_id)
        .group_by(Trigger.chat_id, Chat.title)
        .order_by(alive_count.desc(), last_created.desc())
    )
    result = await session.execute(stmt)

    return [
        UserTriggerChatStat(
            chat_id=row.chat_id,
            chat_title=row.chat_title,
            trigger_count=row.trigger_count,
            last_created_at=row.last_created_at,
        )
        for row in result.all()
    ]


async def get_triggers_stats(
    session: AsyncSession,
    active_only: bool = True,
) -> dict[str, int]:
    """Получить счётчики триггеров по статусам."""
    stmt = select(Trigger.moderation_status, func.count()).group_by(Trigger.moderation_status)

    if active_only:
        stmt = stmt.outerjoin(Chat, Trigger.chat_id == Chat.id).where(Chat.is_active.is_(True))

    # Exclude banned chats and soft-deleted triggers
    stmt = stmt.where(~Trigger.chat_id.in_(select(BannedChat.chat_id)))
    stmt = stmt.where(Trigger.is_deleted.is_(False))

    result = await session.execute(stmt)

    # Fill all statuses with zeros, then overwrite with actual counts
    stats = {s.value: 0 for s in ModerationStatus}
    for status, count in result.all():
        stats[status.value] = count

    # Count soft-deleted triggers separately. Считаем ровно как фильтруется список
    # (status=deleted, см. get_triggers_filtered) -- без исключения забаненных чатов.
    # Триггер, удалённый в забаненном чате, попадает и в deleted, и в banned_chat --
    # так и должно быть, вкладки пересекаются (см. defect #7 ревью: прежняя правка,
    # исключавшая забаненные чаты из deleted, рассинхронизировала счётчик со списком).
    deleted_stmt = select(func.count()).select_from(Trigger).where(Trigger.is_deleted.is_(True))
    if active_only:
        deleted_stmt = deleted_stmt.outerjoin(Chat, Trigger.chat_id == Chat.id).where(Chat.is_active.is_(True))
    stats["deleted"] = (await session.execute(deleted_stmt)).scalar() or 0

    # Count triggers in banned chats
    banned_stmt = select(func.count()).select_from(Trigger).where(Trigger.chat_id.in_(select(BannedChat.chat_id)))
    if active_only:
        banned_stmt = banned_stmt.outerjoin(Chat, Trigger.chat_id == Chat.id).where(Chat.is_active.is_(True))
    stats["banned_chat"] = (await session.execute(banned_stmt)).scalar() or 0

    return stats


@dataclass(frozen=True, slots=True)
class CachedTrigger:
    """Поля триггера, нужные для матчинга и отправки. Контент в кэш не кладём."""

    id: int
    key_phrase: str
    match_type: MatchType
    is_case_sensitive: bool
    access_level: AccessLevel
    is_template: bool
    rich: bool
    moderation_status: ModerationStatus

    def to_cache(self) -> dict:
        return {
            "id": self.id,
            "key_phrase": self.key_phrase,
            "match_type": self.match_type.value,
            "is_case_sensitive": self.is_case_sensitive,
            "access_level": self.access_level.value,
            "is_template": self.is_template,
            "rich": self.rich,
            "moderation_status": self.moderation_status.value,
        }

    @classmethod
    def from_cache(cls, data: dict) -> "CachedTrigger":
        return cls(
            id=data["id"],
            key_phrase=data["key_phrase"],
            match_type=MatchType(data["match_type"]),
            is_case_sensitive=data["is_case_sensitive"],
            access_level=AccessLevel(data["access_level"]),
            is_template=data.get("is_template", False),
            rich=data.get("rich", False),
            moderation_status=ModerationStatus(data.get("moderation_status", ModerationStatus.SAFE.value)),
        )


@dataclass(frozen=True)
class TriggerContentSnapshot:
    """Контент и актуальные поля триггера для отправки сообщения."""

    content: dict
    access_level: AccessLevel
    is_template: bool
    rich: bool


def _triggers_cache_key(chat_id: int) -> str:
    return f"triggers:{chat_id}"


def _triggers_version_key(chat_id: int) -> str:
    return f"triggers_ver:{chat_id}"


async def invalidate_triggers_cache(chat_id: int) -> None:
    """Сбросить кэш триггеров чата после записи в БД.

    Версия растёт на каждую запись: читатель, который прочитал список из БД до этой
    записи, сохранит его под старой версией, и такой список больше никто не примет.
    """
    await valkey.incr(_triggers_version_key(chat_id))
    await valkey.delete(_triggers_cache_key(chat_id))


async def get_triggers_by_chat(session: AsyncSession, chat_id: int) -> list[CachedTrigger]:
    """Получить триггеры чата для матчинга (с кэшированием, без контента)."""
    cache_key = _triggers_cache_key(chat_id)
    raw_version, cached_data = await valkey.mget(_triggers_version_key(chat_id), cache_key)
    # Версию фиксируем до чтения из БД -- под ней же список и будет сохранён
    version = int(raw_version or 0)

    if cached_data:
        payload = json.loads(cached_data)
        if isinstance(payload, dict):
            if payload.get("v") == version:
                return [CachedTrigger.from_cache(t_data) for t_data in payload["items"]]
        elif version == 0:
            # Список старого формата (без версии) годен, пока в чате не было записей
            return [CachedTrigger.from_cache(t_data) for t_data in payload]

    # ORDER BY id: при нескольких совпадениях отвечают одни и те же триггеры в одном порядке
    stmt = (
        select(
            Trigger.id,
            Trigger.key_phrase,
            Trigger.match_type,
            Trigger.is_case_sensitive,
            Trigger.access_level,
            Trigger.is_template,
            Trigger.rich,
            Trigger.moderation_status,
        )
        .where(Trigger.chat_id == chat_id, Trigger.is_deleted.is_(False))
        .order_by(Trigger.id)
    )
    result = await session.execute(stmt)
    triggers = [CachedTrigger(*row) for row in result.all()]

    payload = {"v": version, "items": [t.to_cache() for t in triggers]}
    await valkey.set(cache_key, json.dumps(payload), ex=CACHE_TTL)

    return triggers


async def get_trigger_content(session: AsyncSession, trigger_id: int) -> dict | None:
    """Контент живого триггера по id; None, если триггер удалён."""
    snapshot = await get_trigger_content_snapshot(session, trigger_id)
    return snapshot.content if snapshot is not None else None


async def get_trigger_content_snapshot(session: AsyncSession, trigger_id: int) -> "TriggerContentSnapshot | None":
    """Контент живого триггера вместе с актуальными полями рендеринга.

    Кэш списка триггеров может отставать от БД: access_level, is_template и rich
    читаются из БД в той же выборке, что и контент, чтобы не отправить сообщение
    по устаревшим правилам.
    """
    stmt = select(Trigger.content, Trigger.access_level, Trigger.is_template, Trigger.rich).where(
        Trigger.id == trigger_id, Trigger.is_deleted.is_(False)
    )
    row = (await session.execute(stmt)).one_or_none()
    if row is None:
        return None
    return TriggerContentSnapshot(
        content=row.content,
        access_level=AccessLevel(row.access_level),
        is_template=row.is_template,
        rich=row.rich,
    )


async def find_matches[T: (Trigger, CachedTrigger)](triggers: list[T], text: str) -> list[T]:
    """Найти все подходящие триггеры для текста.

    Перед сравнением текст и ключ приводятся к NFKC; для case-insensitive
    дополнительно применяется casefold. Это даёт совпадение compat-форм
    (ﬁ↔fi, fullwidth↔halfwidth) и корректную обработку «ß↔ss» и пр.
    """
    matches = []
    regex_triggers = [t for t in triggers if t.match_type == MatchType.REGEXP]
    exact_triggers = [t for t in triggers if t.match_type == MatchType.EXACT]
    contains_triggers = [t for t in triggers if t.match_type == MatchType.CONTAINS]

    # Текст сообщения нормализуется один раз, а не на каждый триггер
    text_nfkc = unicodedata.normalize("NFKC", text)
    text_folded = text_nfkc.casefold()

    if regex_triggers:

        def _match_regexes() -> list[T]:
            results = []
            for t in regex_triggers:
                # FULLCASE: полное сворачивание регистра (ß ↔ ss), как casefold у exact/contains
                flags = 0 if t.is_case_sensitive else regex.IGNORECASE | regex.FULLCASE
                try:
                    compiled = regex.compile(t.key_phrase, flags)
                except regex.error:
                    continue
                try:
                    if compiled.search(text_nfkc, timeout=REGEX_MATCH_TIMEOUT):
                        results.append(t)
                except TimeoutError:
                    logger.warning("Regex trigger %d timed out; treated as no match", t.id)
            return results

        regex_matches = await asyncio.to_thread(_match_regexes)
        matches.extend(regex_matches)

    for t in exact_triggers:
        text_cmp = text_nfkc if t.is_case_sensitive else text_folded
        if text_cmp == _normalize_for_match(t.key_phrase, case_sensitive=t.is_case_sensitive):
            matches.append(t)

    for t in contains_triggers:
        text_cmp = text_nfkc if t.is_case_sensitive else text_folded
        if _normalize_for_match(t.key_phrase, case_sensitive=t.is_case_sensitive) in text_cmp:
            matches.append(t)

    return matches


async def get_trigger_by_key(session: AsyncSession, chat_id: int, key_phrase: str) -> Trigger | None:
    """Получить триггер по ключу."""
    stmt = select(Trigger).where(
        Trigger.chat_id == chat_id,
        Trigger.key_phrase == key_phrase,
        Trigger.is_deleted.is_(False),
    )
    result = await session.execute(stmt)
    return result.scalars().first()


async def delete_trigger_by_key(session: AsyncSession, chat_id: int, key_phrase: str) -> bool:
    """Мягко удалить триггер по ключу."""
    stmt = select(Trigger).where(
        Trigger.chat_id == chat_id,
        Trigger.key_phrase == key_phrase,
        Trigger.is_deleted.is_(False),
    )
    result = await session.execute(stmt)
    trigger = result.scalars().first()

    if trigger:
        trigger.is_deleted = True
        trigger.deleted_at = datetime.now(UTC)
        await session.commit()
        await invalidate_triggers_cache(chat_id)
        return True
    return False


async def increment_usage(session: AsyncSession, trigger_id: int) -> None:
    """Увеличить счетчик использования триггера."""
    stmt = update(Trigger).where(Trigger.id == trigger_id).values(usage_count=Trigger.usage_count + 1)
    await session.execute(stmt)

    await session.commit()

    await count_trigger_usage()


async def get_triggers_count(session: AsyncSession, chat_id: int) -> int:
    """Получить количество триггеров в чате."""
    stmt = (
        select(func.count())
        .select_from(Trigger)
        .where(
            Trigger.chat_id == chat_id,
            Trigger.is_deleted.is_(False),
        )
    )
    return (await session.execute(stmt)).scalar() or 0


async def get_triggers_paginated(
    session: AsyncSession, chat_id: int, page: int, page_size: int
) -> tuple[list[Trigger], int]:
    """Получить список триггеров с пагинацией."""
    offset = (page - 1) * page_size

    total = await get_triggers_count(session, chat_id)

    stmt = (
        select(Trigger)
        .where(
            Trigger.chat_id == chat_id,
            Trigger.is_deleted.is_(False),
        )
        .order_by(Trigger.id)
        .offset(offset)
        .limit(page_size)
    )
    result = await session.execute(stmt)
    triggers = result.scalars().all()

    return list(triggers), total


async def get_trigger_by_id(session: AsyncSession, trigger_id: int) -> Trigger | None:
    """Получить триггер по ID (исключая мягко удалённые)."""
    stmt = select(Trigger).where(Trigger.id == trigger_id, Trigger.is_deleted.is_(False))
    result = await session.execute(stmt)
    return result.scalars().first()


async def update_trigger(session: AsyncSession, trigger_id: int, **kwargs) -> Trigger | None:
    """Обновить триггер."""
    trigger = await get_trigger_by_id(session, trigger_id)
    if not trigger:
        return None

    if "content" in kwargs:
        old_file_id = get_file_id_from_content(trigger.content)
        new_file_id = get_file_id_from_content(kwargs["content"])

        if old_file_id and old_file_id != new_file_id:
            await storage.delete_file(old_file_id)

    for key, value in kwargs.items():
        setattr(trigger, key, value)

    await session.commit()
    await session.refresh(trigger)

    await invalidate_triggers_cache(trigger.chat_id)

    return trigger


async def delete_trigger_by_id(session: AsyncSession, trigger_id: int) -> bool:
    """Мягко удалить триггер по ID (сохраняет данные для аудита)."""
    trigger = await get_trigger_by_id(session, trigger_id)
    if not trigger or trigger.is_deleted:
        return False

    trigger.is_deleted = True
    trigger.deleted_at = datetime.now(UTC)

    chat_id = trigger.chat_id
    await session.commit()

    await invalidate_triggers_cache(chat_id)

    return True


async def delete_all_triggers_by_chat(session: AsyncSession, chat_id: int) -> int:
    """Мягко удалить все триггеры чата."""
    now = datetime.now(UTC)
    stmt = (
        update(Trigger)
        .where(Trigger.chat_id == chat_id, Trigger.is_deleted.is_(False))
        .values(is_deleted=True, deleted_at=now)
    )
    result = await session.execute(stmt)
    deleted_count = result.rowcount
    await session.commit()

    await invalidate_triggers_cache(chat_id)

    return deleted_count


async def bulk_remoderate_safe(session: AsyncSession) -> int:
    """Отправить все Safe и Pending триггеры на перемодерацию (silent — без алертов).

    Только из активных незабаненных чатов.
    """
    stmt = (
        select(Trigger)
        .join(Chat, Trigger.chat_id == Chat.id)
        .where(
            Trigger.moderation_status.in_([ModerationStatus.SAFE, ModerationStatus.PENDING]),
            Trigger.is_deleted.is_(False),
            Chat.is_active.is_(True),
            ~Trigger.chat_id.in_(select(BannedChat.chat_id)),
        )
    )
    result = await session.execute(stmt)
    triggers = result.scalars().all()

    if not triggers:
        return 0

    # Init progress in Valkey
    bulk_key = "bulk_remoderate_progress"
    await valkey.delete(bulk_key)
    await valkey.hset(bulk_key, mapping={"total": len(triggers), "processed": 0, "flagged": 0, "status": "running"})
    await valkey.expire(bulk_key, 7200)  # 2 hours TTL

    for trigger in triggers:
        trigger.moderation_status = ModerationStatus.PENDING
        await add_history_step(session, trigger.id, ModerationStep.REQUEUED, details={"bulk": True})

        task = build_moderation_task(trigger, user_id=trigger.created_by or 0, silent=True)

        await set_processing_status(trigger.id)
        await broker.publish(task, "q.moderation.analyze", persist=True)
        await add_history_step(session, trigger.id, ModerationStep.QUEUED)

    await session.commit()
    return len(triggers)
