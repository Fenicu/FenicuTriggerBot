import React, { useEffect, useRef, useState, useCallback } from 'react';
import { chatsApi } from '../api/client';
import { toast } from '../store/store';
import type { ChatFullSettings, UpdateChatSettings } from '../types';
import {
  Settings,
  Shield,
  Gavel,
  Zap,
  Tag,
  Globe,
} from 'lucide-react';
import WelcomeEditor from './WelcomeEditor';

// ============ Props ============

interface ChatSettingsFormProps {
  chatId: number;
  isBotAdmin?: boolean;
}

// ============ Section wrapper ============

const Section = ({
  title,
  icon: Icon,
  children,
}: {
  title: string;
  icon: React.ElementType;
  children: React.ReactNode;
}) => (
  <div className="bg-section-bg rounded-xl p-4 mb-4">
    <div className="flex items-center mb-3 text-link">
      <Icon size={20} className="mr-2" />
      <h2 className="text-base font-bold m-0">{title}</h2>
    </div>
    {children}
  </div>
);

// ============ Reusable UI primitives ============

const Toggle = ({
  label,
  value,
  onChange,
}: {
  label: string;
  value: boolean;
  onChange: (v: boolean) => void;
}) => (
  <label className="flex items-center justify-between py-2 cursor-pointer">
    <span>{label}</span>
    <input
      type="checkbox"
      checked={value}
      onChange={(e) => onChange(e.target.checked)}
      className="w-5 h-5"
    />
  </label>
);

const RadioButtons = <T extends string | number>({
  options,
  value,
  onChange,
}: {
  options: { value: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
}) => (
  <div className="flex gap-2">
    {options.map((opt) => (
      <button
        key={String(opt.value)}
        className={`flex-1 py-2 rounded-lg border-none cursor-pointer text-sm font-medium ${
          value === opt.value
            ? 'bg-button text-button-text'
            : 'bg-secondary-bg text-hint'
        }`}
        onClick={() => onChange(opt.value)}
      >
        {opt.label}
      </button>
    ))}
  </div>
);

const StepperInput = ({
  value,
  onChange,
  min = 1,
  max = 10,
}: {
  value: number;
  onChange: (v: number) => void;
  min?: number;
  max?: number;
}) => (
  <div className="flex items-center gap-2">
    <button
      onClick={() => onChange(Math.max(min, value - 1))}
      className="bg-secondary-bg px-3 py-1 rounded border-none cursor-pointer text-text text-base"
    >
      &minus;
    </button>
    <span className="w-8 text-center">{value}</span>
    <button
      onClick={() => onChange(Math.min(max, value + 1))}
      className="bg-secondary-bg px-3 py-1 rounded border-none cursor-pointer text-text text-base"
    >
      +
    </button>
  </div>
);

const SelectField = <T extends string | number>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (v: T) => void;
}) => (
  <div className="flex items-center justify-between py-2">
    <span>{label}</span>
    <select
      value={String(value)}
      onChange={(e) => {
        const raw = e.target.value;
        // Restore original type
        const parsed =
          typeof value === 'number' ? (Number(raw) as T) : (raw as T);
        onChange(parsed);
      }}
      className="bg-secondary-bg text-text rounded-lg px-3 py-1.5 border-none text-sm"
    >
      {options.map((opt) => (
        <option key={String(opt.value)} value={String(opt.value)}>
          {opt.label}
        </option>
      ))}
    </select>
  </div>
);

const NumberField = ({
  label,
  value,
  onChange,
  onBlur,
  hint,
  min,
  max,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  onBlur?: () => void;
  hint?: string;
  min?: number;
  max?: number;
}) => (
  <div className="flex items-center justify-between py-2 gap-2">
    <div className="flex flex-col">
      <span>{label}</span>
      {hint && <span className="text-xs text-hint">{hint}</span>}
    </div>
    <input
      type="number"
      value={value}
      onChange={(e) => onChange(Number(e.target.value))}
      onBlur={onBlur}
      min={min}
      max={max}
      className="bg-secondary-bg text-text rounded-lg px-3 py-1.5 border-none text-sm w-24 text-right"
    />
  </div>
);

const TextField = ({
  label,
  value,
  onChange,
  onBlur,
  maxLength,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  onBlur?: () => void;
  maxLength?: number;
}) => (
  <div className="flex items-center justify-between py-2 gap-2">
    <span>{label}</span>
    <input
      type="text"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      onBlur={onBlur}
      maxLength={maxLength}
      className="bg-secondary-bg text-text rounded-lg px-3 py-1.5 border-none text-sm w-40 text-right"
    />
  </div>
);

// ============ Loading skeleton ============

const LoadingSkeleton = () => (
  <div className="space-y-4">
    {[1, 2, 3].map((i) => (
      <div key={i} className="bg-section-bg rounded-xl p-4">
        <div className="animate-pulse">
          <div className="h-5 bg-secondary-bg/50 rounded w-32 mb-4" />
          <div className="space-y-3">
            <div className="h-8 bg-secondary-bg/50 rounded" />
            <div className="h-8 bg-secondary-bg/50 rounded" />
          </div>
        </div>
      </div>
    ))}
  </div>
);

// ============ Main component ============

const ChatSettingsForm: React.FC<ChatSettingsFormProps> = ({ chatId, isBotAdmin = false }) => {
  const [settings, setSettings] = useState<ChatFullSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const settingsRef = useRef<ChatFullSettings | null>(null);

  // Keep ref in sync with state
  useEffect(() => {
    settingsRef.current = settings;
  }, [settings]);

  // ---- Fetch on mount ----

  useEffect(() => {
    const fetch = async () => {
      try {
        const data = await chatsApi.getFullSettings(chatId);
        setSettings(data);
      } catch {
        // Error toast fired by interceptor
      } finally {
        setLoading(false);
      }
    };
    fetch();
  }, [chatId]);

  // ---- Persist helper ----

  const save = useCallback(
    async (patch: UpdateChatSettings) => {
      setSaving(true);
      try {
        const updated = await chatsApi.updateFullSettings(chatId, patch);
        setSettings(updated);
        toast.success('Сохранено');
      } catch {
        // Error toast fired by interceptor
      } finally {
        setSaving(false);
      }
    },
    [chatId],
  );

  // Immediate save for boolean/select toggles
  const toggleField = useCallback(
    (field: keyof ChatFullSettings, value: boolean | string | number) => {
      if (!settings) return;
      setSettings({ ...settings, [field]: value });
      save({ [field]: value });
    },
    [settings, save],
  );

  // Local-only update (for text/number — saved on blur)
  const setLocal = useCallback(
    (field: keyof ChatFullSettings, value: unknown) => {
      if (!settings) return;
      setSettings({ ...settings, [field]: value });
    },
    [settings],
  );

  // Save a single field using ref (avoids stale closure in onBlur)
  const saveField = useCallback(
    (field: keyof ChatFullSettings) => {
      const current = settingsRef.current;
      if (current) {
        save({ [field]: current[field] });
      }
    },
    [save],
  );

  // ---- Loading ----

  if (loading) return <LoadingSkeleton />;
  if (!settings) return <div className="text-hint text-center p-8">Не удалось загрузить настройки</div>;

  // ---- Tags helpers ----

  const tagsCustom: Record<string, string> = settings.tags_custom ?? {
    '1': '',
    '2': '',
    '3': '',
    '4': '',
    '5': '',
  };
  const tagsThresholds: number[] = settings.tags_thresholds ?? [50, 200, 500, 1500, 5000];

  const setTagCustomName = (level: string, name: string) => {
    const updated = { ...tagsCustom, [level]: name };
    setSettings({ ...settings, tags_custom: updated });
  };

  const saveTagCustomNames = () => {
    save({ tags_custom: { ...tagsCustom } });
  };

  const setThreshold = (index: number, value: number) => {
    const updated = [...tagsThresholds];
    updated[index] = value;
    setSettings({ ...settings, tags_thresholds: updated });
  };

  const saveThresholds = () => {
    save({ tags_thresholds: [...tagsThresholds] });
  };

  // ---- Render ----

  return (
    <div>
      {/* Section 1: General */}
      <Section title="Общие" icon={Settings}>
        <SelectField
          label="Язык"
          value={settings.language_code}
          options={[
            { value: 'ru', label: 'Русский' },
            { value: 'en', label: 'English' },
          ]}
          onChange={(v) => toggleField('language_code', v)}
        />
        <TextField
          label="Часовой пояс"
          value={settings.timezone}
          onChange={(v) => setLocal('timezone', v)}
          onBlur={() => saveField('timezone')}
        />
      </Section>

      {/* Section 2: Captcha */}
      <Section title="Капча" icon={Shield}>
        <Toggle
          label="Включена"
          value={settings.captcha_enabled}
          onChange={(v) => toggleField('captcha_enabled', v)}
        />
        <div className="py-2">
          <span className="block mb-2">Тип</span>
          <RadioButtons
            options={[
              { value: 'emoji', label: 'Emoji' },
              { value: 'webapp', label: 'WebApp' },
            ]}
            value={settings.captcha_type}
            onChange={(v) => toggleField('captcha_type', v)}
          />
        </div>
        <SelectField
          label="Таймаут"
          value={settings.captcha_timeout}
          options={[
            { value: 60, label: '1 мин' },
            { value: 120, label: '2 мин' },
            { value: 300, label: '5 мин' },
            { value: 600, label: '10 мин' },
          ]}
          onChange={(v) => toggleField('captcha_timeout', v)}
        />
        <div className="flex items-center justify-between py-2">
          <span>Макс. попыток</span>
          <StepperInput
            value={settings.captcha_max_attempts}
            min={1}
            max={10}
            onChange={(v) => toggleField('captcha_max_attempts', v)}
          />
        </div>
        <SelectField
          label="Длительность бана"
          value={settings.captcha_ban_duration}
          options={[
            { value: 3600, label: '1 час' },
            { value: 86400, label: '1 день' },
            { value: 259200, label: '3 дня' },
          ]}
          onChange={(v) => toggleField('captcha_ban_duration', v)}
        />
      </Section>

      {/* Section 3: Moderation */}
      <Section title="Модерация" icon={Gavel}>
        <Toggle
          label="Включена"
          value={settings.module_moderation}
          onChange={(v) => toggleField('module_moderation', v)}
        />
        <div className="flex items-center justify-between py-2">
          <span>Лимит предупреждений</span>
          <StepperInput
            value={settings.warn_limit}
            min={1}
            max={10}
            onChange={(v) => toggleField('warn_limit', v)}
          />
        </div>
        <div className="py-2">
          <span className="block mb-2">Наказание</span>
          <RadioButtons
            options={[
              { value: 'ban', label: 'Бан' },
              { value: 'mute', label: 'Мут' },
            ]}
            value={settings.warn_punishment}
            onChange={(v) => toggleField('warn_punishment', v)}
          />
        </div>
        <SelectField
          label="Длительность"
          value={settings.warn_duration}
          options={[
            { value: 0, label: 'Навсегда' },
            { value: 600, label: '10 мин' },
            { value: 3600, label: '1 час' },
            { value: 86400, label: '1 день' },
            { value: 604800, label: '1 неделя' },
          ]}
          onChange={(v) => toggleField('warn_duration', v)}
        />
      </Section>

      {/* Section 4: Triggers */}
      <Section title="Триггеры" icon={Zap}>
        <Toggle
          label="Включены"
          value={settings.module_triggers}
          onChange={(v) => toggleField('module_triggers', v)}
        />
        <Toggle
          label="Только для админов"
          value={settings.admins_only_add}
          onChange={(v) => toggleField('admins_only_add', v)}
        />
      </Section>

      {/* Section 5: Tags */}
      <Section title="Теги" icon={Tag}>
        <Toggle
          label="Включены"
          value={settings.tags_enabled}
          onChange={(v) => toggleField('tags_enabled', v)}
        />

        {settings.tags_enabled && (
          <>
            <div className="py-2">
              <span className="block mb-2">Пресет</span>
              <RadioButtons
                options={[
                  { value: 'neutral', label: 'Нейтральный' },
                  { value: 'gaming', label: 'Игровой' },
                  { value: 'numeric', label: 'Числовой' },
                  { value: 'custom', label: 'Свой' },
                ]}
                value={settings.tags_preset}
                onChange={(v) => {
                  const patch: UpdateChatSettings = { tags_preset: v };
                  if (v !== 'custom') {
                    patch.tags_custom = null;
                  }
                  setSettings({ ...settings, tags_preset: v, ...(v !== 'custom' ? { tags_custom: null } : {}) });
                  save(patch);
                }}
              />
            </div>

            {settings.tags_preset !== 'custom' && (
              <div className="py-2 px-3 bg-bg rounded-lg text-sm text-hint">
                <span className="block mb-1 text-xs uppercase tracking-wide">Превью уровней:</span>
                {(() => {
                  const presets: Record<string, string[]> = {
                    neutral: ['Участник', 'Активный', 'Опытный', 'Эксперт', 'Легенда'],
                    gaming: ['Бронза', 'Серебро', 'Золото', 'Платина', 'Алмаз'],
                    numeric: ['Lv.1', 'Lv.2', 'Lv.3', 'Lv.4', 'Lv.5'],
                  };
                  const names = presets[settings.tags_preset] || presets.neutral;
                  return (
                    <div className="flex flex-wrap gap-1.5 mt-1">
                      {names.map((name, i) => (
                        <span key={i} className="bg-secondary-bg px-2 py-0.5 rounded text-text text-xs">
                          {name}
                        </span>
                      ))}
                    </div>
                  );
                })()}
              </div>
            )}

            {settings.tags_preset === 'custom' && (
              <div className="py-2 border-t border-secondary-bg mt-2 pt-3">
                <span className="block mb-2 text-hint text-sm">Названия уровней</span>
                {[1, 2, 3, 4, 5].map((level) => (
                  <TextField
                    key={level}
                    label={`Level ${level}`}
                    value={tagsCustom[String(level)] || ''}
                    onChange={(v) => setTagCustomName(String(level), v)}
                    onBlur={saveTagCustomNames}
                    maxLength={16}
                  />
                ))}
              </div>
            )}

            <div className="py-2 border-t border-secondary-bg mt-2 pt-3">
              <span className="block mb-2 text-hint text-sm">Пороги</span>
              {[0, 1, 2, 3, 4].map((i) => (
                <NumberField
                  key={i}
                  label={`Lv.${i + 1}`}
                  value={tagsThresholds[i]}
                  onChange={(v) => setThreshold(i, v)}
                  onBlur={saveThresholds}
                  min={1}
                />
              ))}
            </div>

            <div className="py-2 border-t border-secondary-bg mt-2 pt-3">
              <span className="block mb-2 text-hint text-sm">Веса</span>
              <NumberField
                label="Reactions &times;"
                value={settings.tags_weight_reactions}
                onChange={(v) => setLocal('tags_weight_reactions', v)}
                onBlur={() => saveField('tags_weight_reactions')}
                min={0}
              />
              <NumberField
                label="Replies &times;"
                value={settings.tags_weight_replies}
                onChange={(v) => setLocal('tags_weight_replies', v)}
                onBlur={() => saveField('tags_weight_replies')}
                min={0}
              />
              <NumberField
                label="Messages &times;"
                value={settings.tags_weight_messages}
                onChange={(v) => setLocal('tags_weight_messages', v)}
                onBlur={() => saveField('tags_weight_messages')}
                min={0}
              />
            </div>

            <div className="py-2 border-t border-secondary-bg mt-2 pt-3">
              <span className="block mb-2 text-hint text-sm">Антифлуд</span>
              <NumberField
                label="Сообщений/день"
                value={settings.tags_daily_message_limit}
                onChange={(v) => setLocal('tags_daily_message_limit', v)}
                onBlur={() => saveField('tags_daily_message_limit')}
                min={1}
              />
              <NumberField
                label="Реакций/день от одного"
                value={settings.tags_daily_reaction_limit}
                onChange={(v) => setLocal('tags_daily_reaction_limit', v)}
                onBlur={() => saveField('tags_daily_reaction_limit')}
                min={1}
              />
            </div>
          </>
        )}
      </Section>

      {/* Section 6: Welcome */}
      <WelcomeEditor
        chatId={chatId}
        initialMessage={settings.welcome_message}
        initialEnabled={settings.welcome_enabled}
        initialDeleteTimeout={settings.welcome_delete_timeout}
        onSave={async (data) => {
          await save(data);
        }}
      />

      {/* Section 7: Other */}
      <Section title="Прочее" icon={Globe}>
        <Toggle
          label="Глобальные баны"
          value={settings.gban_enabled}
          onChange={(v) => toggleField('gban_enabled', v)}
        />
        {isBotAdmin && (
          <Toggle
            label="Trusted Chat"
            value={settings.is_trusted}
            onChange={(v) => toggleField('is_trusted', v)}
          />
        )}
      </Section>

      {saving && (
        <div className="text-center text-hint text-sm py-2">Сохранение...</div>
      )}
    </div>
  );
};

export default ChatSettingsForm;
