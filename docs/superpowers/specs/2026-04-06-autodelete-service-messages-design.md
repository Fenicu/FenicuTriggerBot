# Autodelete Service Messages — Design Spec

**Date:** 2026-04-06
**Status:** Approved

## Overview

Add per-chat configurable auto-deletion of bot service messages. Chat admins can choose which message types to auto-delete and set a custom delay (1–3600 seconds) for each type independently.

## Message Types

| Key | Description | Current behavior |
|-----|------------|-----------------|
| `captcha_timeout` | "Время вышло. Пользователь был исключен" — edited captcha message after timeout kick | Stays forever (edited in place) |
| `captcha_success` | Captcha passed confirmation | Hardcoded deletion after 10s |
| `moderation` | Responses to /ban, /mute, /kick, /warn, /unban, /unmute commands | Stays forever |
| `gban` | Global ban notification on user join | Stays forever |
| `welcome` | Welcome messages for new members | Configurable via `welcome_delete_timeout` (separate field) |

## Database Schema

### New field in `Chat` model

```python
autodelete_settings = Column(JSONB, nullable=True, default=dict)
```

### JSONB structure

```json
{
  "captcha_timeout": {"enabled": true, "delay": 30},
  "captcha_success": {"enabled": true, "delay": 10},
  "moderation": {"enabled": false, "delay": 60},
  "gban": {"enabled": true, "delay": 30},
  "welcome": {"enabled": true, "delay": 120}
}
```

- Empty `{}` or missing keys = auto-deletion disabled for that type
- `enabled: false` = disabled (explicit)
- `delay`: integer, 1–3600 seconds

### Migration

- Add `autodelete_settings` JSONB column (default `{}`)
- Migrate existing `welcome_delete_timeout` values:
  - If `welcome_delete_timeout > 0`: set `autodelete_settings["welcome"] = {"enabled": true, "delay": welcome_delete_timeout}`
  - Clamp delay to 3600 if exceeds limit
- Drop `welcome_delete_timeout` column

## Backend

### Pydantic models

```python
class AutodeleteTypeConfig(BaseModel):
    enabled: bool = False
    delay: int = Field(default=30, ge=1, le=3600)

class AutodeleteSettings(BaseModel):
    captcha_timeout: AutodeleteTypeConfig | None = None
    captcha_success: AutodeleteTypeConfig | None = None
    moderation: AutodeleteTypeConfig | None = None
    gban: AutodeleteTypeConfig | None = None
    welcome: AutodeleteTypeConfig | None = None
```

### Helper function

```python
def get_autodelete_delay(chat: Chat, msg_type: str) -> int | None:
    """Return delay in seconds if auto-deletion is enabled for msg_type, else None."""
    settings = chat.autodelete_settings or {}
    config = settings.get(msg_type)
    if config and config.get("enabled"):
        return config.get("delay", 30)
    return None
```

### Handler modifications

1. **`app/bot/handlers/captcha.py`** — captcha success:
   - Replace hardcoded 10s with `get_autodelete_delay(chat, "captcha_success")`
   - If None, don't schedule deletion

2. **`app/worker/captcha.py`** — captcha timeout:
   - After editing message with timeout text, check `get_autodelete_delay(chat, "captcha_timeout")`
   - If set, publish deletion task to `q.messages.delete` with delay

3. **`app/bot/handlers/chat_moderation.py`** — /ban, /mute, /kick, /warn, /unban, /unmute:
   - After sending response, check `get_autodelete_delay(chat, "moderation")`
   - If set, publish deletion task

4. **`app/bot/handlers/chat_member.py`** — gban notification:
   - After sending gban message, check `get_autodelete_delay(chat, "gban")`
   - If set, publish deletion task

5. **`app/services/welcome_service.py`** — welcome messages:
   - Replace `welcome_delete_timeout` logic with `get_autodelete_delay(chat, "welcome")`

### API endpoint

- `GET /api/v1/chats/{chat_id}/autodelete` — return current settings
- `PUT /api/v1/chats/{chat_id}/autodelete` — update settings (requires chat admin)

Both use `AutodeleteSettings` Pydantic model for serialization/validation.

## Frontend (Webapp)

### New section in chat settings: "Автоудаление сообщений"

For each message type, display:
- Label with type name and short description
- Toggle switch (enabled/disabled)
- Number input for delay in seconds (1–3600), shown only when enabled
- Helper text showing human-readable duration (e.g., "30 сек", "2 мин")

### Message type labels (ru)

| Key | Label | Description |
|-----|-------|-------------|
| `captcha_timeout` | Капча (таймаут) | Сообщение об исключении при истечении времени капчи |
| `captcha_success` | Капча (успех) | Подтверждение успешного прохождения капчи |
| `moderation` | Модерация | Ответы на команды /ban, /mute, /kick, /warn |
| `gban` | Глобальный бан | Уведомление о глобальном бане при входе в чат |
| `welcome` | Приветствие | Приветственные сообщения для новых участников |

## Infrastructure

No changes required. Existing RabbitMQ delayed exchange (`q.messages.delete`) handles all delayed deletion.

## Migration path

1. Alembic migration: add column, migrate data, drop old column
2. Backend: add helper, modify handlers, add API endpoints
3. Frontend: add autodelete section to chat settings
4. Locales: add i18n keys for UI labels
