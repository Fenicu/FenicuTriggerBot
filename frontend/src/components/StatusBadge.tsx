import React from 'react';
import { CheckCircle, Ban, Clock, AlertTriangle } from 'lucide-react';

export type ModerationStatus = 'safe' | 'banned' | 'pending' | 'flagged' | string;

interface StatusBadgeProps {
  status: ModerationStatus;
  size?: 'sm' | 'md';
  className?: string;
}

const statusConfig: Record<string, {
  icon: React.ComponentType<{ size: number; className?: string }>;
  label: string;
  colorClass: string;
  bgClass: string;
}> = {
  safe: {
    icon: CheckCircle,
    label: 'Safe',
    colorClass: 'text-green-500',
    bgClass: 'bg-green-500/10',
  },
  banned: {
    icon: Ban,
    label: 'Banned',
    colorClass: 'text-red-500',
    bgClass: 'bg-red-500/10',
  },
  pending: {
    icon: Clock,
    label: 'Pending',
    colorClass: 'text-yellow-500',
    bgClass: 'bg-yellow-500/10',
  },
  flagged: {
    icon: AlertTriangle,
    label: 'Flagged',
    colorClass: 'text-orange-500',
    bgClass: 'bg-orange-500/10',
  },
};

const StatusBadge: React.FC<StatusBadgeProps> = ({ status, size = 'sm', className = '' }) => {
  const config = statusConfig[status];

  if (!config) {
    return (
      <span className={`flex items-center text-gray-500 bg-gray-500/10 px-2 py-1 rounded text-xs font-medium w-fit ${className}`}>
        {status}
      </span>
    );
  }

  const Icon = config.icon;
  const iconSize = size === 'sm' ? 12 : 14;
  const textSize = size === 'sm' ? 'text-xs' : 'text-sm';

  return (
    <span
      className={`flex items-center ${config.colorClass} ${config.bgClass} px-2 py-1 rounded ${textSize} font-medium w-fit ${className}`}
    >
      <Icon size={iconSize} className="mr-1" />
      {config.label}
    </span>
  );
};

export default StatusBadge;
