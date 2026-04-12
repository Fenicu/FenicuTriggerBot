import React from 'react';
import { CheckCircle, Clock, AlertTriangle, Trash2, Ban } from 'lucide-react';
import Badge from './ui/Badge';

export type ModerationStatus = 'safe' | 'pending' | 'flagged' | 'deleted' | string;

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
  pending: { icon: Clock, label: 'Pending', variant: 'orange' },
  flagged: { icon: AlertTriangle, label: 'Flagged', variant: 'orange' },
  deleted: { icon: Trash2, label: 'Deleted', variant: 'gray' },
  banned_chat: { icon: Ban, label: 'Banned', variant: 'red' },
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
