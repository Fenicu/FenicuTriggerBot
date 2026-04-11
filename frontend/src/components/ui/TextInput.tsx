import React from 'react';

interface TextInputProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'onChange'> {
  label?: string;
  hint?: string;
  onChange: (v: string) => void;
}

const TextInput: React.FC<TextInputProps> = ({ label, hint, onChange, className = '', ...props }) => (
  <div className={label ? 'flex items-center justify-between py-2 gap-2' : ''}>
    {label && (
      <div className="flex flex-col">
        <span className="text-[14px] font-medium">{label}</span>
        {hint && <span className="text-xs text-hint">{hint}</span>}
      </div>
    )}
    <input
      {...props}
      onChange={(e) => onChange(e.target.value)}
      className={`bg-elevated text-text border border-border rounded-[10px] px-3.5 py-2 text-sm outline-none focus:border-button transition-colors ${label ? 'w-40 text-right' : 'w-full'} ${className}`}
    />
  </div>
);

export default TextInput;
