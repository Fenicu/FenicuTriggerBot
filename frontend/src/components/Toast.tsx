import React, { useEffect } from 'react';

interface ToastProps {
  message: string;
  onClose: () => void;
  duration?: number;
}

const Toast: React.FC<ToastProps> = ({ message, onClose, duration = 3000 }) => {
  useEffect(() => {
    const timer = setTimeout(() => {
      onClose();
    }, duration);
    return () => clearTimeout(timer);
  }, [duration, onClose]);

  return (
    <div className="fixed bottom-20 left-1/2 -translate-x-1/2 bg-black/80 text-white px-6 py-3 rounded-3xl z-2000 text-sm shadow-md animate-fadeIn">
      {message}
    </div>
  );
};

export default Toast;
