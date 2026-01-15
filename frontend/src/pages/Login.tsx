import React, { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

const Login: React.FC = () => {
  const navigate = useNavigate();
  const botName = import.meta.env.VITE_BOT_USERNAME;

  useEffect(() => {
    if (!botName) return;

    if (document.getElementById('telegram-widget-script')) return;

    const script = document.createElement('script');
    script.id = 'telegram-widget-script';
    script.src = 'https://telegram.org/js/telegram-widget.js?22';
    script.setAttribute('data-telegram-login', botName);
    script.setAttribute('data-size', 'large');
    script.setAttribute('data-request-access', 'write');
    script.setAttribute('data-onauth', 'onTelegramAuth(user)');
    script.async = true;
    document.getElementById('telegram-login-container')?.appendChild(script);

    (window as any).onTelegramAuth = (user: any) => {
      const params = new URLSearchParams();
      Object.entries(user).forEach(([key, value]) => {
        params.append(key, String(value));
      });
      const authData = params.toString();

      localStorage.setItem('auth_data', authData);
      navigate('/');
    };
  }, [botName, navigate]);

  if (!botName) {
    return <div className="p-4 text-red-500">Please configure VITE_BOT_USERNAME in .env</div>;
  }

  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-bg text-text">
      <h1 className="text-2xl font-bold mb-8">Login to Trigger Admin</h1>
      <div id="telegram-login-container"></div>
    </div>
  );
};

export default Login;
