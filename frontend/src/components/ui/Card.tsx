import React from 'react';
import { Lock, Unlock } from 'lucide-react';
import Toggle from './Toggle';

interface CardProps {
  icon?: React.ElementType;
  iconGradient?: string;
  title?: string;
  toggle?: { value: boolean; onChange: (v: boolean) => void };
  lock?: { locked: boolean; onToggle: () => void; visible: boolean };
  disabled?: boolean;
  children: React.ReactNode;
  className?: string;
}

const Card: React.FC<CardProps> = ({ icon: Icon, iconGradient, title, toggle, lock, disabled, children, className = '' }) => (
  <div className={`bg-surface border border-border rounded-[14px] mb-3 ${className}`}>
    {(Icon || title || toggle || lock) && (
      <div className="flex items-center justify-between px-4 py-3.5">
        <div className="flex items-center gap-2.5">
          {Icon && (
            <div className={`w-8 h-8 rounded-[9px] flex items-center justify-center ${iconGradient || 'bg-button'}`}>
              <Icon size={16} className="text-white" />
            </div>
          )}
          {title && <span className="font-semibold text-[15px]">{title}</span>}
        </div>
        <div className={`flex items-center gap-2.5 ${disabled ? 'opacity-50 pointer-events-none' : ''}`}>
          {lock?.visible && (
            <button
              type="button"
              onClick={lock.onToggle}
              className="text-[#52525b] hover:text-text transition-colors p-1"
              title={lock.locked ? 'Unlock for admins' : 'Lock for admins'}
            >
              {lock.locked ? <Lock size={16} /> : <Unlock size={16} />}
            </button>
          )}
          {toggle && <Toggle value={toggle.value} onChange={toggle.onChange} ariaLabel={title ? `Toggle ${title}` : undefined} />}
        </div>
      </div>
    )}
    <div className={`px-4 pb-4 ${!Icon && !title ? 'pt-4' : ''} ${disabled ? 'opacity-50 pointer-events-none' : ''}`}>
      {children}
    </div>
  </div>
);

export default Card;
