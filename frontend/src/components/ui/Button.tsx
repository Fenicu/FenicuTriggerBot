import React from 'react';

type ButtonVariant = 'primary' | 'secondary' | 'danger';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
}

const variantStyles: Record<ButtonVariant, string> = {
  primary: 'bg-button text-button-text',
  secondary: 'bg-elevated text-text',
  danger: 'bg-danger/12 text-[#f87171]',
};

const Button: React.FC<ButtonProps> = ({ variant = 'primary', className = '', children, ...props }) => (
  <button
    className={`px-5 py-3 rounded-[10px] text-sm font-semibold transition-all active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed ${variantStyles[variant]} ${className}`}
    {...props}
  >
    {children}
  </button>
);

export default Button;
