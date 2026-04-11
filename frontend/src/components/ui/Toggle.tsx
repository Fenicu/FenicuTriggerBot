import React from 'react';

interface ToggleProps {
  value: boolean;
  onChange: (v: boolean) => void;
  label?: string;
  hint?: string;
  ariaLabel?: string;
}

const Toggle: React.FC<ToggleProps> = ({ value, onChange, label, hint, ariaLabel }) => {
  if (label) {
    return (
      <label className="flex items-center justify-between py-3 cursor-pointer">
        <div className="flex-1 min-w-0 mr-3">
          <span className="text-[15px] font-medium">{label}</span>
          {hint && <span className="block text-xs text-hint mt-0.5">{hint}</span>}
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={value}
          onClick={() => onChange(!value)}
          className={`relative w-[44px] h-[26px] rounded-[13px] transition-colors duration-250 flex-shrink-0 ${
            value ? 'bg-button' : 'bg-[#3f3f46]'
          }`}
        >
          <span
            className={`absolute top-[3px] left-[3px] w-[20px] h-[20px] rounded-full bg-white shadow-[0_1px_3px_rgba(0,0,0,0.3)] transition-transform duration-250 ${
              value ? 'translate-x-[18px]' : ''
            }`}
          />
        </button>
      </label>
    );
  }

  return (
    <button
      type="button"
      role="switch"
      aria-checked={value}
      aria-label={ariaLabel}
      onClick={() => onChange(!value)}
      className={`relative w-[44px] h-[26px] rounded-[13px] transition-colors duration-250 flex-shrink-0 ${
        value ? 'bg-button' : 'bg-[#3f3f46]'
      }`}
    >
      <span
        className={`absolute top-[3px] left-[3px] w-[20px] h-[20px] rounded-full bg-white shadow-[0_1px_3px_rgba(0,0,0,0.3)] transition-transform duration-250 ${
          value ? 'translate-x-[18px]' : ''
        }`}
      />
    </button>
  );
};

export default Toggle;
