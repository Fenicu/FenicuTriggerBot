import React, { useEffect, useState } from 'react';
import { checkCaptcha, solveCaptcha } from '../api/client';
import { Loader2, Check, CheckCircle, XCircle, ShieldCheck, Shield } from 'lucide-react';

const CaptchaPage: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [verifying, setVerifying] = useState(false);
  const [checked, setChecked] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [ripple, setRipple] = useState(false);
  const [showButton, setShowButton] = useState(false);
  const [checking, setChecking] = useState(false);

  useEffect(() => {
    const init = async () => {
      try {
        const initData = (window as any).Telegram?.WebApp?.initData;
        const result = await checkCaptcha(initData);

        if (result.ok) {
          if (result.status === 'no_session') {
            setError('No active captcha session found.');
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
        setSuccess(true);
        // Close WebApp after a short delay
        setTimeout(() => {
          (window as any).Telegram?.WebApp?.close();
        }, 2000);
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
        <CheckCircle className="text-green-500 mb-4" size={64} />
        <h1 className="text-2xl font-bold mb-2">Verified!</h1>
        <p className="text-hint text-center">You have successfully passed the captcha.</p>
        <p className="text-hint text-sm mt-4">Closing window...</p>
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
            w-full p-4 rounded-xl border-2 cursor-pointer transition-all duration-200 flex items-center gap-4 mb-6 relative overflow-hidden
            ${checked ? 'border-green-500 bg-green-500/5' : 'border-hint/20 hover:border-link'}
          `}
          onClick={() => {
            if (!verifying && !checking) {
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
