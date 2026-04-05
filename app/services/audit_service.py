import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.chat import Chat
from app.db.models.settings_audit import SettingsAuditLog

logger = logging.getLogger(__name__)

# Map each settings field to its section
FIELD_SECTION_MAP = {
    "language_code": "general",
    "timezone": "general",
    "captcha_enabled": "captcha",
    "captcha_type": "captcha",
    "captcha_timeout": "captcha",
    "captcha_max_attempts": "captcha",
    "captcha_ban_duration": "captcha",
    "module_moderation": "moderation",
    "warn_limit": "moderation",
    "warn_punishment": "moderation",
    "warn_duration": "moderation",
    "module_triggers": "triggers",
    "admins_only_add": "triggers",
    "tags_enabled": "tags",
    "tags_preset": "tags",
    "tags_custom": "tags",
    "tags_thresholds": "tags",
    "tags_weight_reactions": "tags",
    "tags_weight_replies": "tags",
    "tags_weight_messages": "tags",
    "tags_daily_message_limit": "tags",
    "tags_daily_reaction_limit": "tags",
    "welcome_enabled": "welcome",
    "welcome_message": "welcome",
    "welcome_delete_timeout": "welcome",
    "gban_enabled": "other",
    "is_trusted": "other",
    "settings_locked_sections": "other",
}

VALID_SECTIONS = {"general", "captcha", "moderation", "triggers", "tags", "welcome", "other"}


async def record_settings_changes(
    session: AsyncSession,
    chat: Chat,
    user_id: int,
    update_data: dict,
) -> None:
    """Record audit log entries for settings changes. Groups by section."""
    # Group changes by section
    sections: dict[str, list[dict]] = {}

    for field, new_value in update_data.items():
        section = FIELD_SECTION_MAP.get(field)
        if not section:
            continue

        old_value = getattr(chat, field, None)

        # Skip if unchanged
        if old_value == new_value:
            continue

        # Serialize for JSON
        old_serialized = _serialize(old_value)
        new_serialized = _serialize(new_value)

        if section not in sections:
            sections[section] = []

        sections[section].append({
            "field": field,
            "old": old_serialized,
            "new": new_serialized,
        })

    # Create one audit entry per section
    for section, changes in sections.items():
        if not changes:
            continue
        entry = SettingsAuditLog(
            chat_id=chat.id,
            user_id=user_id,
            section=section,
            changes=changes,
        )
        session.add(entry)


def _serialize(value: object) -> object:
    """Serialize value for JSON storage."""
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, dict)):
        return value
    return str(value)


def check_section_access(
    chat: Chat,
    update_data: dict,
    is_creator: bool,
) -> list[str]:
    """Check if user can modify the fields in update_data.

    Returns list of field names that are blocked (in locked sections and user is not creator).
    """
    if is_creator:
        return []

    locked = chat.settings_locked_sections or []
    if not locked:
        return []

    blocked = []
    for field in update_data:
        section = FIELD_SECTION_MAP.get(field)
        if section and section in locked:
            blocked.append(field)

    return blocked


async def get_audit_log(
    session: AsyncSession,
    chat_id: int,
    page: int = 1,
    limit: int = 20,
) -> tuple[list[SettingsAuditLog], int]:
    """Get paginated audit log for a chat."""
    count_stmt = select(func.count()).where(SettingsAuditLog.chat_id == chat_id)
    total = await session.scalar(count_stmt) or 0

    stmt = (
        select(SettingsAuditLog)
        .where(SettingsAuditLog.chat_id == chat_id)
        .order_by(SettingsAuditLog.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    result = await session.execute(stmt)
    entries = result.scalars().all()

    return entries, total
