'use client';

import { Suspense, useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { CheckCircle2, XCircle, Loader2 } from 'lucide-react';
import { Button } from '@/src/components/ui';
import { API_BASE } from '@/src/lib/apiFetch';

type State = 'loading' | 'success' | 'error';

function ConfirmEmailChangePageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get('token');
  // A missing token is knowable during render, so it seeds the initial state
  // instead of being set synchronously inside the effect below (which causes
  // a cascading render).
  const [state, setState] = useState<State>(token ? 'loading' : 'error');
  const [message, setMessage] = useState(
    token ? '' : 'Invalid confirmation link. No token found.'
  );
  const [countdown, setCountdown] = useState(3);

  const clearSession = () => {
    localStorage.removeItem('accessToken');
    localStorage.removeItem('refreshToken');
    localStorage.removeItem('mq_user');
  };

  useEffect(() => {
    if (!token) return;

    fetch(`${API_BASE}/api/auth/email-change/confirm/`, {
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
  }, [token]);

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


// useSearchParams() reads the ?token= query string, which does not exist when
// Next.js pre-renders this page at build time. The Suspense boundary defers
// that part to the browser; without it `next build` fails.
export default function ConfirmEmailChangePage() {
  return (
    <Suspense fallback={
    <div className="min-h-screen bg-neutral-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-sm border border-neutral-200 p-10 max-w-md w-full text-center">
        <Loader2 size={48} className="mx-auto text-primary animate-spin mb-6" />
        <h2 className="text-xl font-bold text-neutral-900">Loading…</h2>
      </div>
    </div>
    }>
      <ConfirmEmailChangePageContent />
    </Suspense>
  );
}
