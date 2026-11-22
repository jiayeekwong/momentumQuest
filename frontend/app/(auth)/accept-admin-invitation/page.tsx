'use client';

import { Suspense, useEffect, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { ShieldCheck } from 'lucide-react';
import { Logo } from '@/src/components/Logo';
import { Button, Card, Input } from '@/src/components/ui';
import { API_BASE } from '@/src/lib/apiFetch';

interface InvitationDetails {
  email: string;
  role: 'DEPARTMENT_ADMIN' | 'SUPERUSER';
  department: string | null;
  expires_at: string;
}

function formatApiError(data: unknown, fallback: string): string {
  if (!data || typeof data !== 'object') return fallback;
  const record = data as Record<string, unknown>;
  if (typeof record.detail === 'string') return record.detail;
  for (const value of Object.values(record)) {
    if (Array.isArray(value) && value.length) return String(value[0]);
    if (typeof value === 'string') return value;
  }
  return fallback;
}

function AcceptInvitationContent() {
  const token = useSearchParams().get('token') ?? '';
  const [details, setDetails] = useState<InvitationDetails | null>(null);
  const [name, setName] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [isChecking, setIsChecking] = useState(Boolean(token));
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState(token ? '' : 'This invitation link is invalid.');
  const [complete, setComplete] = useState(false);
  const isSuperuserInvitation = details?.role === 'SUPERUSER';

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    fetch(`${API_BASE}/api/auth/admin-invitations/validate/?token=${encodeURIComponent(token)}`)
      .then(async response => {
        const data = await response.json().catch(() => null);
        if (!response.ok) throw new Error(formatApiError(data, 'This invitation is unavailable.'));
        if (!cancelled) setDetails(data);
      })
      .catch(checkError => {
        if (!cancelled) setError(checkError instanceof Error ? checkError.message : 'This invitation is unavailable.');
      })
      .finally(() => { if (!cancelled) setIsChecking(false); });
    return () => { cancelled = true; };
  }, [token]);

  async function acceptInvitation(event: React.FormEvent) {
    event.preventDefault();
    setError('');
    if (password !== confirmPassword) {
      setError('Passwords do not match.');
      return;
    }
    setIsSubmitting(true);
    try {
      const response = await fetch(`${API_BASE}/api/auth/admin-invitations/accept/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token, name: name.trim(), password, confirm_password: confirmPassword }),
      });
      const data = await response.json().catch(() => null);
      if (!response.ok) throw new Error(formatApiError(data, 'Could not create the administrator account.'));
      setComplete(true);
    } catch (acceptError) {
      setError(acceptError instanceof Error ? acceptError.message : 'Could not create the administrator account.');
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-gradient-to-br from-indigo-600 to-sky-500 px-4 py-10">
      <div className="w-full max-w-md">
        <div className="mb-7 flex justify-center"><Logo size="lg" theme="dark" layout="vertical" /></div>
        <Card className="p-8">
          <div className="mb-5 flex h-12 w-12 items-center justify-center rounded-xl bg-indigo-50 text-primary">
            <ShieldCheck size={24} />
          </div>
          <h1 className="text-2xl font-bold text-neutral-950">
            Set up your {isSuperuserInvitation ? 'superuser' : 'admin'} account
          </h1>

          {isChecking ? (
            <p className="mt-5 text-sm text-neutral-500">Checking your invitation…</p>
          ) : complete ? (
            <div className="mt-5 space-y-5">
              <p className="rounded-lg bg-emerald-50 p-3 text-sm font-semibold text-success">
                Your {isSuperuserInvitation ? 'superuser' : 'administrator'} account is ready. You can now sign in with {details?.email}.
              </p>
              <Link href="/login" className="block rounded-lg bg-primary px-5 py-3 text-center font-semibold text-white hover:opacity-90">
                Go to Login
              </Link>
            </div>
          ) : details ? (
            <form onSubmit={acceptInvitation} className="mt-5 space-y-5">
              <div className="rounded-lg border border-indigo-100 bg-indigo-50 p-3 text-sm text-neutral-700">
                <p><span className="font-semibold">Email:</span> {details.email}</p>
                <p className="mt-1">
                  <span className="font-semibold">Account type:</span>{' '}
                  {isSuperuserInvitation ? 'Superuser' : 'Department administrator'}
                </p>
                <p className="mt-1">
                  <span className="font-semibold">
                    {isSuperuserInvitation ? 'Access:' : 'Department:'}
                  </span>{' '}
                  {isSuperuserInvitation ? 'All departments' : details.department}
                </p>
              </div>
              {isSuperuserInvitation && (
                <p className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs leading-relaxed text-amber-800">
                  This account will have full platform access, including the ability to manage departments and invite other administrators.
                </p>
              )}
              <Input label="Full Name" value={name} onChange={event => setName(event.target.value)} required />
              <div>
                <Input label="Password" type="password" value={password} onChange={event => setPassword(event.target.value)} required />
                <p className="mt-2 text-xs leading-relaxed text-neutral-500">
                  Use at least 8 characters with a letter, number, and special character.
                </p>
              </div>
              <Input label="Confirm Password" type="password" value={confirmPassword} onChange={event => setConfirmPassword(event.target.value)} required />
              {error && <p className="rounded-lg bg-red-50 p-3 text-sm font-semibold text-danger">{error}</p>}
              <Button type="submit" fullWidth size="lg" isLoading={isSubmitting} disabled={isSubmitting}>
                Create {isSuperuserInvitation ? 'Superuser' : 'Admin'} Account
              </Button>
            </form>
          ) : (
            <div className="mt-5 space-y-5">
              <p className="rounded-lg bg-red-50 p-3 text-sm font-semibold text-danger">{error}</p>
              <Link href="/login" className="block text-center text-sm font-semibold text-primary hover:underline">Return to login</Link>
            </div>
          )}
        </Card>
      </div>
    </main>
  );
}

export default function AcceptAdminInvitationPage() {
  return (
    <Suspense fallback={<main className="flex min-h-screen items-center justify-center text-sm text-neutral-500">Loading…</main>}>
      <AcceptInvitationContent />
    </Suspense>
  );
}
