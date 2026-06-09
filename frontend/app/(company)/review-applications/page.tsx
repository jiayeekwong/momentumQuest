'use client';

import { useEffect, useState } from 'react';
import { Search, CheckCircle2, XCircle, Clock, ChevronDown, Star } from 'lucide-react';
import { DashboardLayout } from '@/src/components/Layout';
import { Card, Badge, Button } from '@/src/components/ui';
import { cn } from '@/src/lib/utils';
import { apiFetch } from '@/src/lib/apiFetch';

type AppStatus = 'PENDING' | 'REVIEWED' | 'SHORTLISTED' | 'ACCEPTED' | 'REJECTED';

interface Application {
  id: number;
  student_name: string;
  student_email: string;
  student_skills: string[];
  match_score: number;
  job_title: string;
  cv_url: string;
  status: AppStatus;
  applied_time: string;
  is_read: boolean;
  needs_work_permit: boolean | null;
  available_from: string | null;
  phone: string;
  cover_note: string;
}

const statusVariants: Record<AppStatus, 'neutral' | 'primary' | 'danger' | 'success' | 'warning'> = {
  PENDING:     'neutral',
  REVIEWED:    'warning',
  SHORTLISTED: 'primary',
  ACCEPTED:    'success',
  REJECTED:    'danger',
};

const filterTabs = [
  { label: 'All',         value: 'All' },
  { label: 'Pending',     value: 'PENDING' },
  { label: 'Shortlisted', value: 'SHORTLISTED' },
  { label: 'Rejected',    value: 'REJECTED' },
];

export default function ReviewApplicationsPage() {
  const [filter, setFilter] = useState('All');
  const [search, setSearch] = useState('');
  const [applications, setApplications] = useState<Application[]>([]);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    apiFetch('/api/job-listings/company/applications/')
      .then(r => r.json())
      .then(data => setApplications(Array.isArray(data) ? data : []))
      .catch(() => {})
      .finally(() => setIsLoading(false));
  }, []);

  const updateStatus = async (id: number, status: AppStatus) => {
    const res = await apiFetch(`/api/job-listings/applications/${id}/status/`, {
      method: 'PATCH',
      body: JSON.stringify({ status }),
    });
    if (res.ok) {
      setApplications(prev => prev.map(a => a.id === id ? { ...a, status } : a));
    }
  };

  const filtered = applications.filter(a => {
    const matchFilter = filter === 'All' || a.status === filter;
    const matchSearch = a.student_name.toLowerCase().includes(search.toLowerCase())
      || a.job_title.toLowerCase().includes(search.toLowerCase());
    return matchFilter && matchSearch;
  });

  const formatDate = (d: string) =>
    new Date(d).toLocaleDateString('en-MY', { day: 'numeric', month: 'short', year: 'numeric' });

  return (
    <DashboardLayout title="Review Applications">
      <div className="max-w-5xl mx-auto space-y-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex p-1 bg-neutral-100 rounded-xl">
            {filterTabs.map(({ label, value }) => (
              <button key={value} onClick={() => setFilter(value)}
                className={cn('px-4 py-2 text-xs font-bold rounded-lg transition-all',
                  filter === value ? 'bg-white shadow-sm text-primary' : 'text-neutral-500 hover:text-neutral-900')}>
                {label}
              </button>
            ))}
          </div>
          <div className="relative md:w-64">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400" size={16} />
            <input type="text" placeholder="Search applicants..." value={search} onChange={e => setSearch(e.target.value)}
              className="w-full h-10 pl-10 pr-4 bg-white border border-neutral-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20" />
          </div>
        </div>

        {isLoading ? (
          <div className="flex items-center justify-center py-20">
            <div className="w-8 h-8 border-4 border-primary/20 border-t-primary rounded-full animate-spin" />
          </div>
        ) : (
          <div className="space-y-3">
            {filtered.map(app => (
              <Card key={app.id} className="p-0 overflow-hidden hover:border-primary/30 transition-all">
                <div className="p-5 flex flex-col md:flex-row md:items-center justify-between gap-4">
                  <div className="flex items-center gap-4">
                    <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-primary to-secondary flex items-center justify-center text-white font-black text-lg shrink-0">
                      {app.student_name[0]}
                    </div>
                    <div>
                      <h3 className="font-bold text-neutral-900">{app.student_name}</h3>
                      <p className="text-sm font-medium text-neutral-500">{app.job_title} · Applied {formatDate(app.applied_time)}</p>
                      <div className="flex flex-wrap gap-1.5 mt-2">
                        {app.student_skills.slice(0, 3).map(s => (
                          <span key={s} className="px-2 py-0.5 bg-neutral-100 rounded-full text-[10px] font-bold text-neutral-600">{s}</span>
                        ))}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-3 shrink-0">
                    <div className="text-center">
                      <p className="text-[10px] font-black text-neutral-400 uppercase tracking-widest">Match</p>
                      <p className={cn('text-xl font-black',
                        app.match_score > 70 ? 'text-success' : app.match_score > 40 ? 'text-warning' : 'text-danger')}>
                        {app.match_score}%
                      </p>
                    </div>
                    <Badge variant={statusVariants[app.status]} className="capitalize text-[10px] font-black tracking-widest px-3 py-1.5">
                      {app.status.toLowerCase()}
                    </Badge>
                    <Button variant="outline" size="sm" className="h-9 w-9 p-0"
                      onClick={() => setExpanded(expanded === app.id ? null : app.id)}>
                      <ChevronDown size={16} className={cn('transition-transform', expanded === app.id ? 'rotate-180' : '')} />
                    </Button>
                  </div>
                </div>

                {expanded === app.id && (
                  <div className="px-5 pb-5 pt-0 border-t border-neutral-100">
                    {/* Application answers */}
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 pt-4">
                      <div>
                        <p className="text-[10px] font-black text-neutral-400 uppercase tracking-widest">Work permit needed</p>
                        <p className="text-sm font-bold text-neutral-900">
                          {app.needs_work_permit === null ? '—' : app.needs_work_permit ? 'Yes' : 'No'}
                        </p>
                      </div>
                      <div>
                        <p className="text-[10px] font-black text-neutral-400 uppercase tracking-widest">Earliest start</p>
                        <p className="text-sm font-bold text-neutral-900">{app.available_from ? formatDate(app.available_from) : '—'}</p>
                      </div>
                      <div>
                        <p className="text-[10px] font-black text-neutral-400 uppercase tracking-widest">Phone</p>
                        <p className="text-sm font-bold text-neutral-900">{app.phone || '—'}</p>
                      </div>
                      <div>
                        <p className="text-[10px] font-black text-neutral-400 uppercase tracking-widest">Email</p>
                        <p className="text-sm font-bold text-neutral-900 truncate">{app.student_email}</p>
                      </div>
                    </div>
                    {app.cover_note && (
                      <div className="mt-4">
                        <p className="text-[10px] font-black text-neutral-400 uppercase tracking-widest mb-1">Why they&apos;re a good fit</p>
                        <p className="text-sm text-neutral-700 whitespace-pre-line bg-neutral-50 rounded-lg p-3">{app.cover_note}</p>
                      </div>
                    )}
                    <div className="flex flex-wrap gap-3 pt-4 items-center">
                      {app.cv_url && (
                        <a href={app.cv_url} target="_blank" rel="noopener noreferrer">
                          <Button size="sm" variant="outline" className="h-9 text-xs">View CV</Button>
                        </a>
                      )}
                      <div className="flex gap-2 ml-auto">
                        <Button size="sm"
                          className="h-9 text-xs bg-success hover:bg-success/90 text-white flex items-center gap-1.5"
                          onClick={() => updateStatus(app.id, 'SHORTLISTED')}>
                          <CheckCircle2 size={14} /> Shortlist
                        </Button>
                        <Button size="sm"
                          className="h-9 text-xs bg-primary hover:bg-primary/90 text-white flex items-center gap-1.5"
                          onClick={() => updateStatus(app.id, 'ACCEPTED')}>
                          <Star size={14} /> Accept
                        </Button>
                        <Button size="sm" variant="outline"
                          className="h-9 text-xs text-danger border-danger/30 hover:bg-danger/5 flex items-center gap-1.5"
                          onClick={() => updateStatus(app.id, 'REJECTED')}>
                          <XCircle size={14} /> Reject
                        </Button>
                      </div>
                    </div>
                  </div>
                )}
              </Card>
            ))}
          </div>
        )}

        {!isLoading && filtered.length === 0 && (
          <div className="py-20 text-center">
            <div className="w-20 h-20 bg-neutral-100 rounded-full flex items-center justify-center mx-auto mb-4 text-neutral-300">
              <Clock size={40} />
            </div>
            <h3 className="text-xl font-bold text-neutral-900">No applications found</h3>
            <p className="text-neutral-500 mt-1">Applications matching your filter will appear here.</p>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
