'use client';

import { useState, useEffect, useMemo } from 'react';
import { Search, Clock, Briefcase, ChevronRight, ChevronDown, FileText, ExternalLink } from 'lucide-react';
import Link from 'next/link';
import { DashboardLayout } from '@/src/components/Layout';
import { Card, Badge, Button } from '@/src/components/ui';
import { cn } from '@/src/lib/utils';
import { apiFetch } from '@/src/lib/apiFetch';

type ApplicationStatus = 'PENDING' | 'REVIEWED' | 'SHORTLISTED' | 'ACCEPTED' | 'REJECTED';

interface ApplicantSnapshot {
  skills: { skill_id: number; skill_name: string; skill_level: string | null }[];
  education: string[];
  experience: string[];
  captured_at?: string;
}

interface Application {
  id: number;
  job: number;
  job_title: string;
  company_name: string;
  work_mode: string;
  category_name: string | null;
  job_status: 'ACTIVE' | 'CLOSED' | 'DRAFT';
  status: ApplicationStatus;
  status_display: string;
  applied_time: string;
  // What was submitted, frozen at apply time. The CV file itself is
  // parsed and deleted; only this is kept.
  applicant_snapshot: ApplicantSnapshot;
  needs_work_permit: boolean | null;
  available_from: string | null;
  phone: string;
  cover_note: string;
}

const statusVariants: Record<ApplicationStatus, 'neutral' | 'primary' | 'warning' | 'danger' | 'success'> = {
  PENDING: 'neutral',
  REVIEWED: 'warning',
  SHORTLISTED: 'primary',
  ACCEPTED: 'success',
  REJECTED: 'danger',
};

// Every status the model can hold gets a tab. A status missing from this list
// would silently hide those applications from the student.
const TABS: Array<{ label: string; value: 'ALL' | ApplicationStatus }> = [
  { label: 'All',         value: 'ALL' },
  { label: 'Pending',     value: 'PENDING' },
  { label: 'Reviewed',    value: 'REVIEWED' },
  { label: 'Shortlisted', value: 'SHORTLISTED' },
  { label: 'Accepted',    value: 'ACCEPTED' },
  { label: 'Rejected',    value: 'REJECTED' },
];

const formatDate = (value: string) =>
  new Date(value).toLocaleDateString('en-MY', { day: 'numeric', month: 'short', year: 'numeric' });

export default function MyApplicationsPage() {
  const [applications, setApplications] = useState<Application[] | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  // Why the load failed, not merely that it did. An empty list and a failed
  // request look identical once both render a grey card, and the two were
  // reported with the same sentence -- so "no applications yet" was read as a
  // breakage, and a real breakage was read as an empty shortlist.
  const [loadError, setLoadError] = useState<string | null>(null);
  const [filter, setFilter] = useState<'ALL' | ApplicationStatus>('ALL');
  const [search, setSearch] = useState('');
  const [expandedId, setExpandedId] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    // The status is carried out of the first .then rather than thrown, so a
    // request that reached the server and was refused stays distinguishable
    // from one that never arrived. They have different fixes.
    let refusedWith: number | null = null;
    apiFetch('/api/job-listings/applications/')
      .then(response => {
        refusedWith = response.ok ? null : response.status;
        return response.ok ? response.json() : null;
      })
      .then((data: Application[] | null) => {
        if (cancelled) return;
        if (refusedWith !== null) {
          setLoadError(`The server refused the request (${refusedWith}).`);
        } else {
          setApplications(data ?? []);
        }
      })
      .catch(() => {
        if (!cancelled) setLoadError('The server could not be reached.');
      })
      .finally(() => { if (!cancelled) setIsLoading(false); });
    return () => { cancelled = true; };
  }, []);

  const counts = useMemo(() => {
    const tally: Record<string, number> = { ALL: applications?.length ?? 0 };
    for (const application of applications ?? []) {
      tally[application.status] = (tally[application.status] ?? 0) + 1;
    }
    return tally;
  }, [applications]);

  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase();
    return (applications ?? []).filter(application => {
      const matchesTab = filter === 'ALL' || application.status === filter;
      const matchesSearch =
        !query ||
        application.job_title.toLowerCase().includes(query) ||
        application.company_name.toLowerCase().includes(query);
      return matchesTab && matchesSearch;
    });
  }, [applications, filter, search]);

  return (
    <DashboardLayout title="My Applications">
      <div className="max-w-5xl mx-auto space-y-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex flex-wrap p-1 bg-neutral-100 rounded-xl">
            {TABS.map(tab => (
              <button
                key={tab.value}
                onClick={() => setFilter(tab.value)}
                className={cn(
                  'px-4 py-2 text-xs font-bold rounded-lg transition-all',
                  filter === tab.value ? 'bg-white shadow-sm text-primary' : 'text-neutral-500 hover:text-neutral-900'
                )}
              >
                {tab.label}
                {(counts[tab.value] ?? 0) > 0 && (
                  <span className="ml-1.5 text-[10px] text-neutral-400">{counts[tab.value]}</span>
                )}
              </button>
            ))}
          </div>
          <div className="relative w-full md:w-64">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400" size={16} />
            <input
              type="text"
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search by job or company..."
              className="w-full h-10 pl-10 pr-4 bg-white border border-neutral-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
            />
          </div>
        </div>

        {isLoading ? (
          <Card className="py-16 text-center text-neutral-500">Loading your applications…</Card>
        ) : loadError ? (
          <Card className="py-16 text-center text-neutral-500">
            <p className="font-bold text-neutral-700">Could not load your applications</p>
            <p className="text-sm mt-1">{loadError} Please try again.</p>
          </Card>
        ) : (
          <>
            <div className="space-y-4">
              {filtered.map(application => {
                const isExpanded = expandedId === application.id;
                return (
                  <Card key={application.id} className="p-0 overflow-hidden hover:border-primary/30 transition-all group">
                    <div className="p-6 flex flex-col md:flex-row md:items-center justify-between gap-6">
                      <div className="flex items-start gap-4">
                        <div className="w-14 h-14 rounded-xl bg-neutral-100 flex items-center justify-center text-neutral-400 shrink-0">
                          <FileText size={24} />
                        </div>
                        <div>
                          <h3 className="text-lg font-bold text-neutral-900 group-hover:text-primary transition-colors">
                            {application.job_title}
                          </h3>
                          <p className="text-sm font-semibold text-neutral-600">{application.company_name}</p>
                          <div className="flex flex-wrap items-center gap-4 mt-2">
                            <span className="flex items-center gap-1.5 text-xs text-neutral-400">
                              <Clock size={14} /> Applied on {formatDate(application.applied_time)}
                            </span>
                            {application.work_mode && (
                              <span className="flex items-center gap-1.5 text-xs text-neutral-400">
                                <Briefcase size={14} /> {application.work_mode}
                              </span>
                            )}
                            {application.job_status === 'CLOSED' && (
                              <span className="text-xs font-semibold text-neutral-400">Listing closed</span>
                            )}
                          </div>
                        </div>
                      </div>
                      <div className="flex items-center gap-6">
                        <Badge
                          variant={statusVariants[application.status]}
                          className="px-4 py-1.5 text-[10px] tracking-widest font-black uppercase"
                        >
                          {application.status_display}
                        </Badge>
                        <Button
                          variant="outline"
                          className="h-11 px-6"
                          onClick={() => setExpandedId(isExpanded ? null : application.id)}
                        >
                          {isExpanded ? 'Hide Details' : 'View Details'}
                          {isExpanded
                            ? <ChevronDown size={16} className="ml-2" />
                            : <ChevronRight size={16} className="ml-2" />}
                        </Button>
                      </div>
                    </div>

                    {isExpanded && (
                      <div className="border-t border-neutral-100 bg-neutral-50 px-6 py-5 grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
                        <div>
                          <p className="text-[10px] font-black text-neutral-400 uppercase tracking-widest mb-1">Category</p>
                          <p className="text-neutral-700">{application.category_name ?? 'Not categorised'}</p>
                        </div>
                        <div>
                          <p className="text-[10px] font-black text-neutral-400 uppercase tracking-widest mb-1">Available from</p>
                          <p className="text-neutral-700">
                            {application.available_from ? formatDate(application.available_from) : 'Not stated'}
                          </p>
                        </div>
                        <div>
                          <p className="text-[10px] font-black text-neutral-400 uppercase tracking-widest mb-1">Work permit needed</p>
                          <p className="text-neutral-700">
                            {application.needs_work_permit === null ? 'Not stated' : application.needs_work_permit ? 'Yes' : 'No'}
                          </p>
                        </div>
                        <div>
                          <p className="text-[10px] font-black text-neutral-400 uppercase tracking-widest mb-1">Contact number</p>
                          <p className="text-neutral-700">{application.phone || 'Not provided'}</p>
                        </div>
                        {application.cover_note && (
                          <div className="sm:col-span-2">
                            <p className="text-[10px] font-black text-neutral-400 uppercase tracking-widest mb-1">Cover note</p>
                            <p className="text-neutral-700 whitespace-pre-line">{application.cover_note}</p>
                          </div>
                        )}
                        {application.applicant_snapshot?.skills?.length > 0 && (
                          <div className="sm:col-span-2">
                            <p className="text-[10px] font-black text-neutral-400 uppercase tracking-widest mb-1">
                              Skills you submitted
                            </p>
                            <div className="flex flex-wrap gap-1.5">
                              {application.applicant_snapshot.skills.map(skill => (
                                <span key={skill.skill_id}
                                  className="px-2.5 py-1 rounded-full bg-neutral-100 text-neutral-700 text-xs font-semibold">
                                  {skill.skill_name}
                                  {skill.skill_level && (
                                    <span className="text-neutral-400"> · {skill.skill_level.toLowerCase()}</span>
                                  )}
                                </span>
                              ))}
                            </div>
                            <p className="text-[11px] text-neutral-400 mt-2">
                              This is what you sent. Editing your profile later does not
                              change an application already submitted.
                            </p>
                          </div>
                        )}
                      </div>
                    )}
                  </Card>
                );
              })}
            </div>

            {filtered.length === 0 && (
              <div className="py-20 text-center">
                <div className="w-20 h-20 bg-neutral-100 rounded-full flex items-center justify-center mx-auto mb-4 text-neutral-300">
                  <FileText size={40} />
                </div>
                <h3 className="text-xl font-bold text-neutral-900">
                  {counts.ALL === 0 ? 'No applications yet' : 'No applications match this filter'}
                </h3>
                <p className="text-neutral-500 mt-1">
                  {counts.ALL === 0
                    ? 'Start your career journey by applying for relevant jobs.'
                    : 'Try a different tab or clear your search.'}
                </p>
                {counts.ALL === 0 && (
                  <Link href="/jobs">
                    <Button className="mt-6">Browse Job Listings</Button>
                  </Link>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </DashboardLayout>
  );
}
