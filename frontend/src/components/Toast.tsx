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
    <div style={{
      position: 'fixed',
      bottom: '80px',
      left: '50%',
      transform: 'translateX(-50%)',
      backgroundColor: 'rgba(0, 0, 0, 0.8)',
      color: 'white',
      padding: '12px 24px',
      borderRadius: '24px',
      zIndex: 2000,
      fontSize: '14px',
      boxShadow: '0 4px 6px rgba(0,0,0,0.1)',
      animation: 'fadeIn 0.3s ease-out'
    }}>
      {message}
    </div>
  );
};

export default Toast;
