import React, { useEffect, useRef, useState, useCallback } from 'react';
import { chatsApi } from '../api/client';
import { toast } from '../store/store';
import type { ChatFullSettings, UpdateChatSettings, AutodeleteTypeConfig, AutodeleteSettingsMap } from '../types';
import {
  Settings,
  Shield,
  Gavel,
  Zap,
  Tag,
  Globe,
  Trash2,
} from 'lucide-react';
import WelcomeEditor from './WelcomeEditor';
import AuditLog from './AuditLog';
import Card from './ui/Card';
import Toggle from './ui/Toggle';
import SegmentControl from './ui/SegmentControl';
import Stepper from './ui/Stepper';
import Select from './ui/Select';
import TextInput from './ui/TextInput';
import Badge from './ui/Badge';

// ============ Props ============

interface ChatSettingsFormProps {
  chatId: number;
  isBotAdmin?: boolean;
}

// ============ Tag presets ============

const presets: Record<string, string[]> = {
  neutral: ['Участник', 'Активный', 'Опытный', 'Эксперт', 'Легенда'],
  gaming: ['Бронза', 'Серебро', 'Золото', 'Платина', 'Алмаз'],
  numeric: ['Lv.1', 'Lv.2', 'Lv.3', 'Lv.4', 'Lv.5'],
};

// ============ Loading skeleton ============

const LoadingSkeleton = () => (
  <div className="space-y-3">
    {[1, 2, 3].map((i) => (
      <div key={i} className="bg-surface border border-border rounded-[14px] p-4">
        <div className="animate-pulse">
          <div className="h-5 bg-elevated rounded w-32 mb-4" />
          <div className="space-y-3">
            <div className="h-8 bg-elevated rounded" />
            <div className="h-8 bg-elevated rounded" />
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
    (field: keyof ChatFullSettings, value: boolean | string | number | string[] | null) => {
      if (!settings) return;
      setSettings({ ...settings, [field]: value });
      save({ [field]: value } as Partial<ChatFullSettings>);
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

  // ---- Section lock helpers ----

  const toggleSectionLock = useCallback((section: string) => {
    if (!settings) return;
    const current = settings.settings_locked_sections || [];
    const updated = current.includes(section)
      ? current.filter(s => s !== section)
      : [...current, section];
    toggleField('settings_locked_sections', updated);
  }, [settings, toggleField]);

  const isSectionLocked = (section: string) => {
    if (!settings || settings.is_creator) return false;
    return (settings.settings_locked_sections || []).includes(section);
  };

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

  // ---- Render ----

  return (
    <div>
      {/* Section 1: General */}
      <Card
        icon={Settings}
        title="Общие"
        lock={{
          locked: (settings.settings_locked_sections || []).includes('general'),
          onToggle: () => toggleSectionLock('general'),
          visible: settings.is_creator,
        }}
        disabled={isSectionLocked('general')}
      >
        <Select
          label="Язык"
          value={settings.language_code}
          options={[
            { value: 'ru', label: 'Русский' },
            { value: 'en', label: 'English' },
          ]}
          onChange={(v) => toggleField('language_code', v)}
        />
        <TextInput
          label="Часовой пояс"
          value={settings.timezone}
          onChange={(v) => setLocal('timezone', v)}
          onBlur={() => saveField('timezone')}
        />
      </Card>

      {/* Section 2: Captcha */}
      <Card
        icon={Shield}
        title="Капча"
        toggle={{ value: settings.captcha_enabled, onChange: (v) => toggleField('captcha_enabled', v) }}
        lock={{
          locked: (settings.settings_locked_sections || []).includes('captcha'),
          onToggle: () => toggleSectionLock('captcha'),
          visible: settings.is_creator,
        }}
        disabled={isSectionLocked('captcha')}
      >
        <div className="mb-2.5">
          <div className="text-xs text-hint mb-1.5">Тип</div>
          <SegmentControl
            options={[{ value: 'emoji', label: 'Emoji' }, { value: 'webapp', label: 'WebApp' }]}
            value={settings.captcha_type}
            onChange={(v) => toggleField('captcha_type', v)}
          />
        </div>
        <Select
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
          <div><span className="text-[14px] font-medium">Макс. попыток</span></div>
          <Stepper value={settings.captcha_max_attempts} min={1} max={10} onChange={(v) => toggleField('captcha_max_attempts', v)} />
        </div>
        <Select
          label="Длительность бана"
          value={settings.captcha_ban_duration}
          options={[
            { value: 3600, label: '1 час' },
            { value: 86400, label: '1 день' },
            { value: 259200, label: '3 дня' },
          ]}
          onChange={(v) => toggleField('captcha_ban_duration', v)}
        />
      </Card>

      {/* Section 3: Moderation */}
      <Card
        icon={Gavel}
        title="Модерация"
        toggle={{ value: settings.module_moderation, onChange: (v) => toggleField('module_moderation', v) }}
        lock={{
          locked: (settings.settings_locked_sections || []).includes('moderation'),
          onToggle: () => toggleSectionLock('moderation'),
          visible: settings.is_creator,
        }}
        disabled={isSectionLocked('moderation')}
      >
        <div className="flex items-center justify-between py-2">
          <div><span className="text-[14px] font-medium">Лимит предупреждений</span></div>
          <Stepper value={settings.warn_limit} min={1} max={10} onChange={(v) => toggleField('warn_limit', v)} />
        </div>
        <div className="py-2">
          <div className="text-xs text-hint mb-1.5">Наказание</div>
          <SegmentControl
            options={[{ value: 'ban', label: 'Бан' }, { value: 'mute', label: 'Мут' }]}
            value={settings.warn_punishment}
            onChange={(v) => toggleField('warn_punishment', v)}
          />
        </div>
        <Select
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
      </Card>

      {/* Section 4: Triggers */}
      <Card
        icon={Zap}
        title="Триггеры"
        toggle={{ value: settings.module_triggers, onChange: (v) => toggleField('module_triggers', v) }}
        lock={{
          locked: (settings.settings_locked_sections || []).includes('triggers'),
          onToggle: () => toggleSectionLock('triggers'),
          visible: settings.is_creator,
        }}
        disabled={isSectionLocked('triggers')}
      >
        <Toggle label="Только для админов" value={settings.admins_only_add} onChange={(v) => toggleField('admins_only_add', v)} />
      </Card>

      {/* Section 5: Tags */}
      <Card
        icon={Tag}
        title="Теги"
        lock={{
          locked: (settings.settings_locked_sections || []).includes('tags'),
          onToggle: () => toggleSectionLock('tags'),
          visible: settings.is_creator,
        }}
        disabled={isSectionLocked('tags')}
      >
        <Toggle label="Включены" value={settings.tags_enabled} onChange={(v) => toggleField('tags_enabled', v)} />

        {settings.tags_enabled && (
          <>
            <div className="py-2">
              <div className="text-xs text-hint mb-1.5">Пресет</div>
              <SegmentControl
                options={[
                  { value: 'neutral', label: 'Нейтральный' },
                  { value: 'gaming', label: 'Игровой' },
                  { value: 'numeric', label: 'Числовой' },
                  { value: 'custom', label: 'Свой' },
                ]}
                value={settings.tags_preset}
                onChange={(v) => {
                  const patch: UpdateChatSettings = { tags_preset: v };
                  if (v !== 'custom') patch.tags_custom = null;
                  setSettings({ ...settings, tags_preset: v, ...(v !== 'custom' ? { tags_custom: null } : {}) });
                  save(patch);
                }}
              />
            </div>

            {/* Preset preview */}
            {settings.tags_preset !== 'custom' && (
              <div className="py-2 px-3 bg-elevated rounded-[10px] text-sm">
                <span className="block mb-1.5 text-[10px] text-hint uppercase tracking-wider">Превью уровней</span>
                <div className="flex flex-wrap gap-1.5">
                  {(presets[settings.tags_preset] || presets.neutral).map((name, i) => (
                    <Badge key={i} variant="blue">{name}</Badge>
                  ))}
                </div>
              </div>
            )}

            {/* Custom tag names */}
            {settings.tags_preset === 'custom' && (
              <div className="py-2 border-t border-border mt-2 pt-3">
                <span className="block mb-2 text-hint text-sm">Названия уровней</span>
                {[1, 2, 3, 4, 5].map((level) => (
                  <TextInput
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

            {/* Thresholds */}
            <div className="py-2 border-t border-border mt-2 pt-3">
              <span className="block mb-2 text-hint text-sm">Пороги</span>
              {[0, 1, 2, 3, 4].map((i) => (
                <TextInput
                  key={i}
                  type="number"
                  label={`Lv.${i + 1}`}
                  value={String(tagsThresholds[i])}
                  onChange={(v) => setThreshold(i, Number(v))}
                  onBlur={saveThresholds}
                  min={1}
                />
              ))}
            </div>

            {/* Weights */}
            <div className="py-2 border-t border-border mt-2 pt-3">
              <span className="block mb-2 text-hint text-sm">Веса</span>
              <TextInput type="number" label="Reactions &times;" value={String(settings.tags_weight_reactions)} onChange={(v) => setLocal('tags_weight_reactions', Number(v))} onBlur={() => saveField('tags_weight_reactions')} min={0} />
              <TextInput type="number" label="Replies &times;" value={String(settings.tags_weight_replies)} onChange={(v) => setLocal('tags_weight_replies', Number(v))} onBlur={() => saveField('tags_weight_replies')} min={0} />
              <TextInput type="number" label="Messages &times;" value={String(settings.tags_weight_messages)} onChange={(v) => setLocal('tags_weight_messages', Number(v))} onBlur={() => saveField('tags_weight_messages')} min={0} />
            </div>

            {/* Anti-flood */}
            <div className="py-2 border-t border-border mt-2 pt-3">
              <span className="block mb-2 text-hint text-sm">Антифлуд</span>
              <TextInput type="number" label="Сообщений/день" value={String(settings.tags_daily_message_limit)} onChange={(v) => setLocal('tags_daily_message_limit', Number(v))} onBlur={() => saveField('tags_daily_message_limit')} min={1} />
              <TextInput type="number" label="Реакций/день от одного" value={String(settings.tags_daily_reaction_limit)} onChange={(v) => setLocal('tags_daily_reaction_limit', Number(v))} onBlur={() => saveField('tags_daily_reaction_limit')} min={1} />
            </div>
          </>
        )}
      </Card>

      {/* Section 6: Welcome */}
      <WelcomeEditor
        chatId={chatId}
        initialMessage={settings.welcome_message}
        initialEnabled={settings.welcome_enabled}
        onSave={async (data) => {
          await save(data);
        }}
      />

      {/* Section 7: Autodelete */}
      <Card
        icon={Trash2}
        title="Автоудаление сообщений"
        lock={{
          locked: (settings.settings_locked_sections || []).includes('autodelete'),
          onToggle: () => toggleSectionLock('autodelete'),
          visible: settings.is_creator,
        }}
        disabled={isSectionLocked('autodelete')}
      >
        <p className="text-hint text-xs mb-3">
          Автоматически удалять сервисные сообщения бота через заданное время
        </p>
        {AUTODELETE_TYPES.map(({ key, label, hint }) => {
          const config = autodeleteSettings[key] ?? { enabled: false, delay: 30 };
          return (
            <div key={key} className="py-2 border-b border-border last:border-b-0">
              <div className="flex items-center justify-between">
                <div className="flex flex-col">
                  <span className="text-sm">{label}</span>
                  <span className="text-xs text-hint">{hint}</span>
                </div>
                <Toggle
                  value={config.enabled}
                  onChange={(v) => updateAutodelete(key, { ...config, enabled: v })}
                />
              </div>
              {config.enabled && (
                <div className="flex items-center gap-2 mt-2">
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
                    className="bg-elevated text-text border border-border rounded-[10px] px-3 py-1.5 text-sm w-20 text-right outline-none focus:border-button transition-colors"
                  />
                  <span className="text-xs text-hint">{formatDelay(config.delay)}</span>
                </div>
              )}
            </div>
          );
        })}
      </Card>

      {/* Section 8: Other */}
      <Card
        icon={Globe}
        title="Прочее"
        lock={{
          locked: (settings.settings_locked_sections || []).includes('other'),
          onToggle: () => toggleSectionLock('other'),
          visible: settings.is_creator,
        }}
        disabled={isSectionLocked('other')}
      >
        <Toggle label="Глобальные баны" value={settings.gban_enabled} onChange={(v) => toggleField('gban_enabled', v)} />
        {isBotAdmin && (
          <Toggle label="Trusted Chat" value={settings.is_trusted} onChange={(v) => toggleField('is_trusted', v)} />
        )}
      </Card>

      <AuditLog chatId={chatId} />

      {saving && (
        <div className="text-center text-hint text-sm py-2">Сохранение...</div>
      )}
    </div>
  );
};

export default ChatSettingsForm;
