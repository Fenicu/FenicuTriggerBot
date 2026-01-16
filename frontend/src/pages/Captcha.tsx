import React, { useEffect, useState } from 'react';
import apiClient, { checkCaptcha, solveCaptcha } from '../api/client';
import { Loader2, Check, CheckCircle, XCircle, ShieldCheck, Shield, Clock } from 'lucide-react';
import type { Chat } from '../types';

const CaptchaPage: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [verifying, setVerifying] = useState(false);
  const [checked, setChecked] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [ripple, setRipple] = useState(false);
  const [showButton, setShowButton] = useState(false);
  const [checking, setChecking] = useState(false);
  const [verified, setVerified] = useState(false);
  const [chat, setChat] = useState<Chat | null>(null);
  const [avatarUrl, setAvatarUrl] = useState<string | null>(null);
  const [chatId, setChatId] = useState<number | null>(null);
  const [timer, setTimer] = useState(7);

  useEffect(() => {
    const init = async () => {
      try {
        const initData = (window as any).Telegram?.WebApp?.initData;
        const result = await checkCaptcha(initData);

        if (result.ok) {
          if (result.status === 'no_session') {
            setError('No active captcha session found.');
          } else if (result.status === 'pending' && result.chat_id) {
            setChatId(result.chat_id);
          }
        }
      } catch (err: any) {
        console.error('Captcha check failed:', err);
        setError(err.response?.data?.detail || 'Failed to check captcha status.');
      } finally {
        setLoading(false);
      }
    };

    init();
  }, []);

  const handleVerify = async () => {
    if (!checked) return;

    setVerifying(true);
    setError(null);

    try {
      const initData = (window as any).Telegram?.WebApp?.initData;
      const result = await solveCaptcha(initData);

      if (result.ok) {
        setVerified(true);
        setSuccess(true);

        if (chatId) {
          apiClient.get<Chat>(`/chats/${chatId}`).then(res => {
            setChat(res.data);
            if (res.data.photo_id) {
              apiClient.get(`/chats/${chatId}/photo`, { responseType: 'blob' })
                .then(photoRes => {
                  const url = URL.createObjectURL(photoRes.data);
                  setAvatarUrl(url);
                })
                .catch(err => console.error('Failed to load avatar', err));
            }
          }).catch(err => console.error('Failed to load chat', err));
        }

        const interval = setInterval(() => {
          setTimer(prev => {
            if (prev <= 1) {
              clearInterval(interval);
              (window as any).Telegram?.WebApp?.close();
              return 0;
            }
            return prev - 1;
          });
        }, 1000);
      }
    } catch (err: any) {
      console.error('Captcha solve failed:', err);
      setError(err.response?.data?.detail || 'Failed to verify captcha.');
      setChecked(false);
      setShowButton(false);
      setChecking(false);
    } finally {
      setVerifying(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-bg text-text">
        <Loader2 className="animate-spin text-link" size={48} />
      </div>
    );
  }

  if (success) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-bg text-text p-4">
        <div className="bg-section-bg p-8 rounded-2xl shadow-lg max-w-md w-full flex flex-col items-center">
          <CheckCircle className="text-green-500 mb-4" size={64} />
          <h1 className="text-2xl font-bold mb-2 text-center">Verified!</h1>
          <p className="text-hint text-center mb-6">You have successfully passed the captcha.</p>

          {chat && (
            <div className="w-full bg-bg/50 rounded-xl p-4 mb-6 flex items-center gap-4">
              {avatarUrl && (
                <img
                  src={avatarUrl}
                  alt="Chat Avatar"
                  className="w-12 h-12 rounded-full object-cover"
                />
              )}
              <div className="flex-1">
                <div className="font-bold">{chat.title || chat.username || `Chat ${chat.id}`}</div>
                <div className="text-hint text-sm capitalize">{chat.type}</div>
              </div>
            </div>
          )}

          <div className="w-full bg-bg/50 rounded-xl p-4 mb-6 text-center">
            <div className="flex items-center justify-center gap-2 mb-2">
              <Clock size={20} className="text-hint" />
              <span className="text-hint">Closing in {timer} seconds</span>
            </div>
            <div className="w-full bg-bg rounded-full h-2">
              <div
                className="bg-link h-2 rounded-full transition-all duration-1000"
                style={{ width: `${(timer / 7) * 100}%` }}
              ></div>
            </div>
          </div>

          <button
            onClick={() => (window as any).Telegram?.WebApp?.close()}
            className="w-full py-3 px-6 rounded-xl font-bold text-white bg-link hover:bg-opacity-90 transition-colors shadow-lg"
          >
            Close Now
          </button>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-bg text-text p-4">
        <XCircle className="text-red-500 mb-4" size={64} />
        <h1 className="text-2xl font-bold mb-2">Error</h1>
        <p className="text-red-500 text-center mb-4">{error}</p>
        <button
          onClick={() => window.location.reload()}
          className="px-6 py-2 bg-section-bg rounded-lg hover:bg-opacity-80 transition-colors"
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-bg text-text p-4">
      <div className="bg-section-bg p-8 rounded-2xl shadow-lg max-w-md w-full flex flex-col items-center">
        <ShieldCheck className="text-link mb-6" size={48} />

        <h1 className="text-2xl font-bold mb-2 text-center">Security Check</h1>
        <p className="text-hint text-center mb-8">
          Please verify that you are a human to continue.
        </p>

        <div
          className={`
            w-full p-4 rounded-xl border-2 transition-all duration-200 flex items-center gap-4 mb-6 relative overflow-hidden
            ${verified ? 'cursor-default' : 'cursor-pointer'}
            ${checked ? 'border-green-500 bg-green-500/5' : 'border-hint/20 hover:border-link'}
          `}
          onClick={() => {
            if (!verifying && !checking && !verified && (!checked || !showButton)) {
              const newChecked = !checked;
              setChecked(newChecked);
              setRipple(true);
              setTimeout(() => setRipple(false), 600);
              if (newChecked) {
                setChecking(true);
                setTimeout(() => {
                  setChecking(false);
                  setShowButton(true);
                }, 1000);
              } else {
                setShowButton(false);
              }
            }
          }}
        >
          {ripple && (
            <div className="absolute inset-0 bg-green-500/20 rounded-xl animate-ripple"></div>
          )}
          <div className={`
            w-6 h-6 border-2 flex items-center justify-center transition-colors relative
            ${checked ? 'bg-green-500 border-green-500' : 'border-hint'}
          `}>
            {checked && <Check size={16} className="text-white animate-checkmark" />}
          </div>
          <span className="font-medium">I am not a robot</span>
        </div>

        {checking && (
          <div className="flex items-center justify-center gap-2 text-hint animate-fadeIn">
            <Loader2 className="animate-spin" size={16} />
            <span>Checking your response...</span>
          </div>
        )}

        {showButton && (
          <button
            onClick={handleVerify}
            disabled={!checked || verifying}
            className={`
              w-full py-4 px-6 rounded-2xl font-bold text-white transition-all duration-500 transform animate-fadeIn
              bg-linear-to-r from-link to-blue-600 hover:from-blue-600 hover:to-link
              shadow-xl shadow-link/30 hover:shadow-2xl hover:shadow-link/40
              flex items-center justify-center gap-3
              ${!checked || verifying
                ? 'bg-gray-500/20 text-gray-400 cursor-not-allowed scale-95 opacity-50'
                : 'hover:scale-105 scale-100 active:scale-95'}
            `}
          >
            {verifying ? (
              <>
                <Loader2 className="animate-spin" size={24} />
                <span>Verifying...</span>
              </>
            ) : (
              <>
                <Shield size={24} />
                <span>Verify</span>
              </>
            )}
          </button>
        )}
      </div>
    </div>
  );
};

export default CaptchaPage;
