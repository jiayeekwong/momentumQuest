'use client';

import { useState, useEffect } from 'react';
import { CheckCircle2, XCircle, Clock, GraduationCap, X, FileText, ExternalLink } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { DashboardLayout } from '@/src/components/Layout';
import { Card, Badge, Button } from '@/src/components/ui';
import { cn } from '@/src/lib/utils';
import { apiFetch } from '@/src/lib/apiFetch';

type ApprovalStatus = 'pending' | 'approved' | 'rejected';

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
}

const statusVariants: Record<ApprovalStatus, 'neutral' | 'success' | 'danger'> = {
  pending: 'neutral', approved: 'success', rejected: 'danger',
};

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-MY', { day: 'numeric', month: 'short', year: 'numeric' });
}

function isImageUrl(url: string): boolean {
  return /\.(jpg|jpeg|png|gif|webp|svg)(\?|$)/i.test(url);
}

// ─── Detail Modal ──────────────────────────────────────────────────────────────

function DetailModal({ item, onClose }: { item: ApprovalItem; onClose: () => void }) {
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
              <p className="text-[10px] font-black text-neutral-400 uppercase tracking-widest">Training Programme</p>
              {item.skill && <Badge variant="primary" className="text-[9px] font-black tracking-widest">{item.skill}</Badge>}
              <Badge variant={statusVariants[item.status]} className="capitalize text-[9px] font-black tracking-widest">{item.status}</Badge>
            </div>
            <h2 className="text-xl font-black text-neutral-900 leading-tight">{item.title}</h2>
            <div className="flex flex-wrap items-center gap-4 mt-2 text-[11px] text-neutral-400 font-medium">
              <span>By {item.submittedBy}</span>
              {item.duration && <span className="flex items-center gap-1"><Clock size={11} /> {item.duration}</span>}
              <span>Submitted {item.submittedDate}</span>
            </div>
          </div>
          <button onClick={onClose} className="w-8 h-8 shrink-0 flex items-center justify-center rounded-lg hover:bg-neutral-100 text-neutral-400">
            <X size={18} />
          </button>
        </div>

        <div className="p-7 space-y-5">
          <div className="text-sm text-neutral-700 leading-relaxed rich-text"
            dangerouslySetInnerHTML={{ __html: item.details }} />

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

// ─── Page ────────────────────────────────────────────────────────────────────

export default function ApprovalsPage() {
  const [items, setItems] = useState<ApprovalItem[]>([]);
  const [filter, setFilter] = useState<'All' | ApprovalStatus>('All');
  const [isLoading, setIsLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<number | null>(null);
  const [detailItem, setDetailItem] = useState<ApprovalItem | null>(null);

  useEffect(() => {
    apiFetch('/api/resources/training/admin/')
      .then(r => r.json())
      .then((data: Array<{
        id: number; title: string; company_name: string | null;
        submission_time: string; approval_status: string; description: string;
        skill: string | null; programme_duration: string; supporting_doc: string | null;
      }>) => {
        setItems(data.map(t => ({
          id:            t.id,
          title:         t.title,
          submittedBy:   t.company_name ?? 'Unknown Company',
          submittedDate: formatDate(t.submission_time),
          status:        (t.approval_status.toLowerCase() as ApprovalStatus),
          details:       t.description || 'No description provided.',
          skill:         t.skill,
          duration:      t.programme_duration || '',
          supportingDoc: t.supporting_doc,
        })));
      })
      .catch(() => {})
      .finally(() => setIsLoading(false));
  }, []);

  const updateStatus = async (id: number, newStatus: 'APPROVED' | 'REJECTED') => {
    setActionLoading(id);
    try {
      const res = await apiFetch(`/api/resources/training/admin/${id}/review/`, {
        method: 'PATCH',
        body: JSON.stringify({ approval_status: newStatus }),
      });
      if (res.ok) {
        const ui = newStatus.toLowerCase() as ApprovalStatus;
        setItems(prev => prev.map(item => item.id === id ? { ...item, status: ui } : item));
        setDetailItem(prev => prev && prev.id === id ? { ...prev, status: ui } : prev);
      }
    } catch {
      // silent
    } finally {
      setActionLoading(null);
    }
  };

  const filtered = items.filter((i) => filter === 'All' || i.status === filter);
  const pendingCount = items.filter((i) => i.status === 'pending').length;

  return (
    <DashboardLayout title="Approvals">
      <div className="max-w-4xl mx-auto space-y-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h2 className="text-2xl font-bold text-neutral-900 flex items-center gap-3">
              Pending Approvals
              {pendingCount > 0 && <Badge variant="warning" className="text-xs font-black">{pendingCount} pending</Badge>}
            </h2>
            <p className="text-neutral-500 mt-1 text-sm">Review and approve training programme submissions from companies.</p>
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

        {isLoading ? (
          <div className="space-y-4">
            {[1, 2, 3].map(i => (
              <div key={i} className="h-32 bg-neutral-100 animate-pulse rounded-2xl" />
            ))}
          </div>
        ) : (
          <div className="space-y-4">
            {filtered.map((item) => (
              <Card key={item.id} className="p-6 hover:border-primary/20 transition-all">
                <div className="flex flex-col md:flex-row md:items-start gap-5">
                  <div className="w-12 h-12 rounded-xl flex items-center justify-center shrink-0 bg-indigo-50 text-primary">
                    <GraduationCap size={22} />
                  </div>
                  <div className="flex-1">
                    <div className="flex flex-col md:flex-row md:items-start justify-between gap-2 mb-1">
                      <div>
                        <p className="text-[10px] font-black text-neutral-400 uppercase tracking-widest mb-0.5">Training Programme</p>
                        <button type="button" onClick={() => setDetailItem(item)}
                          className="text-left text-base font-bold text-neutral-900 hover:text-primary hover:underline underline-offset-2 transition-colors">
                          {item.title}
                        </button>
                      </div>
                      <Badge variant={statusVariants[item.status]} className="capitalize text-[10px] font-black tracking-widest shrink-0">{item.status}</Badge>
                    </div>
                    <p className="text-xs font-semibold text-neutral-500 mb-1">
                      By {item.submittedBy} · {item.submittedDate}
                      {item.supportingDoc && (
                        <span className="inline-flex items-center gap-1 ml-2 text-primary"><FileText size={10} /> Attachment</span>
                      )}
                    </p>
                    <p className="text-sm text-neutral-600 leading-relaxed line-clamp-2">{item.details}</p>
                    {item.status === 'pending' && (
                      <div className="flex gap-3 mt-4">
                        <Button size="sm"
                          className="h-9 text-xs bg-success hover:bg-success/90 text-white flex items-center gap-1.5"
                          disabled={actionLoading === item.id}
                          onClick={() => updateStatus(item.id, 'APPROVED')}>
                          <CheckCircle2 size={14} />
                          {actionLoading === item.id ? 'Saving…' : 'Approve'}
                        </Button>
                        <Button size="sm" variant="outline"
                          className="h-9 text-xs text-danger border-danger/30 hover:bg-danger/5 flex items-center gap-1.5"
                          disabled={actionLoading === item.id}
                          onClick={() => updateStatus(item.id, 'REJECTED')}>
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
    </DashboardLayout>
  );
}
