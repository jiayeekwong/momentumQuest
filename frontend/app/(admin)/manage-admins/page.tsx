'use client';

import { useCallback, useEffect, useState } from 'react';
import { Mail, RefreshCw, ShieldCheck, UserPlus, XCircle } from 'lucide-react';
import { DashboardLayout } from '@/src/components/Layout';
import { Badge, Button, Card, Input } from '@/src/components/ui';
import { useAuth } from '@/src/context/AuthContext';
import { apiFetch } from '@/src/lib/apiFetch';
import { useDepartments } from '@/src/lib/privacyNotice';

type InvitationStatus = 'PENDING' | 'ACCEPTED' | 'REVOKED' | 'EXPIRED';

interface AdminInvitation {
  id: number;
  email: string;
  department: string;
  status: InvitationStatus;
  invited_by: string | null;
  expires_at: string;
  accepted_at: string | null;
  created_at: string;
}

const statusVariant = {
  PENDING: 'warning',
  ACCEPTED: 'success',
  REVOKED: 'danger',
  EXPIRED: 'neutral',
} as const;

function apiError(data: unknown, fallback: string): string {
  if (!data || typeof data !== 'object') return fallback;
  const record = data as Record<string, unknown>;
  if (typeof record.detail === 'string') return record.detail;
  for (const value of Object.values(record)) {
    if (Array.isArray(value) && value.length) return String(value[0]);
    if (typeof value === 'string') return value;
  }
  return fallback;
}

export default function ManageAdminsPage() {
  const { user } = useAuth();
  const { departments } = useDepartments();
  const [email, setEmail] = useState('');
  const [department, setDepartment] = useState('');
  const [invitations, setInvitations] = useState<AdminInvitation[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSending, setIsSending] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const loadInvitations = useCallback(async () => {
    setIsLoading(true);
    try {
      const response = await apiFetch('/api/auth/admin-invitations/');
      const data = await response.json().catch(() => null);
      if (!response.ok) throw new Error(apiError(data, 'Could not load invitations.'));
      setInvitations(Array.isArray(data) ? data : (data?.results ?? []));
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Could not load invitations.');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!user?.isSuperuser) return;
    let cancelled = false;
    apiFetch('/api/auth/admin-invitations/')
      .then(async response => {
        const data = await response.json().catch(() => null);
        if (!response.ok) throw new Error(apiError(data, 'Could not load invitations.'));
        if (!cancelled) setInvitations(Array.isArray(data) ? data : (data?.results ?? []));
      })
      .catch(loadError => {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : 'Could not load invitations.');
        }
      })
      .finally(() => { if (!cancelled) setIsLoading(false); });
    return () => { cancelled = true; };
  }, [user?.isSuperuser]);

  async function sendInvitation(event: React.FormEvent) {
    event.preventDefault();
    setError('');
    setSuccess('');
    setIsSending(true);
    try {
      const response = await apiFetch('/api/auth/admin-invitations/', {
        method: 'POST',
        body: JSON.stringify({ email: email.trim(), department }),
      });
      const data = await response.json().catch(() => null);
      if (!response.ok) throw new Error(apiError(data, 'Could not send the invitation.'));
      setInvitations(current => [data, ...current]);
      setEmail('');
      setDepartment('');
      setSuccess(`Invitation sent to ${data.email}.`);
    } catch (sendError) {
      setError(sendError instanceof Error ? sendError.message : 'Could not send the invitation.');
    } finally {
      setIsSending(false);
    }
  }

  async function updateInvitation(invitation: AdminInvitation, action: 'resend' | 'revoke') {
    setError('');
    setSuccess('');
    setBusyId(invitation.id);
    try {
      const response = await apiFetch(
        `/api/auth/admin-invitations/${invitation.id}/${action}/`,
        { method: 'POST' },
      );
      const data = await response.json().catch(() => null);
      if (!response.ok) throw new Error(apiError(data, `Could not ${action} the invitation.`));
      setInvitations(current => current.map(item => item.id === data.id ? data : item));
      setSuccess(action === 'resend'
        ? `A fresh invitation was sent to ${invitation.email}.`
        : `Invitation for ${invitation.email} was revoked.`);
    } catch (updateError) {
      setError(updateError instanceof Error ? updateError.message : `Could not ${action} the invitation.`);
    } finally {
      setBusyId(null);
    }
  }

  if (user && !user.isSuperuser) {
    return (
      <DashboardLayout title="Manage Admins">
        <Card className="mx-auto max-w-xl text-center">
          <ShieldCheck className="mx-auto mb-4 text-neutral-300" size={44} />
          <h1 className="text-xl font-bold text-neutral-900">Superadmin access required</h1>
          <p className="mt-2 text-sm text-neutral-500">
            Department administrators cannot create or invite other administrators.
          </p>
        </Card>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout title="Manage Admins">
      <div className="mx-auto max-w-5xl space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-neutral-900">Administrator invitations</h1>
          <p className="mt-1 text-sm text-neutral-500">
            Assign a department and send a single-use registration link. Links expire automatically.
          </p>
        </div>

        <Card>
          <form onSubmit={sendInvitation} className="grid gap-4 md:grid-cols-[1fr_1fr_auto] md:items-end">
            <Input
              label="Administrator Email"
              type="email"
              value={email}
              onChange={event => setEmail(event.target.value)}
              placeholder="admin@university.edu"
              required
            />
            <div className="space-y-1.5">
              <label className="block text-[10px] font-black uppercase tracking-widest text-neutral-900">
                Department
              </label>
              <select
                value={department}
                onChange={event => setDepartment(event.target.value)}
                required
                className="h-10 w-full rounded-lg border border-neutral-300 bg-white px-3 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
              >
                <option value="">Select a department</option>
                {departments.map(name => <option key={name} value={name}>{name}</option>)}
              </select>
            </div>
            <Button type="submit" isLoading={isSending} disabled={!department || isSending}>
              <UserPlus size={16} /> Send Invitation
            </Button>
          </form>

          {(error || success) && (
            <p className={`mt-4 rounded-lg px-3 py-2 text-sm font-semibold ${
              error ? 'bg-red-50 text-danger' : 'bg-emerald-50 text-success'
            }`}>
              {error || success}
            </p>
          )}
        </Card>

        <Card className="p-0">
          <div className="flex items-center justify-between border-b border-neutral-100 px-6 py-4">
            <div>
              <h2 className="font-bold text-neutral-900">Invitation history</h2>
              <p className="text-xs text-neutral-500">Accepted invitations are retained for audit history.</p>
            </div>
            <button
              type="button"
              onClick={() => void loadInvitations()}
              aria-label="Refresh invitations"
              className="rounded-lg p-2 text-neutral-500 hover:bg-neutral-100"
            >
              <RefreshCw size={17} />
            </button>
          </div>

          {isLoading ? (
            <div className="space-y-3 p-6">
              {[0, 1, 2].map(item => <div key={item} className="h-16 animate-pulse rounded-lg bg-neutral-100" />)}
            </div>
          ) : invitations.length === 0 ? (
            <div className="px-6 py-14 text-center text-sm text-neutral-400">
              No administrator invitations have been sent.
            </div>
          ) : (
            <div className="divide-y divide-neutral-100">
              {invitations.map(invitation => (
                <div key={invitation.id} className="flex flex-col gap-4 px-6 py-4 sm:flex-row sm:items-center">
                  <div className="flex min-w-0 flex-1 items-start gap-3">
                    <span className="mt-0.5 rounded-lg bg-indigo-50 p-2 text-primary"><Mail size={16} /></span>
                    <div className="min-w-0">
                      <p className="truncate text-sm font-bold text-neutral-900">{invitation.email}</p>
                      <p className="mt-0.5 text-xs text-neutral-500">
                        {invitation.department} · sent {new Date(invitation.created_at).toLocaleDateString('en-MY')}
                      </p>
                    </div>
                  </div>
                  <Badge variant={statusVariant[invitation.status]}>{invitation.status.toLowerCase()}</Badge>
                  <div className="flex gap-2">
                    {invitation.status !== 'ACCEPTED' && (
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        disabled={busyId === invitation.id}
                        onClick={() => void updateInvitation(invitation, 'resend')}
                      >
                        <RefreshCw size={13} /> Resend
                      </Button>
                    )}
                    {invitation.status === 'PENDING' && (
                      <Button
                        type="button"
                        size="sm"
                        variant="danger"
                        disabled={busyId === invitation.id}
                        onClick={() => void updateInvitation(invitation, 'revoke')}
                      >
                        <XCircle size={13} /> Revoke
                      </Button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </DashboardLayout>
  );
}
