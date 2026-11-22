'use client';

import { useState, useEffect } from 'react';
import { AlertTriangle, CheckCircle2, XCircle, Clock, GraduationCap, X, FileText, ExternalLink, Megaphone } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { DashboardLayout } from '@/src/components/Layout';
import { Card, Badge, Button } from '@/src/components/ui';
import { cn } from '@/src/lib/utils';
import { apiFetch } from '@/src/lib/apiFetch';
import { notifyPendingReviewsChanged } from '@/src/lib/adminReviewEvents';
import { RichText } from '@/src/lib/richText';

type ApprovalStatus = 'pending' | 'approved' | 'rejected' | 'withdrawn';
type ApprovalKind = 'training' | 'announcement';

interface ApprovalItem {
  id: number;
  title: string;
  submittedBy: string;
  submittedDate: string;
  status: ApprovalStatus;
  details: string;
  skill: string | null;
  duration: string;
  supportingDoc: string | null;
  kind: ApprovalKind;
  rejectionReason: string;
  department: string | null;
  visibility: 'DEPARTMENT' | 'EVERYONE' | null;
}

const statusVariants: Record<ApprovalStatus, 'neutral' | 'success' | 'danger'> = {
  pending: 'neutral', approved: 'success', rejected: 'danger', withdrawn: 'neutral',
};

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-MY', { day: 'numeric', month: 'short', year: 'numeric' });
}

function isImageUrl(url: string): boolean {
  return /\.(jpg|jpeg|png|gif|webp|svg)(\?|$)/i.test(url);
}

// Strip HTML tags for short plain-text previews (full HTML is rendered in the modal).
function stripHtml(html: string): string {
  return html.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
}

function apiErrorMessage(data: unknown, fallback: string): string {
  if (!data || typeof data !== 'object') return fallback;
  const response = data as Record<string, unknown>;
  if (typeof response.detail === 'string') return response.detail;
  for (const value of Object.values(response)) {
    if (Array.isArray(value) && value.length) return String(value[0]);
    if (typeof value === 'string') return value;
  }
  return fallback;
}

// ─── Detail Modal ──────────────────────────────────────────────────────────────

function DetailModal({ item, onClose }: { item: ApprovalItem; onClose: () => void }) {
  const typeLabel = item.kind === 'training' ? 'Training Programme' : 'Company Announcement';
  return (
    <motion.div key="detail-backdrop"
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm px-4 py-8 overflow-y-auto"
      onClick={onClose}>
      <motion.div
        initial={{ scale: 0.96, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.96, opacity: 0 }}
        transition={{ type: 'spring', stiffness: 300, damping: 30 }}
        className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl my-auto"
        onClick={e => e.stopPropagation()}>

        <div className="flex items-start justify-between gap-4 p-7 border-b border-neutral-100">
          <div className="flex-1 min-w-0">
            <div className="flex flex-wrap items-center gap-2 mb-3">
              <p className="text-[10px] font-black text-neutral-400 uppercase tracking-widest">{typeLabel}</p>
              {item.skill && <Badge variant="primary" className="text-[9px] font-black tracking-widest">{item.skill}</Badge>}
              <Badge variant={statusVariants[item.status]} className="capitalize text-[9px] font-black tracking-widest">{item.status}</Badge>
            </div>
            <h2 className="text-xl font-black text-neutral-900 leading-tight">{item.title}</h2>
            <div className="flex flex-wrap items-center gap-4 mt-2 text-[11px] text-neutral-400 font-medium">
              <span>By {item.submittedBy}</span>
              {item.department && <span>{item.department}</span>}
              {item.duration && <span className="flex items-center gap-1"><Clock size={11} /> {item.duration}</span>}
              <span>Submitted {item.submittedDate}</span>
            </div>
          </div>
          <button onClick={onClose} className="w-8 h-8 shrink-0 flex items-center justify-center rounded-lg hover:bg-neutral-100 text-neutral-400">
            <X size={18} />
          </button>
        </div>

        <div className="p-7 space-y-5">
          <RichText className="text-sm text-neutral-700 leading-relaxed rich-text"
            html={item.details} />

          {item.rejectionReason && (
            <p className="p-3 rounded-lg bg-red-50 border border-red-100 text-sm text-red-700">
              <strong>Review note:</strong> {item.rejectionReason}
            </p>
          )}

          {item.supportingDoc && (
            <div className="border border-neutral-200 rounded-xl overflow-hidden">
              {isImageUrl(item.supportingDoc) ? (
                <img src={item.supportingDoc} alt="Attachment" className="w-full max-h-80 object-contain bg-neutral-50" />
              ) : (
                <a href={item.supportingDoc} target="_blank" rel="noopener noreferrer"
                  className="flex items-center gap-3 p-4 hover:bg-neutral-50 transition-colors">
                  <div className="w-10 h-10 bg-indigo-50 rounded-lg flex items-center justify-center text-primary shrink-0">
                    <FileText size={20} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-bold text-neutral-900">Attached Document</p>
                    <p className="text-xs text-neutral-400 truncate">{item.supportingDoc}</p>
                  </div>
                  <ExternalLink size={15} className="text-neutral-400 shrink-0" />
                </a>
              )}
            </div>
          )}
        </div>

        <div className="px-7 pb-7">
          <Button variant="outline" fullWidth onClick={onClose}>Close</Button>
        </div>
      </motion.div>
    </motion.div>
  );
}

function RejectionModal({
  item,
  reason,
  error,
  isSubmitting,
  onReasonChange,
  onClose,
  onSubmit,
}: {
  item: ApprovalItem;
  reason: string;
  error: string;
  isSubmitting: boolean;
  onReasonChange: (value: string) => void;
  onClose: () => void;
  onSubmit: (event: React.FormEvent) => void;
}) {
  const typeLabel = item.kind === 'training' ? 'training programme' : 'announcement';
  const rejectionPlaceholder = item.kind === 'training'
    ? 'For example: Please include the programme schedule and clarify the learning outcomes.'
    : 'For example: Please include the event date and clarify how students can participate.';

  return (
    <motion.div
      key="rejection-backdrop"
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      className="fixed inset-0 z-[60] flex items-center justify-center bg-neutral-950/45 px-4 py-8 backdrop-blur-sm"
      onClick={() => { if (!isSubmitting) onClose(); }}
      onKeyDown={event => {
        if (event.key === 'Escape' && !isSubmitting) onClose();
      }}
    >
      <motion.form
        role="dialog"
        aria-modal="true"
        aria-labelledby="rejection-title"
        aria-describedby="rejection-description"
        initial={{ scale: 0.95, opacity: 0, y: 10 }}
        animate={{ scale: 1, opacity: 1, y: 0 }}
        exit={{ scale: 0.96, opacity: 0, y: 8 }}
        transition={{ type: 'spring', stiffness: 320, damping: 28 }}
        onSubmit={onSubmit}
        onClick={event => event.stopPropagation()}
        className="w-full max-w-lg overflow-hidden rounded-2xl border border-neutral-200 bg-white shadow-2xl"
      >
        <div className="flex items-start gap-4 border-b border-neutral-100 px-6 py-5">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-red-50 text-danger">
            <AlertTriangle size={22} />
          </span>
          <div className="min-w-0 flex-1">
            <h2 id="rejection-title" className="text-lg font-black text-neutral-900">
              Reject {item.kind === 'training' ? 'Training Programme' : 'Announcement'}
            </h2>
            <p id="rejection-description" className="mt-1 text-sm leading-relaxed text-neutral-500">
              Explain what needs to be corrected. The company will see this reason and can revise its submission.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={isSubmitting}
            aria-label="Close rejection dialog"
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-neutral-400 hover:bg-neutral-100 hover:text-neutral-700 disabled:opacity-40"
          >
            <X size={17} />
          </button>
        </div>

        <div className="space-y-5 px-6 py-5">
          <div className="rounded-xl border border-neutral-200 bg-neutral-50 px-4 py-3">
            <p className="text-[10px] font-black uppercase tracking-widest text-neutral-400">{typeLabel}</p>
            <p className="mt-1 truncate text-sm font-bold text-neutral-900">{item.title}</p>
            <p className="mt-0.5 text-xs text-neutral-500">Submitted by {item.submittedBy}</p>
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between gap-3">
              <label htmlFor="rejection-reason" className="text-[10px] font-black uppercase tracking-widest text-neutral-900">
                Reason for rejection
              </label>
              <span className="text-[10px] font-semibold tabular-nums text-neutral-400">{reason.length}/500</span>
            </div>
            <textarea
              id="rejection-reason"
              value={reason}
              onChange={event => onReasonChange(event.target.value)}
              maxLength={500}
              rows={5}
              autoFocus
              disabled={isSubmitting}
              aria-invalid={Boolean(error)}
              aria-describedby={error ? 'rejection-error' : undefined}
              placeholder={rejectionPlaceholder}
              className={cn(
                'w-full resize-none rounded-xl border bg-white px-3.5 py-3 text-sm leading-relaxed text-neutral-800 outline-none transition-all',
                'placeholder:text-neutral-400 focus:border-primary focus:ring-2 focus:ring-primary/15 disabled:bg-neutral-50',
                error ? 'border-danger focus:border-danger focus:ring-danger/15' : 'border-neutral-300',
              )}
            />
            {error && <p id="rejection-error" role="alert" className="text-xs font-semibold text-danger">{error}</p>}
          </div>
        </div>

        <div className="flex flex-col-reverse gap-3 border-t border-neutral-100 bg-neutral-50/70 px-6 py-4 sm:flex-row sm:justify-end">
          <Button type="button" variant="outline" onClick={onClose} disabled={isSubmitting}>
            Cancel
          </Button>
          <Button type="submit" variant="danger" isLoading={isSubmitting} disabled={isSubmitting || !reason.trim()}>
            <XCircle size={15} /> Reject {item.kind === 'training' ? 'Programme' : 'Announcement'}
          </Button>
        </div>
      </motion.form>
    </motion.div>
  );
}

// ─── Page ────────────────────────────────────────────────────────────────────

export default function ApprovalsPage() {
  const [items, setItems] = useState<ApprovalItem[]>([]);
  const [kind, setKind] = useState<ApprovalKind>('training');
  const [filter, setFilter] = useState<'All' | ApprovalStatus>('All');
  const [isLoading, setIsLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<number | null>(null);
  const [detailItem, setDetailItem] = useState<ApprovalItem | null>(null);
  const [rejectionItem, setRejectionItem] = useState<ApprovalItem | null>(null);
  const [rejectionReason, setRejectionReason] = useState('');
  const [rejectionError, setRejectionError] = useState('');
  const [pageError, setPageError] = useState('');
  const [visibilityByItem, setVisibilityByItem] = useState<Record<number, 'DEPARTMENT' | 'EVERYONE'>>({});

  useEffect(() => {
    Promise.all([
      apiFetch('/api/resources/training/admin/').then(r => r.json()),
      apiFetch('/api/dashboard/admin/announcement-submissions/').then(r => r.json()),
    ])
      .then(([trainingResponse, announcementResponse]) => {
        const trainingData = (Array.isArray(trainingResponse)
          ? trainingResponse : trainingResponse.results ?? []) as Array<{
        id: number; title: string; company_name: string | null;
        submission_time: string; approval_status: string; description: string;
        skill: string | null; programme_duration: string; supporting_doc: string | null;
        department: string | null; visibility: 'DEPARTMENT' | 'EVERYONE' | null;
        rejection_reason: string;
        }>;
        const announcementData = (Array.isArray(announcementResponse)
          ? announcementResponse : announcementResponse.results ?? []) as Array<{
          id: number; title: string; author_name: string | null;
          submitted_at: string; approval_status: string; message: string;
          supporting_doc: string | null; rejection_reason: string;
        }>;
        setItems([
          ...trainingData.map(t => ({
          id:            t.id,
          title:         t.title,
          submittedBy:   t.company_name ?? 'Unknown Company',
          submittedDate: formatDate(t.submission_time),
          status:        (t.approval_status.toLowerCase() as ApprovalStatus),
          details:       t.description || 'No description provided.',
          skill:         t.skill,
          duration:      t.programme_duration || '',
          supportingDoc: t.supporting_doc,
          kind:           'training' as const,
          rejectionReason: t.rejection_reason || '',
          department: t.department,
          visibility: t.visibility,
          })),
          ...announcementData.map(a => ({
            id: a.id,
            title: a.title,
            submittedBy: a.author_name ?? 'Unknown Company',
            submittedDate: formatDate(a.submitted_at),
            status: a.approval_status.toLowerCase() as ApprovalStatus,
            details: a.message || 'No announcement body provided.',
            skill: null,
            duration: '',
            supportingDoc: a.supporting_doc,
            kind: 'announcement' as const,
            rejectionReason: a.rejection_reason || '',
            department: null,
            visibility: null,
          })),
        ]);
      })
      .catch(() => {})
      .finally(() => setIsLoading(false));
  }, []);

  const updateStatus = async (
    item: ApprovalItem,
    newStatus: 'APPROVED' | 'REJECTED',
    reason = '',
  ): Promise<string | null> => {
    setActionLoading(item.id);
    try {
      const endpoint = item.kind === 'training'
        ? `/api/resources/training/admin/${item.id}/review/`
        : `/api/dashboard/admin/announcement-submissions/${item.id}/review/`;
      const res = await apiFetch(endpoint, {
        method: 'PATCH',
        body: JSON.stringify({
          approval_status: newStatus,
          ...(item.kind === 'training' && newStatus === 'APPROVED'
            ? { visibility: visibilityByItem[item.id] ?? 'DEPARTMENT' }
            : {}),
          ...(reason ? { rejection_reason: reason } : {}),
        }),
      });
      if (res.ok) {
        const ui = newStatus.toLowerCase() as ApprovalStatus;
        setItems(prev => prev.map(row => row.id === item.id && row.kind === item.kind
          ? { ...row, status: ui, rejectionReason: reason }
          : row));
        setDetailItem(prev => prev && prev.id === item.id && prev.kind === item.kind
          ? { ...prev, status: ui, rejectionReason: reason }
          : prev);
        notifyPendingReviewsChanged();
        return null;
      }
      const data = await res.json().catch(() => null);
      return apiErrorMessage(data, 'The review could not be saved. Please try again.');
    } catch {
      return 'Network error. Check your connection and try again.';
    } finally {
      setActionLoading(null);
    }
  };

  const approveItem = async (item: ApprovalItem) => {
    setPageError('');
    const error = await updateStatus(item, 'APPROVED');
    if (error) setPageError(error);
  };

  const openRejectionModal = (item: ApprovalItem) => {
    setRejectionItem(item);
    setRejectionReason('');
    setRejectionError('');
    setPageError('');
  };

  const closeRejectionModal = () => {
    if (actionLoading !== null) return;
    setRejectionItem(null);
    setRejectionReason('');
    setRejectionError('');
  };

  const submitRejection = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!rejectionItem) return;
    const reason = rejectionReason.trim();
    if (!reason) {
      setRejectionError('Enter a reason so the company knows what to correct.');
      return;
    }

    setRejectionError('');
    const error = await updateStatus(rejectionItem, 'REJECTED', reason);
    if (error) {
      setRejectionError(error);
      return;
    }
    setRejectionItem(null);
    setRejectionReason('');
  };

  const kindItems = items.filter(item => item.kind === kind);
  const filtered = kindItems.filter((i) => filter === 'All' || i.status === filter);
  const pendingCount = kindItems.filter((i) => i.status === 'pending').length;

  return (
    <DashboardLayout title="Approvals">
      <div className="max-w-4xl mx-auto space-y-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h2 className="text-2xl font-bold text-neutral-900 flex items-center gap-3">
              Pending Approvals
              {pendingCount > 0 && <Badge variant="warning" className="text-xs font-black">{pendingCount} pending</Badge>}
            </h2>
            <p className="text-neutral-500 mt-1 text-sm">Review company submissions before they become visible to students.</p>
          </div>
          <div className="flex gap-1 p-1 bg-neutral-100 rounded-xl">
            {(['All', 'pending', 'approved', 'rejected'] as const).map((f) => (
              <button key={f} onClick={() => setFilter(f)}
                className={cn('px-4 py-2 text-xs font-bold rounded-lg transition-all capitalize', filter === f ? 'bg-white shadow-sm text-primary' : 'text-neutral-500 hover:text-neutral-900')}>
                {f}
              </button>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2 p-1 bg-neutral-100 rounded-xl">
          <button onClick={() => { setKind('training'); setFilter('All'); }}
            className={cn('px-4 py-2.5 rounded-lg text-sm font-bold flex items-center justify-center gap-2',
              kind === 'training' ? 'bg-white shadow-sm text-primary' : 'text-neutral-500')}>
            <GraduationCap size={16} /> Training Programmes
          </button>
          <button onClick={() => { setKind('announcement'); setFilter('All'); }}
            className={cn('px-4 py-2.5 rounded-lg text-sm font-bold flex items-center justify-center gap-2',
              kind === 'announcement' ? 'bg-white shadow-sm text-primary' : 'text-neutral-500')}>
            <Megaphone size={16} /> Announcements
          </button>
        </div>

        {pageError && (
          <p role="alert" className="rounded-xl border border-red-100 bg-red-50 px-4 py-3 text-sm font-semibold text-danger">
            {pageError}
          </p>
        )}

        {isLoading ? (
          <div className="space-y-4">
            {[1, 2, 3].map(i => (
              <div key={i} className="h-32 bg-neutral-100 animate-pulse rounded-2xl" />
            ))}
          </div>
        ) : (
          <div className="space-y-4">
            {filtered.map((item) => (
              <Card key={`${item.kind}-${item.id}`} className="p-6 hover:border-primary/20 transition-all">
                <div className="flex flex-col md:flex-row md:items-start gap-5">
                  <div className="w-12 h-12 rounded-xl flex items-center justify-center shrink-0 bg-indigo-50 text-primary">
                    {item.kind === 'training' ? <GraduationCap size={22} /> : <Megaphone size={22} />}
                  </div>
                  <div className="flex-1">
                    <div className="flex flex-col md:flex-row md:items-start justify-between gap-2 mb-1">
                      <div>
                        <p className="text-[10px] font-black text-neutral-400 uppercase tracking-widest mb-0.5">
                          {item.kind === 'training' ? 'Training Programme' : 'Company Announcement'}
                        </p>
                        <button type="button" onClick={() => setDetailItem(item)}
                          className="text-left text-base font-bold text-neutral-900 hover:text-primary hover:underline underline-offset-2 transition-colors">
                          {item.title}
                        </button>
                      </div>
                      <Badge variant={statusVariants[item.status]} className="capitalize text-[10px] font-black tracking-widest shrink-0">{item.status}</Badge>
                    </div>
                    <p className="text-xs font-semibold text-neutral-500 mb-1">
                      By {item.submittedBy} · {item.submittedDate}
                      {item.department && <span> · {item.department}</span>}
                      {item.supportingDoc && (
                        <span className="inline-flex items-center gap-1 ml-2 text-primary"><FileText size={10} /> Attachment</span>
                      )}
                    </p>
                    <p className="text-sm text-neutral-600 leading-relaxed line-clamp-2">{stripHtml(item.details)}</p>
                    {item.status === 'pending' && (
                      <div className="flex flex-wrap gap-3 mt-4">
                        {item.kind === 'training' && (
                          <select
                            aria-label={`Visibility for ${item.title}`}
                            value={visibilityByItem[item.id] ?? 'DEPARTMENT'}
                            onChange={event => setVisibilityByItem(previous => ({
                              ...previous,
                              [item.id]: event.target.value as 'DEPARTMENT' | 'EVERYONE',
                            }))}
                            className="h-9 px-3 rounded-lg border border-neutral-300 bg-white text-xs font-bold text-neutral-700"
                          >
                            <option value="DEPARTMENT">{item.department ?? 'Department'} students only</option>
                            <option value="EVERYONE">All students</option>
                          </select>
                        )}
                        <Button size="sm"
                          className="h-9 text-xs bg-success hover:bg-success/90 text-white flex items-center gap-1.5"
                          disabled={actionLoading === item.id}
                          onClick={() => void approveItem(item)}>
                          <CheckCircle2 size={14} />
                          {actionLoading === item.id ? 'Saving…' : 'Approve'}
                        </Button>
                        <Button size="sm" variant="outline"
                          className="h-9 text-xs text-danger border-danger/30 hover:bg-danger/5 flex items-center gap-1.5"
                          disabled={actionLoading === item.id}
                          onClick={() => openRejectionModal(item)}>
                          <XCircle size={14} /> Reject
                        </Button>
                      </div>
                    )}
                  </div>
                </div>
              </Card>
            ))}
          </div>
        )}

        {!isLoading && filtered.length === 0 && (
          <div className="py-20 text-center">
            <div className="w-20 h-20 bg-neutral-100 rounded-full flex items-center justify-center mx-auto mb-4 text-neutral-300">
              <Clock size={40} />
            </div>
            <h3 className="text-xl font-bold text-neutral-900">All clear!</h3>
            <p className="text-neutral-500 mt-1">No items matching this filter.</p>
          </div>
        )}
      </div>

      {/* Detail modal */}
      <AnimatePresence>
        {detailItem && <DetailModal item={detailItem} onClose={() => setDetailItem(null)} />}
      </AnimatePresence>

      <AnimatePresence>
        {rejectionItem && (
          <RejectionModal
            item={rejectionItem}
            reason={rejectionReason}
            error={rejectionError}
            isSubmitting={actionLoading === rejectionItem.id}
            onReasonChange={value => {
              setRejectionReason(value);
              if (rejectionError) setRejectionError('');
            }}
            onClose={closeRejectionModal}
            onSubmit={submitRejection}
          />
        )}
      </AnimatePresence>
    </DashboardLayout>
  );
}
