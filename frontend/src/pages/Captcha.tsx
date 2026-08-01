import React, { useEffect, useState, useRef } from 'react';
import { captchaApi, chatsApi } from '../api/client';
import { Loader2, Check, CheckCircle, XCircle, ShieldCheck, Shield, Clock } from 'lucide-react';
import type { Chat, CaptchaSessionKind } from '../types';
import { parseCaptchaToken } from '../lib/captchaToken';
import { AxiosError } from 'axios';

type Status = 'init' | 'idle' | 'verifying_human' | 'verifying_api' | 'success' | 'error';

const CaptchaPage: React.FC = () => {
  const [token] = useState<string | null>(() => parseCaptchaToken(window.location.hash));
  const [status, setStatus] = useState<Status>('init');
  const [chat, setChat] = useState<Chat | null>(null);
  const [avatarUrl, setAvatarUrl] = useState<string | null>(null);
  const [chatId, setChatId] = useState<number | null>(null);
  const [kind, setKind] = useState<CaptchaSessionKind | null>(null);
  const [timer, setTimer] = useState(7);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [checked, setChecked] = useState(false);
  const [ripple, setRipple] = useState(false);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    const init = async () => {
      try {
        const initData = window.Telegram?.WebApp?.initData;
        const result = await captchaApi.check(initData, token);

        if (!mountedRef.current) return;

        if (result.ok) {
          if (result.status === 'no_session') {
            setStatus('error');
            setErrorMessage('Активная сессия капчи не найдена.');
          } else if (result.status === 'pending' && result.chat_id) {
            setChatId(result.chat_id);
            setKind(result.kind ?? null);
            setStatus('idle');
          }
        } else {
          setStatus('error');
          setErrorMessage('Не удалось проверить статус капчи.');
        }
      } catch (err) {
        if (!mountedRef.current) return;
        setStatus('error');
        const message = err instanceof AxiosError ? err.response?.data?.detail : 'Не удалось проверить статус капчи.';
        setErrorMessage(message || 'Не удалось проверить статус капчи.');
      }
    };

    init();
  }, [token]);

  const handleVerify = async () => {
    if (!checked || status !== 'idle') return;

    setStatus('verifying_api');
    setErrorMessage(null);

    try {
      const initData = window.Telegram?.WebApp?.initData;
      const result = await captchaApi.solve(initData, token);

      if (!mountedRef.current) return;

      if (result.ok) {
        setStatus('success');
        setKind(result.kind ?? kind);

        // Trigger haptic feedback
        window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('success');

        if (chatId) {
          try {
            const chatData = await chatsApi.getById(chatId);
            if (!mountedRef.current) return;
            setChat(chatData);

            if (chatData.photo_id) {
              try {
                const photoBlob = await chatsApi.getPhoto(chatId);
                if (!mountedRef.current) return;
                const url = URL.createObjectURL(photoBlob);
                setAvatarUrl(url);
              } catch {
                // Photo loading failed, ignore
              }
            }
          } catch {
            // Chat loading failed, ignore
          }
        }
      } else if (result.status === 'expired') {
        // Join-request сессия протухла между показом Mini App и нажатием Verify
        setStatus('error');
        setErrorMessage('Ваша заявка на вступление истекла. Отправьте её снова.');
        setChecked(false);
      } else {
        setStatus('error');
        setErrorMessage('Не удалось пройти капчу.');
        setChecked(false);
      }
    } catch (err) {
      if (!mountedRef.current) return;

      // Транзиентный сбой approve на стороне Telegram: сессия возвращена в PENDING,
      // юзер должен мочь нажать Verify ещё раз без ухода на полноэкранный error.
      if (err instanceof AxiosError && err.response?.status === 503) {
        setStatus('idle');
        setErrorMessage('Не удалось подтвердить. Попробуйте ещё раз.');
        return;
      }

      setStatus('error');
      const message = err instanceof AxiosError ? err.response?.data?.detail : 'Не удалось пройти капчу.';
      setErrorMessage(message || 'Не удалось пройти капчу.');
      setChecked(false);
    }
  };

  useEffect(() => {
    if (avatarUrl) {
      return () => URL.revokeObjectURL(avatarUrl);
    }
  }, [avatarUrl]);

  useEffect(() => {
    if (status === 'success') {
      const interval = setInterval(() => {
        setTimer(prev => {
          if (prev <= 1) {
            clearInterval(interval);
            window.Telegram?.WebApp?.close?.();
            return 0;
          }
          return prev - 1;
        });
      }, 1000);
      return () => clearInterval(interval);
    }
  }, [status]);

  if (status === 'init') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-bg text-text">
        <Loader2 className="animate-spin text-link" size={48} />
      </div>
    );
  }

  if (status === 'success') {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-bg text-text p-4">
        <div className="bg-surface border border-border p-8 rounded-2xl shadow-lg max-w-md w-full flex flex-col items-center">
          <CheckCircle className="text-success mb-4" size={64} />
          <h1 className="text-2xl font-bold mb-2 text-center">
            {kind === 'join_request' ? 'Заявка одобрена!' : 'Пройдено!'}
          </h1>
          <p className="text-hint text-center mb-6">
            {kind === 'join_request'
              ? 'Ваша заявка одобрена.'
              : 'Вы успешно прошли капчу.'}
          </p>

          {chat && (
            <div className="w-full bg-elevated/50 rounded-xl p-4 mb-6 flex items-center gap-4">
              {avatarUrl && (
                <img
                  src={avatarUrl}
                  alt="Аватар чата"
                  className="w-12 h-12 rounded-full object-cover"
                />
              )}
              <div className="flex-1">
                <div className="font-bold">{chat.title || chat.username || `Чат ${chat.id}`}</div>
                <div className="text-hint text-sm capitalize">{chat.type}</div>
              </div>
            </div>
          )}

          <div className="w-full bg-elevated/50 rounded-xl p-4 mb-6 text-center">
            <div className="flex items-center justify-center gap-2 mb-2">
              <Clock size={20} className="text-hint" />
              <span className="text-hint">Закрытие через {timer} с</span>
            </div>
            <div className="w-full bg-bg rounded-full h-2">
              <div
                className="bg-button h-2 rounded-full transition-[width] duration-1000"
                style={{ width: `${(timer / 7) * 100}%` }}
              ></div>
            </div>
          </div>

          <button
            onClick={() => window.Telegram?.WebApp?.close?.()}
            className="w-full py-3 px-6 rounded-xl font-bold text-white bg-button hover:opacity-90 transition-colors shadow-lg"
          >
            Закрыть
          </button>
        </div>
      </div>
    );
  }

  if (status === 'error') {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-bg text-text p-4">
        <XCircle className="text-danger mb-4" size={64} />
        <h1 className="text-2xl font-bold mb-2">Ошибка</h1>
        <p className="text-danger text-center mb-4">{errorMessage}</p>
        <button
          onClick={() => window.location.reload()}
          className="px-6 py-2 bg-surface border border-border rounded-lg hover:opacity-80 transition-colors"
        >
          Повторить
        </button>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-bg text-text p-4">
      <div className="bg-surface border border-border p-8 rounded-2xl shadow-lg max-w-md w-full flex flex-col items-center">
        <ShieldCheck className="text-link mb-6" size={48} />

        <h1 className="text-2xl font-bold mb-2 text-center">Проверка безопасности</h1>
        <p className="text-hint text-center mb-8">
          Подтвердите, что вы не робот, чтобы продолжить.
        </p>

        <div
          className={`
            w-full p-4 rounded-xl border-2 transition-colors duration-200 flex items-center gap-4 mb-6 relative overflow-hidden
            ${status === 'idle' ? 'cursor-pointer' : 'cursor-default'}
            ${checked ? 'border-success bg-success-soft' : 'border-hint/20 hover:border-link'}
          `}
          onClick={() => {
            if (status === 'idle' && !checked) {
              setStatus('verifying_human');
              setRipple(true);
              window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('light');
              setTimeout(() => setRipple(false), 600);
              setTimeout(() => {
                setStatus('idle');
                setChecked(true);
              }, 1000);
            }
          }}
        >
          {ripple && (
            <div className="absolute inset-0 bg-success-soft rounded-xl animate-ripple"></div>
          )}
          <div className={`
            w-6 h-6 border-2 flex items-center justify-center transition-colors relative
            ${checked ? 'bg-success border-success' : 'border-hint'}
          `}>
            {checked && <Check size={16} className="text-white animate-checkmark" />}
          </div>
          <span className="font-medium">Я не робот</span>
        </div>

        {status === 'verifying_human' && (
          <div className="flex items-center justify-center gap-2 text-hint animate-fadeIn">
            <Loader2 className="animate-spin" size={16} />
            <span>Проверяем ваш ответ…</span>
          </div>
        )}

        {checked && status === 'idle' && (
          <button
            onClick={handleVerify}
            className={`
              w-full py-4 px-6 rounded-2xl font-bold text-white transition-colors duration-150 animate-fadeIn
              bg-linear-to-r from-link to-button hover:from-button hover:to-link
              shadow-xl shadow-link/30 hover:shadow-2xl hover:shadow-link/40
              flex items-center justify-center gap-3
            `}
          >
            <Shield size={24} />
            <span>Подтвердить</span>
          </button>
        )}

        {status === 'idle' && errorMessage && (
          <div className="w-full mt-4 text-center text-danger text-sm animate-fadeIn">
            {errorMessage}
          </div>
        )}
      </div>
    </div>
  );
};

export default CaptchaPage;
