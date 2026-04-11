import React from 'react';

type BadgeVariant = 'green' | 'red' | 'blue' | 'orange' | 'purple' | 'gray';

interface BadgeProps {
  variant: BadgeVariant;
  icon?: React.ElementType;
  children: React.ReactNode;
  className?: string;
}

const variantStyles: Record<BadgeVariant, string> = {
  green: 'bg-success/12 text-success',
  red: 'bg-danger/12 text-[#f87171]',
  blue: 'bg-button/12 text-link',
  orange: 'bg-warning/12 text-[#fbbf24]',
  purple: 'bg-purple-500/12 text-purple-400',
  gray: 'bg-hint/12 text-hint',
};

const Badge: React.FC<BadgeProps> = ({ variant, icon: Icon, children, className = '' }) => (
  <span className={`inline-flex items-center gap-1 text-xs font-medium px-2.5 py-1 rounded-full ${variantStyles[variant]} ${className}`}>
    {Icon && <Icon size={12} />}
    {children}
  </span>
);

export default Badge;
