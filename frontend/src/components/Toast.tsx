import React from 'react';
import { X, CheckCircle, XCircle, AlertTriangle, Info } from 'lucide-react';
import { useToasts, removeToast, type ToastType } from '../store/store';

interface SingleToastProps {
  id: string;
  message: string;
  type: ToastType;
  onClose: () => void;
}

const toastConfig: Record<ToastType, {
  icon: React.ComponentType<{ size: number; className?: string }>;
  bgClass: string;
  iconClass: string;
  borderClass: string;
}> = {
  success: {
    icon: CheckCircle,
    bgClass: 'bg-green-500/10',
    iconClass: 'text-green-500',
    borderClass: 'border-green-500/20',
  },
  error: {
    icon: XCircle,
    bgClass: 'bg-red-500/10',
    iconClass: 'text-red-500',
    borderClass: 'border-red-500/20',
  },
  warning: {
    icon: AlertTriangle,
    bgClass: 'bg-yellow-500/10',
    iconClass: 'text-yellow-500',
    borderClass: 'border-yellow-500/20',
  },
  info: {
    icon: Info,
    bgClass: 'bg-link/10',
    iconClass: 'text-link',
    borderClass: 'border-link/20',
  },
};

const SingleToast: React.FC<SingleToastProps> = ({ message, type, onClose }) => {
  const config = toastConfig[type];
  const Icon = config.icon;

  return (
    <div
      className={`
        flex items-center gap-3 px-4 py-3 rounded-xl shadow-lg border backdrop-blur-sm
        ${config.bgClass} ${config.borderClass}
        animate-fadeIn
      `}
    >
      <Icon size={20} className={config.iconClass} />
      <span className="flex-1 text-sm text-text">{message}</span>
      <button
        onClick={onClose}
        className="text-hint hover:text-text transition-colors p-1"
      >
        <X size={16} />
      </button>
    </div>
  );
};

const ToastContainer: React.FC = () => {
  const toasts = useToasts();

  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-20 left-4 right-4 md:bottom-6 md:left-auto md:right-6 md:w-80 z-200 flex flex-col gap-2">
      {toasts.map((toast) => (
        <SingleToast
          key={toast.id}
          id={toast.id}
          message={toast.message}
          type={toast.type}
          onClose={() => removeToast(toast.id)}
        />
      ))}
    </div>
  );
};

export default ToastContainer;
