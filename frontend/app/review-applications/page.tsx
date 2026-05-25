'use client';

import { useState } from 'react';
import { Search, Filter, CheckCircle2, XCircle, Clock, ChevronDown, FileText, User } from 'lucide-react';
import { DashboardLayout } from '@/src/components/Layout';
import { Card, Badge, Button } from '@/src/components/ui';
import { cn } from '@/src/lib/utils';

type Status = 'pending' | 'shortlisted' | 'rejected' | 'accepted';

type Applicant = {
  id: string; name: string; role: string; matchScore: number;
  appliedDate: string; status: Status; skills: string[];
};

const mockApplicants: Applicant[] = [
  { id: '1', name: 'Aisha Rahman', role: 'Data Scientist', matchScore: 88, appliedDate: 'May 20, 2026', status: 'shortlisted', skills: ['Python', 'SQL', 'NLP', 'Tableau'] },
  { id: '2', name: 'Tan Wei Liang', role: 'Data Scientist', matchScore: 72, appliedDate: 'May 19, 2026', status: 'pending', skills: ['Python', 'SQL', 'Excel'] },
  { id: '3', name: 'Priya Nair', role: 'Product Analyst', matchScore: 65, appliedDate: 'May 18, 2026', status: 'shortlisted', skills: ['SQL', 'Excel', 'A/B Testing'] },
  { id: '4', name: 'Marcus Lee', role: 'Data Scientist', matchScore: 43, appliedDate: 'May 17, 2026', status: 'rejected', skills: ['Python', 'Machine Learning'] },
  { id: '5', name: 'Nurul Izzati', role: 'Product Analyst', matchScore: 79, appliedDate: 'May 16, 2026', status: 'pending', skills: ['SQL', 'Tableau', 'User Research'] },
];

const statusVariants: Record<Status, 'neutral' | 'primary' | 'danger' | 'success'> = {
  pending: 'neutral', shortlisted: 'primary', rejected: 'danger', accepted: 'success',
};

const filterTabs: { label: string; value: string }[] = [
  { label: 'All', value: 'All' },
  { label: 'Pending', value: 'pending' },
  { label: 'Shortlisted', value: 'shortlisted' },
  { label: 'Rejected', value: 'rejected' },
];

export default function ReviewApplicationsPage() {
  const [filter, setFilter] = useState('All');
  const [search, setSearch] = useState('');
  const [applicants, setApplicants] = useState<Applicant[]>(mockApplicants);
  const [expanded, setExpanded] = useState<string | null>(null);

  const updateStatus = (id: string, status: Status) => {
    setApplicants((prev) => prev.map((a) => a.id === id ? { ...a, status } : a));
  };

  const filtered = applicants.filter((a) => {
    const matchFilter = filter === 'All' || a.status === filter;
    const matchSearch = a.name.toLowerCase().includes(search.toLowerCase()) || a.role.toLowerCase().includes(search.toLowerCase());
    return matchFilter && matchSearch;
  });

  return (
    <DashboardLayout title="Review Applications">
      <div className="max-w-5xl mx-auto space-y-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex p-1 bg-neutral-100 rounded-xl">
            {filterTabs.map(({ label, value }) => (
              <button key={value} onClick={() => setFilter(value)}
                className={cn('px-4 py-2 text-xs font-bold rounded-lg transition-all', filter === value ? 'bg-white shadow-sm text-primary' : 'text-neutral-500 hover:text-neutral-900')}>
                {label}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-3">
            <div className="relative flex-1 md:w-64">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400" size={16} />
              <input type="text" placeholder="Search applicants..." value={search} onChange={(e) => setSearch(e.target.value)}
                className="w-full h-10 pl-10 pr-4 bg-white border border-neutral-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20" />
            </div>
            <Button variant="outline" size="sm" className="h-10"><Filter size={16} className="mr-2" /> Filter</Button>
          </div>
        </div>

        <div className="space-y-3">
          {filtered.map((app) => (
            <Card key={app.id} className="p-0 overflow-hidden hover:border-primary/30 transition-all">
              <div className="p-5 flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div className="flex items-center gap-4">
                  <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-primary to-secondary flex items-center justify-center text-white font-black text-lg shrink-0">
                    {app.name[0]}
                  </div>
                  <div>
                    <h3 className="font-bold text-neutral-900">{app.name}</h3>
                    <p className="text-sm font-medium text-neutral-500">{app.role} · Applied {app.appliedDate}</p>
                    <div className="flex flex-wrap gap-1.5 mt-2">
                      {app.skills.slice(0, 3).map((s) => (
                        <span key={s} className="px-2 py-0.5 bg-neutral-100 rounded-full text-[10px] font-bold text-neutral-600">{s}</span>
                      ))}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-3 shrink-0">
                  <div className="text-center">
                    <p className="text-[10px] font-black text-neutral-400 uppercase tracking-widest">Match</p>
                    <p className={cn('text-xl font-black', app.matchScore > 70 ? 'text-success' : app.matchScore > 40 ? 'text-warning' : 'text-danger')}>{app.matchScore}%</p>
                  </div>
                  <Badge variant={statusVariants[app.status]} className="capitalize text-[10px] font-black tracking-widest px-3 py-1.5">{app.status}</Badge>
                  <Button variant="outline" size="sm" className="h-9 w-9 p-0" onClick={() => setExpanded(expanded === app.id ? null : app.id)}>
                    <ChevronDown size={16} className={cn('transition-transform', expanded === app.id ? 'rotate-180' : '')} />
                  </Button>
                </div>
              </div>

              {expanded === app.id && (
                <div className="px-5 pb-5 pt-0 border-t border-neutral-100">
                  <div className="flex flex-wrap gap-3 pt-4">
                    <Button size="sm" variant="outline" className="h-9 text-xs flex items-center gap-1.5">
                      <FileText size={14} /> View CV
                    </Button>
                    <Button size="sm" variant="outline" className="h-9 text-xs flex items-center gap-1.5">
                      <User size={14} /> View Profile
                    </Button>
                    <div className="flex gap-2 ml-auto">
                      <Button size="sm" className="h-9 text-xs bg-success hover:bg-success/90 text-white flex items-center gap-1.5"
                        onClick={() => updateStatus(app.id, 'shortlisted')}>
                        <CheckCircle2 size={14} /> Shortlist
                      </Button>
                      <Button size="sm" variant="outline" className="h-9 text-xs text-danger border-danger/30 hover:bg-danger/5 flex items-center gap-1.5"
                        onClick={() => updateStatus(app.id, 'rejected')}>
                        <XCircle size={14} /> Reject
                      </Button>
                    </div>
                  </div>
                </div>
              )}
            </Card>
          ))}
        </div>

        {filtered.length === 0 && (
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
