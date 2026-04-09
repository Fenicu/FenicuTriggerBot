# Autodelete Service Messages — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-chat configurable auto-deletion of bot service messages (captcha, moderation, gban, welcome) with per-type enable/disable and delay (1–3600s).

**Architecture:** New JSONB column `autodelete_settings` in the Chat model stores per-type `{enabled, delay}` config. A shared helper `schedule_autodelete` publishes to the existing RabbitMQ delayed exchange. Each handler calls this helper after sending its service message. The webapp gets a new "Autodelete" section in ChatSettingsForm. The existing `welcome_delete_timeout` field is migrated into the new JSONB and dropped.

**Tech Stack:** Python 3.12, SQLAlchemy 2 (async), Alembic, FastAPI, aiogram 3, FastStream (RabbitMQ), React 18, TypeScript, Tailwind CSS.

---

## File Map

| Action | File | Responsibility |
|--------|------|---------------|
| Modify | `app/db/models/chat.py` | Add `autodelete_settings` column |
| Create | `app/db/migrations/versions/xxxx_add_autodelete_settings.py` | Migration: add column, migrate welcome data, drop old column |
| Modify | `app/schemas/chat_settings.py` | Add `AutodeleteTypeConfig`, `AutodeleteSettings` schemas; update response/request |
| Modify | `app/services/audit_service.py` | Add `autodelete_settings` to FIELD_SECTION_MAP |
| Modify | `app/services/welcome_service.py` | Replace `welcome_delete_timeout` with autodelete helper |
| Modify | `app/bot/handlers/captcha.py` | Use autodelete helper for captcha success |
| Modify | `app/worker/captcha.py` | Schedule deletion for captcha timeout message |
| Modify | `app/bot/handlers/chat_moderation.py` | Schedule deletion for moderation command responses |
| Modify | `app/bot/handlers/chat_member.py` | Schedule deletion for gban notification |
| Modify | `frontend/src/types/index.ts` | Add `AutodeleteTypeConfig`, `autodelete_settings` to types |
| Modify | `frontend/src/components/ChatSettingsForm.tsx` | Add Autodelete section UI |

---

### Task 1: Database — Add `autodelete_settings` column to Chat model

**Files:**
- Modify: `app/db/models/chat.py:46` (after `welcome_delete_timeout`)

- [ ] **Step 1: Add the `autodelete_settings` column and remove `welcome_delete_timeout`**

In `app/db/models/chat.py`, replace line 46:

```python
welcome_delete_timeout: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
```

with:

```python
autodelete_settings: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=dict)
```

- [ ] **Step 2: Generate and edit the Alembic migration**

Run:
```bash
cd /home/fenicu/myprojects/trigger && alembic revision --autogenerate -m "add autodelete_settings and migrate welcome_delete_timeout"
```

Then edit the generated migration file to add data migration logic. The `upgrade()` should be:

```python
def upgrade() -> None:
    # 1. Add new column
    op.add_column('chats', sa.Column('autodelete_settings', postgresql.JSONB(astext_type=sa.Text()), nullable=True))

    # 2. Migrate welcome_delete_timeout data
    op.execute("""
        UPDATE chats
        SET autodelete_settings = jsonb_build_object(
            'welcome', jsonb_build_object(
                'enabled', true,
                'delay', LEAST(welcome_delete_timeout, 3600)
            )
        )
        WHERE welcome_delete_timeout > 0
    """)

    # 3. Drop old column
    op.drop_column('chats', 'welcome_delete_timeout')
```

The `downgrade()` should be:

```python
def downgrade() -> None:
    op.add_column('chats', sa.Column('welcome_delete_timeout', sa.Integer(), server_default='0', nullable=False))

    op.execute("""
        UPDATE chats
        SET welcome_delete_timeout = COALESCE(
            (autodelete_settings->'welcome'->>'delay')::int,
            0
        )
        WHERE autodelete_settings IS NOT NULL
          AND autodelete_settings->'welcome' IS NOT NULL
          AND (autodelete_settings->'welcome'->>'enabled')::boolean = true
    """)

    op.drop_column('chats', 'autodelete_settings')
```

- [ ] **Step 3: Verify migration applies cleanly**

Run:
```bash
cd /home/fenicu/myprojects/trigger && alembic upgrade head
```

Expected: migration applies with no errors.

- [ ] **Step 4: Commit**

```bash
git add app/db/models/chat.py app/db/migrations/versions/*autodelete*
git commit -m "feat: add autodelete_settings JSONB column, migrate welcome_delete_timeout"
```

---

### Task 2: Backend — Pydantic schemas and helper function

**Files:**
- Modify: `app/schemas/chat_settings.py`
- Modify: `app/services/audit_service.py`

- [ ] **Step 1: Add Pydantic models and update schemas**

In `app/schemas/chat_settings.py`, add these classes before `ChatFullSettingsResponse`:

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

Add `Field` to the pydantic imports at line 4:

```python
from pydantic import BaseModel, ConfigDict, Field, field_validator
```

In `ChatFullSettingsResponse`, replace:
```python
    # Welcome
    welcome_enabled: bool
    welcome_delete_timeout: int
    welcome_message: dict | None = None
```

with:
```python
    # Welcome
    welcome_enabled: bool
    welcome_message: dict | None = None

    # Autodelete
    autodelete_settings: dict | None = None
```

In `UpdateChatFullSettingsRequest`, replace:
```python
    # Welcome
    welcome_enabled: bool | None = None
    welcome_delete_timeout: int | None = None
    welcome_message: dict | None = None
```

with:
```python
    # Welcome
    welcome_enabled: bool | None = None
    welcome_message: dict | None = None

    # Autodelete
    autodelete_settings: dict | None = None
```

Add a validator for `autodelete_settings` in `UpdateChatFullSettingsRequest`:

```python
    @field_validator("autodelete_settings")
    @classmethod
    def validate_autodelete(cls, v: dict | None) -> dict | None:
        if v is None:
            return v
        valid_keys = {"captcha_timeout", "captcha_success", "moderation", "gban", "welcome"}
        for key, config in v.items():
            if key not in valid_keys:
                raise ValueError(f"Unknown autodelete type: {key}")
            if not isinstance(config, dict):
                raise ValueError(f"autodelete config for '{key}' must be a dict")
            if "enabled" not in config or not isinstance(config["enabled"], bool):
                raise ValueError(f"autodelete config for '{key}' must have 'enabled' (bool)")
            if "delay" in config:
                delay = config["delay"]
                if not isinstance(delay, int) or delay < 1 or delay > 3600:
                    raise ValueError(f"autodelete delay for '{key}' must be int 1-3600")
        return v
```

- [ ] **Step 2: Update audit service**

In `app/services/audit_service.py`, add to `FIELD_SECTION_MAP`:

```python
    "autodelete_settings": "autodelete",
```

Add `"autodelete"` to `VALID_SECTIONS`:

```python
VALID_SECTIONS = {"general", "captcha", "moderation", "triggers", "tags", "welcome", "other", "autodelete"}
```

- [ ] **Step 3: Commit**

```bash
git add app/schemas/chat_settings.py app/services/audit_service.py
git commit -m "feat: add autodelete Pydantic schemas and audit section"
```

---

### Task 3: Backend — Autodelete helper and handler integrations

**Files:**
- Modify: `app/services/welcome_service.py`
- Modify: `app/bot/handlers/captcha.py`
- Modify: `app/worker/captcha.py`
- Modify: `app/bot/handlers/chat_moderation.py`
- Modify: `app/bot/handlers/chat_member.py`

- [ ] **Step 1: Add `schedule_autodelete` helper to broker module**

This avoids importing from core.broker everywhere with repetitive publish logic. Add at the end of `app/core/broker.py`:

```python
from app.db.models.chat import Chat


def get_autodelete_delay(chat: Chat, msg_type: str) -> int | None:
    """Return delay in seconds if auto-deletion is enabled for msg_type, else None."""
    settings = chat.autodelete_settings or {}
    config = settings.get(msg_type)
    if config and config.get("enabled"):
        return config.get("delay", 30)
    return None


async def schedule_autodelete(chat: Chat, msg_type: str, chat_id: int, message_id: int) -> None:
    """Publish a delayed message-deletion task if autodelete is configured for msg_type."""
    delay = get_autodelete_delay(chat, msg_type)
    if delay is None:
        return
    await broker.publish(
        message={"chat_id": chat_id, "message_id": message_id},
        exchange=delayed_exchange,
        routing_key="q.messages.delete",
        headers={"x-delay": delay * 1000},
    )
```

- [ ] **Step 2: Update `welcome_service.py`**

In `app/services/welcome_service.py`, replace the import line 9:
```python
from app.core.broker import broker, delayed_exchange
```
with:
```python
from app.core.broker import schedule_autodelete
```

Replace lines 112-118:
```python
        if db_chat.welcome_delete_timeout > 0 and sent_msg:
            await broker.publish(
                message={"chat_id": chat.id, "message_id": sent_msg.message_id},
                exchange=delayed_exchange,
                routing_key="q.messages.delete",
                headers={"x-delay": db_chat.welcome_delete_timeout * 1000},
            )
```

with:
```python
        if sent_msg:
            await schedule_autodelete(db_chat, "welcome", chat.id, sent_msg.message_id)
```

- [ ] **Step 3: Update `captcha.py` handler (captcha success)**

In `app/bot/handlers/captcha.py`, add import at line 18:
```python
from app.core.broker import broker, delayed_exchange, schedule_autodelete
```
(Replace the existing `from app.core.broker import broker, delayed_exchange`)

In `_handle_success`, replace lines 123-128:
```python
            await broker.publish(
                message={"chat_id": chat.id, "message_id": sent_msg.message_id},
                exchange=delayed_exchange,
                routing_key="q.messages.delete",
                headers={"x-delay": 10000},
            )
```

with:
```python
            if db_chat:
                await schedule_autodelete(db_chat, "captcha_success", chat.id, sent_msg.message_id)
```

- [ ] **Step 4: Update `worker/captcha.py` (captcha timeout)**

In `app/worker/captcha.py`, add imports:
```python
from app.core.broker import delayed_exchange as core_delayed_exchange, schedule_autodelete
from app.db.models.chat import Chat
```

After the `edit_message_text` call (line 64-68), add auto-deletion scheduling. Replace the inner try block (lines 60-70):

```python
            try:
                lang_code = await valkey.get(f"lang:{chat_id}")
                i18n = translator_hub.get_translator_by_locale(lang_code or ROOT_LOCALE)

                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=captcha_session.message_id,
                    text=i18n.captcha.timeout.kick(),
                )

                # Schedule auto-deletion if configured
                db_chat = await session.get(Chat, chat_id)
                if db_chat:
                    await schedule_autodelete(
                        db_chat, "captcha_timeout", chat_id, captcha_session.message_id
                    )
            except TelegramBadRequest as e:
                logger.warning(f"Failed to edit message: {e}")
```

- [ ] **Step 5: Update `chat_moderation.py` (moderation commands)**

In `app/bot/handlers/chat_moderation.py`, add import:
```python
from app.core.broker import schedule_autodelete
```

In `cmd_ban`, replace line 72-79:
```python
        await message.answer(
            i18n.mod.user.banned(
                user=html.quote(user_name),
                reason=reason or "—",
                date=until_date or "∞",
            ),
            parse_mode="HTML",
        )
```

with:
```python
        sent = await message.answer(
            i18n.mod.user.banned(
                user=html.quote(user_name),
                reason=reason or "—",
                date=until_date or "∞",
            ),
            parse_mode="HTML",
        )
        await schedule_autodelete(db_chat, "moderation", message.chat.id, sent.message_id)
```

Note: `cmd_ban` needs `db_chat` — add it to the function signature:
```python
async def cmd_ban(message: Message, command: CommandObject, db_chat: Chat, i18n: TranslatorRunner) -> None:
```

Apply the same pattern to `cmd_mute` (line 104-111), `cmd_unban` (line 136), `cmd_unmute` (line 160), `cmd_kick` (line 181), and `cmd_warn` (lines 210-218, 235-241).

For each command:
1. Add `db_chat: Chat` to function signature (if not already present)
2. Capture the return value of `message.answer(...)` as `sent`
3. Add `await schedule_autodelete(db_chat, "moderation", message.chat.id, sent.message_id)` after

Full list of modifications:

**`cmd_ban` (line 56):** Change signature to add `db_chat: Chat`:
```python
async def cmd_ban(message: Message, command: CommandObject, db_chat: Chat, i18n: TranslatorRunner) -> None:
```

**`cmd_mute` (line 85):** Change signature to add `db_chat: Chat`:
```python
async def cmd_mute(message: Message, command: CommandObject, db_chat: Chat, i18n: TranslatorRunner) -> None:
```

**`cmd_unban` (line 117):** Change signature to add `db_chat: Chat`:
```python
async def cmd_unban(message: Message, command: CommandObject, db_chat: Chat, i18n: TranslatorRunner) -> None:
```

**`cmd_unmute` (line 142):** Change signature to add `db_chat: Chat`:
```python
async def cmd_unmute(message: Message, db_chat: Chat, i18n: TranslatorRunner) -> None:
```

**`cmd_kick` (line 166):** Change signature to add `db_chat: Chat`:
```python
async def cmd_kick(message: Message, db_chat: Chat, i18n: TranslatorRunner) -> None:
```

For each handler, capture the sent message and schedule deletion:
```python
        sent = await message.answer(...)
        await schedule_autodelete(db_chat, "moderation", message.chat.id, sent.message_id)
```

For `cmd_warn`, two messages may be sent (warn added + punishment applied). Schedule deletion for both:
- Line 210: `sent = await message.answer(i18n.mod.warn.added(...))`  then `await schedule_autodelete(db_chat, "moderation", message.chat.id, sent.message_id)`
- Line 235: `sent = await message.answer(i18n.mod.warn.reset(...))`  then `await schedule_autodelete(db_chat, "moderation", message.chat.id, sent.message_id)`

- [ ] **Step 6: Update `chat_member.py` (gban notification)**

In `app/bot/handlers/chat_member.py`, add import:
```python
from app.core.broker import broker, delayed_exchange, schedule_autodelete
```
(Replace existing `from app.core.broker import broker, delayed_exchange`)

Replace lines 94-98:
```python
            await bot.send_message(
                chat.id,
                i18n.gban.user.banned(user=user.mention_html()),
                parse_mode="HTML",
            )
```

with:
```python
            sent = await bot.send_message(
                chat.id,
                i18n.gban.user.banned(user=user.mention_html()),
                parse_mode="HTML",
            )
            await schedule_autodelete(db_chat, "gban", chat.id, sent.message_id)
```

- [ ] **Step 7: Commit**

```bash
git add app/core/broker.py app/services/welcome_service.py app/bot/handlers/captcha.py app/worker/captcha.py app/bot/handlers/chat_moderation.py app/bot/handlers/chat_member.py
git commit -m "feat: integrate autodelete into all service message handlers"
```

---

### Task 4: Frontend — Types and API

**Files:**
- Modify: `frontend/src/types/index.ts`

- [ ] **Step 1: Update TypeScript types**

In `frontend/src/types/index.ts`, add before `ChatFullSettings`:

```typescript
export interface AutodeleteTypeConfig {
  enabled: boolean;
  delay: number;
}

export interface AutodeleteSettingsMap {
  captcha_timeout?: AutodeleteTypeConfig;
  captcha_success?: AutodeleteTypeConfig;
  moderation?: AutodeleteTypeConfig;
  gban?: AutodeleteTypeConfig;
  welcome?: AutodeleteTypeConfig;
}
```

In `ChatFullSettings`, replace:
```typescript
  // Welcome
  welcome_enabled: boolean;
  welcome_delete_timeout: number;
  welcome_message: WelcomeMessage | null;
```

with:
```typescript
  // Welcome
  welcome_enabled: boolean;
  welcome_message: WelcomeMessage | null;

  // Autodelete
  autodelete_settings: AutodeleteSettingsMap | null;
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/types/index.ts
git commit -m "feat: add autodelete TypeScript types"
```

---

### Task 5: Frontend — Autodelete settings section in ChatSettingsForm

**Files:**
- Modify: `frontend/src/components/ChatSettingsForm.tsx`
- Modify: `frontend/src/components/WelcomeEditor.tsx`

- [ ] **Step 1: Add Autodelete section to ChatSettingsForm**

In `frontend/src/components/ChatSettingsForm.tsx`, add the `Trash2` icon to lucide imports (line 14):
```typescript
import {
  Settings,
  Shield,
  Gavel,
  Zap,
  Tag,
  Globe,
  Lock,
  Unlock,
  Trash2,
} from 'lucide-react';
```

Add import of the type:
```typescript
import type { ChatFullSettings, UpdateChatSettings, AutodeleteTypeConfig, AutodeleteSettingsMap } from '../types';
```

Add this helper function inside the component, after `saveThresholds` (around line 380):

```typescript
  // ---- Autodelete helpers ----

  const AUTODELETE_TYPES: { key: keyof AutodeleteSettingsMap; label: string; hint: string }[] = [
    { key: 'captcha_timeout', label: 'Капча (таймаут)', hint: 'Сообщение об исключении при истечении капчи' },
    { key: 'captcha_success', label: 'Капча (успех)', hint: 'Подтверждение успешного прохождения капчи' },
    { key: 'moderation', label: 'Модерация', hint: 'Ответы на /ban, /mute, /kick, /warn' },
    { key: 'gban', label: 'Глобальный бан', hint: 'Уведомление о глобальном бане' },
    { key: 'welcome', label: 'Приветствие', hint: 'Приветственные сообщения для новых участников' },
  ];

  const autodeleteSettings: AutodeleteSettingsMap = settings.autodelete_settings ?? {};

  const formatDelay = (seconds: number): string => {
    if (seconds < 60) return `${seconds} сек`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)} мин`;
    return '1 час';
  };

  const updateAutodelete = (key: keyof AutodeleteSettingsMap, config: AutodeleteTypeConfig) => {
    const updated = { ...autodeleteSettings, [key]: config };
    setSettings({ ...settings, autodelete_settings: updated });
    save({ autodelete_settings: updated });
  };

  const setAutodeleteLocal = (key: keyof AutodeleteSettingsMap, config: AutodeleteTypeConfig) => {
    const updated = { ...autodeleteSettings, [key]: config };
    setSettings({ ...settings, autodelete_settings: updated });
  };

  const saveAutodelete = () => {
    const current = settingsRef.current;
    if (current) {
      save({ autodelete_settings: current.autodelete_settings ?? {} });
    }
  };
```

Add the Autodelete section JSX after the Welcome section (after line 659) and before the "Other" section:

```tsx
      {/* Section 7: Autodelete */}
      <Section title="Автоудаление сообщений" icon={Trash2} extra={<SectionLock section="autodelete" settings={settings} onToggle={toggleSectionLock} />}>
        <div className={isSectionLocked('autodelete') ? 'opacity-50 pointer-events-none' : ''}>
          <p className="text-hint text-xs mb-3">
            Автоматически удалять сервисные сообщения бота через заданное время
          </p>
          {AUTODELETE_TYPES.map(({ key, label, hint }) => {
            const config = autodeleteSettings[key] ?? { enabled: false, delay: 30 };
            return (
              <div key={key} className="py-2 border-b border-secondary-bg last:border-b-0">
                <div className="flex items-center justify-between">
                  <div className="flex flex-col">
                    <span className="text-sm">{label}</span>
                    <span className="text-xs text-hint">{hint}</span>
                  </div>
                  <input
                    type="checkbox"
                    checked={config.enabled}
                    onChange={(e) => updateAutodelete(key, { ...config, enabled: e.target.checked })}
                    className="w-5 h-5"
                  />
                </div>
                {config.enabled && (
                  <div className="flex items-center gap-2 mt-2 ml-0">
                    <span className="text-xs text-hint">Задержка:</span>
                    <input
                      type="number"
                      value={config.delay}
                      min={1}
                      max={3600}
                      onChange={(e) => {
                        const val = Math.max(1, Math.min(3600, Number(e.target.value) || 1));
                        setAutodeleteLocal(key, { ...config, delay: val });
                      }}
                      onBlur={saveAutodelete}
                      className="bg-secondary-bg text-text rounded-lg px-3 py-1 border-none text-sm w-20 text-right"
                    />
                    <span className="text-xs text-hint">{formatDelay(config.delay)}</span>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </Section>
```

- [ ] **Step 2: Update WelcomeEditor to remove `welcome_delete_timeout`**

In `frontend/src/components/WelcomeEditor.tsx`, remove the `initialDeleteTimeout` prop from the interface and all references. The `welcome_delete_timeout` is now managed through the autodelete section.

Update the `WelcomeEditorProps` interface:
```typescript
interface WelcomeEditorProps {
  chatId: number;
  initialMessage: WelcomeMessage | null;
  initialEnabled: boolean;
  onSave: (data: {
    welcome_message: WelcomeMessage | null;
    welcome_enabled: boolean;
  }) => Promise<void>;
}
```

Remove the `deleteTimeout` state and all its usages. The `onSave` call should no longer include `welcome_delete_timeout`.

In `ChatSettingsForm.tsx`, update the WelcomeEditor invocation (around line 651):
```tsx
      <WelcomeEditor
        chatId={chatId}
        initialMessage={settings.welcome_message}
        initialEnabled={settings.welcome_enabled}
        onSave={async (data) => {
          await save(data);
        }}
      />
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/ChatSettingsForm.tsx frontend/src/components/WelcomeEditor.tsx
git commit -m "feat: add autodelete settings section in webapp"
```

---

### Task 6: Integration test and cleanup

**Files:**
- Verify: all modified files

- [ ] **Step 1: Verify the full build**

```bash
cd /home/fenicu/myprojects/trigger/frontend && npm run build
```

Expected: build succeeds with no TypeScript errors.

- [ ] **Step 2: Verify Python imports**

```bash
cd /home/fenicu/myprojects/trigger && python -c "
from app.db.models.chat import Chat
from app.schemas.chat_settings import ChatFullSettingsResponse, UpdateChatFullSettingsRequest, AutodeleteTypeConfig, AutodeleteSettings
from app.core.broker import get_autodelete_delay, schedule_autodelete
print('All imports OK')
"
```

Expected: "All imports OK"

- [ ] **Step 3: Check for any remaining references to `welcome_delete_timeout`**

```bash
cd /home/fenicu/myprojects/trigger && grep -r "welcome_delete_timeout" --include="*.py" --include="*.ts" --include="*.tsx" .
```

Expected: no matches (all references should be removed).

- [ ] **Step 4: Final commit (if any remaining fixes)**

```bash
git add -A
git commit -m "chore: cleanup remaining welcome_delete_timeout references"
```
