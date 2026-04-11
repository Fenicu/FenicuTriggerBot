import React from 'react';
import { CheckCircle, Ban, Clock, AlertTriangle, XCircle } from 'lucide-react';
import Badge from './ui/Badge';

export type ModerationStatus = 'safe' | 'banned' | 'pending' | 'flagged' | 'error' | string;

interface StatusBadgeProps {
  status: ModerationStatus;
  size?: 'sm' | 'md';
  className?: string;
}

const statusConfig: Record<string, {
  icon: React.ComponentType<{ size: number; className?: string }>;
  label: string;
  variant: 'green' | 'red' | 'orange' | 'gray';
}> = {
  safe: { icon: CheckCircle, label: 'Safe', variant: 'green' },
  banned: { icon: Ban, label: 'Banned', variant: 'red' },
  pending: { icon: Clock, label: 'Pending', variant: 'orange' },
  flagged: { icon: AlertTriangle, label: 'Flagged', variant: 'orange' },
  error: { icon: XCircle, label: 'Error', variant: 'gray' },
};

const StatusBadge: React.FC<StatusBadgeProps> = ({ status, size, className = '' }) => {
  const config = statusConfig[status];
  const sizeClass = size === 'md' ? 'text-sm px-3 py-1.5' : '';
  if (!config) {
    return <Badge variant="gray" className={`${sizeClass} ${className}`}>{status}</Badge>;
  }
  return (
    <Badge variant={config.variant} icon={config.icon} className={`${sizeClass} ${className}`}>
      {config.label}
    </Badge>
  );
};

export default StatusBadge;
