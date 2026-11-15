import React from 'react';
import type { WelcomeButton } from '../types';
import { sanitizeHtml } from '../lib/sanitizeHtml';
import { formatDate, formatTime } from '../lib/dateFormat';

interface WelcomePreviewProps {
  text: string;
  media: { file_id: string; file_type: 'photo' | 'video' | 'animation' } | null;
  buttons: WelcomeButton[][];
  isTemplate: boolean;
  richMode?: boolean;
}

function replaceTemplateVars(text: string): string {
  const now = new Date();
  return text
    .replace(/\{\{\s*user\.mention\s*\}\}/g, '<b>@username</b>')
    .replace(/\{\{\s*user\.full_name\s*\}\}/g, 'Имя Пользователя')
    .replace(/\{\{\s*chat\.title\s*\}\}/g, 'Название чата')
    .replace(/\{\{\s*date\s*\}\}/g, formatDate(now))
    .replace(/\{\{\s*time\s*\}\}/g, formatTime(now));
}

const MEDIA_ICONS: Record<string, string> = {
  photo: '📷',
  video: '🎬',
  animation: '🎞',
};

const WelcomePreview: React.FC<WelcomePreviewProps> = ({ text, media, buttons, isTemplate, richMode = false }) => {
  const filteredButtons = buttons.filter(row => row.some(btn => btn.text));

  let displayText = text;
  if (isTemplate) {
    displayText = replaceTemplateVars(displayText);
  }
  const sanitized = sanitizeHtml(displayText, richMode);

  const hasContent = !!sanitized.trim() || !!media || filteredButtons.length > 0;

  return (
    <div className="bg-surface rounded-xl p-4">
      <div className="text-hint text-xs uppercase tracking-wide mb-3">Предпросмотр</div>
      <div className="bg-[#0d1117] rounded-xl p-4 min-h-32">
        {hasContent ? (
          <div style={{ maxWidth: '90%' }}>
            {/* message bubble */}
            <div
              className="rounded-xl rounded-bl-sm overflow-hidden"
              style={{
                background: '#2b5278',
                borderRadius: '12px 12px 12px 4px',
              }}
            >
              {media && (
                <div className="bg-black/20 rounded-t-xl p-8 text-center text-3xl">
                  {MEDIA_ICONS[media.file_type] ?? '📎'}
                </div>
              )}
              {sanitized.trim() && (
                <div
                  className={`px-3 py-2 text-white text-sm${richMode ? ' rich-preview' : ''}`}
                  style={{ fontSize: '14px', lineHeight: '1.5' }}
                  dangerouslySetInnerHTML={{ __html: sanitized }}
                />
              )}
            </div>
            {/* buttons below bubble */}
            {filteredButtons.map((row, rowIdx) => (
              <div key={rowIdx} className="flex gap-1 mt-1">
                {row
                  .filter(btn => btn.text)
                  .map((btn, btnIdx) => (
                    <div
                      key={btnIdx}
                      className="flex-1 bg-[#3a7bd5] rounded-md py-1.5 text-center text-white text-sm"
                    >
                      {btn.text}
                    </div>
                  ))}
              </div>
            ))}
          </div>
        ) : (
          <div className="flex items-center justify-center min-h-32 text-hint text-sm">
            Предпросмотр будет здесь
          </div>
        )}
      </div>
    </div>
  );
};

export default WelcomePreview;
