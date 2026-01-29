import React, { useEffect, useCallback } from 'react';
import { X, AlertTriangle, AlertCircle, HelpCircle } from 'lucide-react';
import { useConfirmModal } from '../store/store';

const ConfirmModal: React.FC = () => {
  const { isOpen, title, message, confirmText, cancelText, variant, onConfirm, onCancel } =
    useConfirmModal();

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (!isOpen) return;

      if (e.key === 'Escape') {
        onCancel();
      } else if (e.key === 'Enter') {
        onConfirm();
      }
    },
    [isOpen, onConfirm, onCancel]
  );

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  // Prevent body scroll when modal is open
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => {
      document.body.style.overflow = '';
    };
  }, [isOpen]);

  if (!isOpen) return null;

  const getIcon = () => {
    switch (variant) {
      case 'danger':
        return <AlertTriangle className="text-red-500" size={28} />;
      case 'warning':
        return <AlertCircle className="text-yellow-500" size={28} />;
      default:
        return <HelpCircle className="text-link" size={28} />;
    }
  };

  const getIconBgClass = () => {
    switch (variant) {
      case 'danger':
        return 'bg-red-500/10';
      case 'warning':
        return 'bg-yellow-500/10';
      default:
        return 'bg-link/10';
    }
  };

  const getConfirmButtonClass = () => {
    switch (variant) {
      case 'danger':
        return 'bg-red-500 hover:bg-red-600 text-white';
      case 'warning':
        return 'bg-yellow-500 hover:bg-yellow-600 text-black';
      default:
        return 'bg-link hover:bg-opacity-90 text-white';
    }
  };

  return (
    <div
      className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-100 p-4 animate-fadeIn"
      onClick={onCancel}
    >
      <div
        className="bg-section-bg p-6 rounded-2xl max-w-sm w-full shadow-2xl border border-secondary-bg"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Close button */}
        <button
          onClick={onCancel}
          className="absolute top-4 right-4 text-hint hover:text-text transition-colors"
        >
          <X size={20} />
        </button>

        {/* Icon */}
        <div className={`w-14 h-14 ${getIconBgClass()} rounded-full flex items-center justify-center mx-auto mb-4`}>
          {getIcon()}
        </div>

        {/* Title */}
        <h2 className="text-lg font-bold text-center mb-2">{title}</h2>

        {/* Message */}
        <p className="text-hint text-center mb-6">{message}</p>

        {/* Buttons */}
        <div className="flex gap-3">
          <button
            onClick={onCancel}
            className="flex-1 py-3 px-4 rounded-xl font-medium bg-secondary-bg hover:bg-black/10 transition-colors"
          >
            {cancelText}
          </button>
          <button
            onClick={onConfirm}
            className={`flex-1 py-3 px-4 rounded-xl font-medium transition-colors ${getConfirmButtonClass()}`}
          >
            {confirmText}
          </button>
        </div>
      </div>
    </div>
  );
};

export default ConfirmModal;
