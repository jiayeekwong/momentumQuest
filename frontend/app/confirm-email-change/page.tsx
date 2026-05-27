'use client';

import { useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { CheckCircle2, XCircle, Loader2 } from 'lucide-react';
import { Button } from '@/src/components/ui';

type State = 'loading' | 'success' | 'error';

export default function ConfirmEmailChangePage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [state, setState] = useState<State>('loading');
  const [message, setMessage] = useState('');
  const [countdown, setCountdown] = useState(3);

  const clearSession = () => {
    localStorage.removeItem('accessToken');
    localStorage.removeItem('refreshToken');
    localStorage.removeItem('mq_user');
  };

  useEffect(() => {
    const token = searchParams.get('token');
    if (!token) {
      setState('error');
      setMessage('Invalid confirmation link. No token found.');
      return;
    }

    fetch('http://localhost:8000/api/auth/email-change/confirm/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token }),
    })
      .then(async res => {
        const data = await res.json();
        if (res.ok) {
          clearSession();
          setState('success');
          setMessage(data.detail ?? 'Email updated successfully.');
        } else {
          setState('error');
          setMessage(data.detail ?? 'Confirmation failed.');
        }
      })
      .catch(() => {
        setState('error');
        setMessage('Network error. Please try again.');
      });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  // Auto-redirect countdown after success
  useEffect(() => {
    if (state !== 'success') return;
    if (countdown <= 0) { router.push('/login'); return; }
    const t = setTimeout(() => setCountdown(c => c - 1), 1000);
    return () => clearTimeout(t);
  }, [state, countdown, router]);

  return (
    <div className="min-h-screen bg-neutral-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-sm border border-neutral-200 p-10 max-w-md w-full text-center">
        {state === 'loading' && (
          <>
            <Loader2 size={48} className="mx-auto text-primary animate-spin mb-6" />
            <h2 className="text-xl font-bold text-neutral-900">Confirming email change…</h2>
            <p className="text-sm text-neutral-500 mt-2">Please wait a moment.</p>
          </>
        )}

        {state === 'success' && (
          <>
            <div className="w-20 h-20 bg-emerald-50 rounded-full flex items-center justify-center mx-auto mb-6">
              <CheckCircle2 size={40} className="text-emerald-500" />
            </div>
            <h2 className="text-xl font-bold text-neutral-900">Email Updated!</h2>
            <p className="text-sm text-neutral-500 mt-2">{message}</p>
            <p className="text-xs text-neutral-400 mt-4">
              Redirecting to login in <span className="font-bold text-primary">{countdown}</span>s…
            </p>
            <Button className="mt-4 w-full" onClick={() => router.push('/login')}>
              Log in now
            </Button>
          </>
        )}

        {state === 'error' && (
          <>
            <div className="w-20 h-20 bg-red-50 rounded-full flex items-center justify-center mx-auto mb-6">
              <XCircle size={40} className="text-red-500" />
            </div>
            <h2 className="text-xl font-bold text-neutral-900">Confirmation Failed</h2>
            <p className="text-sm text-neutral-500 mt-2">{message}</p>
            <Button variant="outline" className="mt-8 w-full" onClick={() => router.push('/profile')}>
              Back to Profile
            </Button>
          </>
        )}
      </div>
    </div>
  );
}
