import React, { useEffect } from 'react';
import { X } from 'lucide-react';

interface MediaModalProps {
  isOpen: boolean;
  onClose: () => void;
  children: React.ReactNode;
}

const MediaModal: React.FC<MediaModalProps> = ({ isOpen, onClose, children }) => {
  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    if (isOpen) {
      document.addEventListener('keydown', handleEsc);
      document.body.style.overflow = 'hidden';
    }
    return () => {
      document.removeEventListener('keydown', handleEsc);
      document.body.style.overflow = 'unset';
    };
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-100 bg-black/90 flex items-center justify-center p-4 cursor-zoom-out animate-in fade-in duration-200"
      onClick={(e) => {
        e.stopPropagation();
        onClose();
      }}
    >
      <button
        className="absolute top-4 right-4 text-white/70 hover:text-white transition-colors z-101"
        onClick={(e) => {
            e.stopPropagation();
            onClose();
        }}
      >
        <X size={32} />
      </button>
      <div
        onClick={(e) => e.stopPropagation()}
        className="max-w-full max-h-full flex items-center justify-center overflow-hidden"
      >
        {children}
      </div>
    </div>
  );
};

export default MediaModal;
