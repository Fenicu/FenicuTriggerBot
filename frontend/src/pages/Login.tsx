import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { systemApi } from '../api/client';

const Login: React.FC = () => {
  const navigate = useNavigate();
  const [botName, setBotName] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchConfig = async () => {
      try {
        const config = await systemApi.getConfig();
        setBotName(config.bot_username);
      } catch {
        setError('Failed to load configuration');
      } finally {
        setLoading(false);
      }
    };
    fetchConfig();
  }, []);

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

    (window as Window & { onTelegramAuth?: (user: Record<string, unknown>) => void }).onTelegramAuth = (user) => {
      const params = new URLSearchParams();
      Object.entries(user).forEach(([key, value]) => {
        params.append(key, String(value));
      });
      const authData = params.toString();

      localStorage.setItem('auth_data', authData);
      navigate('/');
    };
  }, [botName, navigate]);

  if (loading) {
    return <div className="flex items-center justify-center min-h-screen bg-bg text-text">Loading...</div>;
  }

  if (error || !botName) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen bg-bg text-text p-4">
        <div className="text-red-500 mb-4">{error || 'Bot username not configured'}</div>
        <div className="text-hint text-sm">Please ensure BOT_USERNAME is set in server configuration</div>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-bg text-text">
      <h1 className="text-2xl font-bold mb-8">Login to Trigger Admin</h1>
      <div id="telegram-login-container"></div>
    </div>
  );
};

export default Login;
