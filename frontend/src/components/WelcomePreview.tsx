import React from 'react';
import type { WelcomeButton } from '../types';

interface WelcomePreviewProps {
  text: string;
  media: { file_id: string; file_type: 'photo' | 'video' | 'animation' } | null;
  buttons: WelcomeButton[][];
  isTemplate: boolean;
}

const ALLOWED_TAGS = ['b', 'i', 'u', 's', 'code', 'pre', 'tg-spoiler', 'a'];
const ALLOWED_ATTRS: Record<string, string[]> = { a: ['href'] };

function sanitizeHtml(html: string): string {
  const div = document.createElement('div');
  div.innerHTML = html;

  function cleanNode(node: Node): void {
    if (node.nodeType === Node.ELEMENT_NODE) {
      const el = node as Element;
      const tag = el.tagName.toLowerCase();

      if (!ALLOWED_TAGS.includes(tag)) {
        // Replace with text content
        const text = document.createTextNode(el.textContent || '');
        el.parentNode?.replaceChild(text, el);
        return;
      }

      // Remove disallowed attributes
      const allowedAttrs = ALLOWED_ATTRS[tag] || [];
      for (const attr of Array.from(el.attributes)) {
        if (!allowedAttrs.includes(attr.name)) {
          el.removeAttribute(attr.name);
        }
      }

      // Check href for javascript:
      if (tag === 'a') {
        const href = el.getAttribute('href') || '';
        if (href.trim().toLowerCase().startsWith('javascript:')) {
          el.removeAttribute('href');
        }
      }

      // Recurse into children (copy array since we may modify)
      Array.from(el.childNodes).forEach(cleanNode);
    }
  }

  Array.from(div.childNodes).forEach(cleanNode);
  return div.innerHTML;
}

function replaceTemplateVars(text: string): string {
  const now = new Date();
  return text
    .replace(/\{\{\s*user\.mention\s*\}\}/g, '<b>@username</b>')
    .replace(/\{\{\s*user\.full_name\s*\}\}/g, 'User Name')
    .replace(/\{\{\s*chat\.title\s*\}\}/g, 'Название чата')
    .replace(/\{\{\s*date\s*\}\}/g, now.toLocaleDateString('ru-RU'))
    .replace(/\{\{\s*time\s*\}\}/g, now.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' }));
}

const MEDIA_ICONS: Record<string, string> = {
  photo: '📷',
  video: '🎬',
  animation: '🎞',
};

const WelcomePreview: React.FC<WelcomePreviewProps> = ({ text, media, buttons, isTemplate }) => {
  const filteredButtons = buttons.filter(row => row.some(btn => btn.text));

  let displayText = text;
  if (isTemplate) {
    displayText = replaceTemplateVars(displayText);
  }
  const sanitized = sanitizeHtml(displayText);

  const hasContent = !!sanitized.trim() || !!media || filteredButtons.length > 0;

  return (
    <div className="bg-section-bg rounded-xl p-4">
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
                  className="px-3 py-2 text-white text-sm"
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
