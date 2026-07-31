import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { systemApi } from '../api/client';

const Login: React.FC = () => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [oidcEnabled, setOidcEnabled] = useState(false);

  useEffect(() => {
    // Обработка OIDC callback: ?oidc_code=...
    const params = new URLSearchParams(window.location.search);
    const oidcCode = params.get('oidc_code');

    if (oidcCode) {
      window.history.replaceState({}, '', window.location.pathname + window.location.hash);
      const baseUrl = import.meta.env.VITE_API_URL || '/api/v1';
      fetch(`${baseUrl}/auth/oidc/exchange`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: oidcCode }),
      })
        .then((r) => r.json())
        .then((data) => {
          if (data.token) {
            localStorage.setItem('auth_token', data.token);
            navigate('/');
          } else {
            setError('Не удалось завершить авторизацию');
            setLoading(false);
          }
        })
        .catch(() => {
          setError('Ошибка при обмене кода');
          setLoading(false);
        });
      return;
    }

    const fetchConfig = async () => {
      try {
        const config = await systemApi.getConfig();
        setOidcEnabled(config.telegram_oidc_enabled);
      } catch {
        setError('Failed to load configuration');
      } finally {
        setLoading(false);
      }
    };
    fetchConfig();
  }, [navigate]);

  if (loading) {
    return <div className="flex items-center justify-center min-h-screen bg-bg text-text">Loading...</div>;
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen bg-bg text-text p-4">
        <div className="text-danger mb-4">{error}</div>
        <button
          onClick={() => { setError(null); window.location.reload(); }}
          className="px-4 py-2 bg-button text-button-text rounded-lg"
        >
          Попробовать снова
        </button>
      </div>
    );
  }

  const apiBase = import.meta.env.VITE_API_URL || '/api/v1';

  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-bg text-text">
      <h1 className="text-2xl font-bold mb-8">Login to Trigger Admin</h1>
      {oidcEnabled ? (
        <a
          href={`${apiBase}/auth/telegram-oidc/login`}
          className="flex items-center justify-center gap-2.5 px-6 py-3 rounded-xl bg-[#2AABEE] !text-white no-underline text-sm font-semibold hover:opacity-90 transition-opacity"
        >
          <svg viewBox="0 0 24 24" className="h-5 w-5" fill="currentColor">
            <path d="M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a12 12 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.48.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z"/>
          </svg>
          Войти через Telegram
        </a>
      ) : (
        <div className="text-hint text-sm">Telegram OIDC не настроен</div>
      )}
    </div>
  );
};

export default Login;
