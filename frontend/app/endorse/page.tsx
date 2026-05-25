'use client';

import { useState } from 'react';
import { Search, CheckCircle2, XCircle, Award, ChevronDown } from 'lucide-react';
import { DashboardLayout } from '@/src/components/Layout';
import { Card, Badge, Button } from '@/src/components/ui';
import { cn } from '@/src/lib/utils';

type EndorseStatus = 'pending' | 'endorsed' | 'rejected';

type EndorsementRequest = {
  id: string; studentName: string; skill: string;
  evidence: string; submittedDate: string; status: EndorseStatus;
};

const mockRequests: EndorsementRequest[] = [
  { id: '1', studentName: 'Aisha Rahman', skill: 'Natural Language Processing', evidence: 'Completed Coursera NLP Specialization with certificate. Project: Sentiment analysis tool for Malay social media.', submittedDate: 'May 22, 2026', status: 'pending' },
  { id: '2', studentName: 'Tan Wei Liang', skill: 'Apache Spark', evidence: 'Udacity Big Data Nanodegree graduate. Built a real-time pipeline processing 10M events/day.', submittedDate: 'May 21, 2026', status: 'pending' },
  { id: '3', studentName: 'Priya Nair', skill: 'Tableau', evidence: 'Tableau Desktop Specialist certified. Created 5 executive dashboards at HealthTech internship.', submittedDate: 'May 20, 2026', status: 'endorsed' },
  { id: '4', studentName: 'Marcus Lee', skill: 'Machine Learning', evidence: 'Self-reported ML knowledge. No certificate provided.', submittedDate: 'May 18, 2026', status: 'rejected' },
  { id: '5', studentName: 'Nurul Izzati', skill: 'A/B Testing', evidence: 'Ran 3 statistically significant A/B tests during internship at FinTrack. Results documented.', submittedDate: 'May 17, 2026', status: 'pending' },
];

const statusVariants: Record<EndorseStatus, 'neutral' | 'success' | 'danger'> = {
  pending: 'neutral', endorsed: 'success', rejected: 'danger',
};

export default function EndorsePage() {
  const [requests, setRequests] = useState<EndorsementRequest[]>(mockRequests);
  const [filter, setFilter] = useState<'All' | EndorseStatus>('All');
  const [search, setSearch] = useState('');
  const [expanded, setExpanded] = useState<string | null>(null);

  const update = (id: string, status: EndorseStatus) =>
    setRequests((prev) => prev.map((r) => r.id === id ? { ...r, status } : r));

  const filtered = requests.filter((r) => {
    const matchFilter = filter === 'All' || r.status === filter;
    const matchSearch = r.studentName.toLowerCase().includes(search.toLowerCase()) || r.skill.toLowerCase().includes(search.toLowerCase());
    return matchFilter && matchSearch;
  });

  const pendingCount = requests.filter((r) => r.status === 'pending').length;

  return (
    <DashboardLayout title="Endorse Skills">
      <div className="max-w-4xl mx-auto space-y-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h2 className="text-2xl font-bold text-neutral-900 flex items-center gap-3">
              Skill Endorsements
              {pendingCount > 0 && <Badge variant="warning" className="text-xs font-black">{pendingCount} pending</Badge>}
            </h2>
            <p className="text-neutral-500 mt-1 text-sm">Review student skill evidence and grant or deny endorsements.</p>
          </div>
          <div className="flex items-center gap-3">
            <div className="relative w-full md:w-52">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400" size={16} />
              <input type="text" placeholder="Search..." value={search} onChange={(e) => setSearch(e.target.value)}
                className="w-full h-10 pl-10 pr-4 bg-white border border-neutral-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20" />
            </div>
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

        <div className="space-y-3">
          {filtered.map((req) => (
            <Card key={req.id} className="p-0 overflow-hidden hover:border-primary/20 transition-all">
              <div className="p-5 flex items-start gap-4">
                <div className="w-11 h-11 rounded-xl bg-indigo-50 flex items-center justify-center text-primary shrink-0">
                  <Award size={20} />
                </div>
                <div className="flex-1">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <h3 className="font-bold text-neutral-900">{req.studentName}</h3>
                      <p className="text-sm font-semibold text-primary mt-0.5">{req.skill}</p>
                      <p className="text-[10px] font-medium text-neutral-400 mt-0.5">Submitted {req.submittedDate}</p>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <Badge variant={statusVariants[req.status]} className="capitalize text-[10px] font-black tracking-widest">{req.status}</Badge>
                      <Button variant="outline" size="sm" className="h-8 w-8 p-0" onClick={() => setExpanded(expanded === req.id ? null : req.id)}>
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
                      <p className="text-[10px] font-black text-neutral-400 uppercase tracking-widest mb-1.5">Evidence Submitted</p>
                      <p className="text-sm text-neutral-700 leading-relaxed bg-neutral-50 p-4 rounded-xl border border-neutral-100">{req.evidence}</p>
                    </div>
                    {req.status === 'pending' && (
                      <div className="flex gap-3">
                        <Button size="sm" className="h-9 text-xs bg-success hover:bg-success/90 text-white flex items-center gap-1.5"
                          onClick={() => update(req.id, 'endorsed')}>
                          <CheckCircle2 size={14} /> Endorse Skill
                        </Button>
                        <Button size="sm" variant="outline" className="h-9 text-xs text-danger border-danger/30 hover:bg-danger/5 flex items-center gap-1.5"
                          onClick={() => update(req.id, 'rejected')}>
                          <XCircle size={14} /> Reject
                        </Button>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </Card>
          ))}
        </div>

        {filtered.length === 0 && (
          <div className="py-20 text-center">
            <Award size={48} className="mx-auto text-neutral-200 mb-4" />
            <h3 className="text-xl font-bold text-neutral-900">No requests found</h3>
            <p className="text-neutral-500 mt-1 text-sm">Endorsement requests will appear here.</p>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
