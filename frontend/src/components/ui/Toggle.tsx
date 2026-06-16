import React from 'react';
import * as SwitchPrimitive from '@radix-ui/react-switch';

interface ToggleProps {
  value: boolean;
  onChange: (v: boolean) => void;
  label?: string;
  hint?: string;
  ariaLabel?: string;
}

const Toggle: React.FC<ToggleProps> = ({ value, onChange, label, hint, ariaLabel }) => {
  const sw = (
    <SwitchPrimitive.Root
      checked={value}
      onCheckedChange={onChange}
      aria-label={ariaLabel}
      className={`relative inline-flex items-center w-[46px] h-[26px] shrink-0 rounded-full outline-none cursor-pointer transition-colors duration-200 focus-visible:ring-2 focus-visible:ring-accent/50 ${
        value ? 'bg-accent' : 'bg-border-strong'
      }`}
    >
      <SwitchPrimitive.Thumb
        className={`pointer-events-none block w-[20px] h-[20px] rounded-full bg-white shadow-[0_1px_3px_rgba(0,0,0,0.4)] transition-transform duration-200 ${
          value ? 'translate-x-[23px]' : 'translate-x-[3px]'
        }`}
      />
    </SwitchPrimitive.Root>
  );

  if (label) {
    return (
      <label className="flex items-center justify-between py-3 cursor-pointer">
        <div className="flex-1 min-w-0 mr-3">
          <span className="text-[15px] font-medium">{label}</span>
          {hint && <span className="block text-xs text-hint mt-0.5">{hint}</span>}
        </div>
        {sw}
      </label>
    );
  }

  return sw;
};

export default Toggle;
