'use client';

import { useState, useEffect } from 'react';
import { Search, CheckCircle2, XCircle, Award, ChevronDown, ExternalLink } from 'lucide-react';
import { DashboardLayout } from '@/src/components/Layout';
import { Card, Badge, Button } from '@/src/components/ui';
import { cn } from '@/src/lib/utils';
import { apiFetch } from '@/src/lib/apiFetch';

type EndorseStatus = 'pending' | 'endorsed' | 'rejected';

interface EndorsementRequest {
  id: number;
  student_name: string | null;
  skill: string | null;
  cert_url: string;
  source: string;
  uploaded_time: string;
  verified_status: 'PENDING' | 'APPROVED' | 'REJECTED';
}

const toUiStatus = (vs: string): EndorseStatus => {
  if (vs === 'APPROVED') return 'endorsed';
  if (vs === 'REJECTED') return 'rejected';
  return 'pending';
};

const statusVariants: Record<EndorseStatus, 'neutral' | 'success' | 'danger'> = {
  pending: 'neutral', endorsed: 'success', rejected: 'danger',
};

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-MY', { day: 'numeric', month: 'short', year: 'numeric' });
}

export default function EndorsePage() {
  const [requests, setRequests] = useState<EndorsementRequest[]>([]);
  const [filter, setFilter] = useState<'All' | EndorseStatus>('All');
  const [search, setSearch] = useState('');
  const [expanded, setExpanded] = useState<number | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<number | null>(null);

  useEffect(() => {
    apiFetch('/api/resources/certificates/')
      .then(r => r.json())
      .then(data => setRequests(Array.isArray(data) ? data : (data.results ?? [])))
      .catch(() => {})
      .finally(() => setIsLoading(false));
  }, []);

  const endorse = async (id: number, verdict: 'APPROVED' | 'REJECTED') => {
    setActionLoading(id);
    try {
      const res = await apiFetch(`/api/resources/certificates/${id}/endorse/`, {
        method: 'PATCH',
        body: JSON.stringify({ verified_status: verdict }),
      });
      if (res.ok) {
        setRequests(prev => prev.map(r => r.id === id ? { ...r, verified_status: verdict } : r));
        setExpanded(null);
      }
    } catch {
      // silent
    } finally {
      setActionLoading(null);
    }
  };

  const filtered = requests.filter((r) => {
    const uiStatus = toUiStatus(r.verified_status);
    const matchFilter = filter === 'All' || uiStatus === filter;
    const name  = (r.student_name ?? '').toLowerCase();
    const skill = (r.skill ?? '').toLowerCase();
    const matchSearch = name.includes(search.toLowerCase()) || skill.includes(search.toLowerCase());
    return matchFilter && matchSearch;
  });

  const pendingCount = requests.filter(r => r.verified_status === 'PENDING').length;

  return (
    <DashboardLayout title="Endorse Skills">
      <div className="max-w-4xl mx-auto space-y-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h2 className="text-2xl font-bold text-neutral-900 flex items-center gap-3">
              Skill Endorsements
              {pendingCount > 0 && <Badge variant="warning" className="text-xs font-black">{pendingCount} pending</Badge>}
            </h2>
            <p className="text-neutral-500 mt-1 text-sm">Review student certificate submissions and grant or deny endorsements.</p>
          </div>
          <div className="relative w-full md:w-52">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400" size={16} />
            <input type="text" placeholder="Search..." value={search} onChange={(e) => setSearch(e.target.value)}
              className="w-full h-10 pl-10 pr-4 bg-white border border-neutral-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20" />
          </div>
        </div>

        <div className="flex gap-1 p-1 bg-neutral-100 rounded-xl w-fit">
          {(['All', 'pending', 'endorsed', 'rejected'] as const).map((f) => (
            <button key={f} onClick={() => setFilter(f)}
              className={cn('px-4 py-2 text-xs font-bold rounded-lg transition-all capitalize', filter === f ? 'bg-white shadow-sm text-primary' : 'text-neutral-500 hover:text-neutral-900')}>
              {f}
            </button>
          ))}
        </div>

        {isLoading ? (
          <div className="space-y-3">
            {[1, 2, 3].map(i => <div key={i} className="h-20 bg-neutral-100 animate-pulse rounded-2xl" />)}
          </div>
        ) : (
          <div className="space-y-3">
            {filtered.map((req) => {
              const uiStatus = toUiStatus(req.verified_status);
              return (
                <Card key={req.id} className="p-0 overflow-hidden hover:border-primary/20 transition-all">
                  <div className="p-5 flex items-start gap-4">
                    <div className="w-11 h-11 rounded-xl bg-indigo-50 flex items-center justify-center text-primary shrink-0">
                      <Award size={20} />
                    </div>
                    <div className="flex-1">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <h3 className="font-bold text-neutral-900">{req.student_name ?? 'Unknown Student'}</h3>
                          <p className="text-sm font-semibold text-primary mt-0.5">{req.skill ?? 'Unknown Skill'}</p>
                          <p className="text-[10px] font-medium text-neutral-400 mt-0.5">Submitted {formatDate(req.uploaded_time)}</p>
                        </div>
                        <div className="flex items-center gap-2 shrink-0">
                          <Badge variant={statusVariants[uiStatus]} className="capitalize text-[10px] font-black tracking-widest">{uiStatus}</Badge>
                          <Button variant="outline" size="sm" className="h-8 w-8 p-0"
                            onClick={() => setExpanded(expanded === req.id ? null : req.id)}>
                            <ChevronDown size={15} className={cn('transition-transform', expanded === req.id ? 'rotate-180' : '')} />
                          </Button>
                        </div>
                      </div>
                    </div>
                  </div>

                  {expanded === req.id && (
                    <div className="px-5 pb-5 border-t border-neutral-100">
                      <div className="pt-4 space-y-4">
                        <div>
                          <p className="text-[10px] font-black text-neutral-400 uppercase tracking-widest mb-1.5">Certificate / Evidence</p>
                          {req.cert_url ? (
                            <a href={req.cert_url} target="_blank" rel="noopener noreferrer"
                              className="inline-flex items-center gap-1.5 text-sm text-primary font-semibold hover:underline bg-indigo-50 px-3 py-2 rounded-lg border border-indigo-100">
                              <ExternalLink size={13} />
                              View Certificate
                              {req.source && <span className="text-neutral-400 font-normal">— {req.source}</span>}
                            </a>
                          ) : (
                            <p className="text-sm text-neutral-400 italic bg-neutral-50 p-4 rounded-xl border border-neutral-100">No certificate URL provided.</p>
                          )}
                        </div>
                        {uiStatus === 'pending' && (
                          <div className="flex gap-3">
                            <Button size="sm"
                              className="h-9 text-xs bg-success hover:bg-success/90 text-white flex items-center gap-1.5"
                              disabled={actionLoading === req.id}
                              onClick={() => endorse(req.id, 'APPROVED')}>
                              <CheckCircle2 size={14} />
                              {actionLoading === req.id ? 'Saving…' : 'Endorse Skill'}
                            </Button>
                            <Button size="sm" variant="outline"
                              className="h-9 text-xs text-danger border-danger/30 hover:bg-danger/5 flex items-center gap-1.5"
                              disabled={actionLoading === req.id}
                              onClick={() => endorse(req.id, 'REJECTED')}>
                              <XCircle size={14} /> Reject
                            </Button>
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </Card>
              );
            })}
          </div>
        )}

        {!isLoading && filtered.length === 0 && (
          <div className="py-20 text-center">
            <Award size={48} className="mx-auto text-neutral-200 mb-4" />
            <h3 className="text-xl font-bold text-neutral-900">No requests found</h3>
            <p className="text-neutral-500 mt-1 text-sm">
              {search || filter !== 'All' ? 'Try adjusting your search or filter.' : 'Certificate submissions will appear here.'}
            </p>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
