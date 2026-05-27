'use client';

import React, { useState, useEffect, useMemo } from 'react';
import { Search, MapPin, DollarSign, Calendar, CheckCircle2, XCircle, Bookmark, Briefcase, Sparkles, ExternalLink } from 'lucide-react';
import { DashboardLayout } from '@/src/components/Layout';
import { Card, Badge, Button } from '@/src/components/ui';
import { cn } from '@/src/lib/utils';

interface ScrapedJob {
  id: number;
  job_title: string;
  company_name: string;
  location: string;
  salary_text: string;
  salary_min: number | null;
  salary_max: number | null;
  job_type: string;
  posted_date: string | null;
  source_url: string;
  source_portal: string;
  job_category: string | null;
  skills: string[];
}

interface MappedJob {
  id: string;
  title: string;
  company: string;
  location: string;
  salary: string;
  postedDate: string;
  job_type: string;
  requiredSkills: string[];
  source_url: string;
  category: string;
  matchScore: number;
}

const stringToColor = (str: string): string => {
  let hash = 0;
  for (let i = 0; i < str.length; i++) hash = str.charCodeAt(i) + ((hash << 5) - hash);
  return `hsl(${Math.abs(hash) % 360}, 55%, 45%)`;
};

const formatSalary = (min: number | null, max: number | null, text: string): string => {
  if (min && max) return `RM ${Number(min).toLocaleString()} – RM ${Number(max).toLocaleString()}`;
  if (text) return text;
  return 'Salary not disclosed';
};

const calcMatch = (requiredSkills: string[], mySkills: string[]): number => {
  if (requiredSkills.length === 0) return 0;
  const lower = mySkills.map(s => s.toLowerCase());
  const matched = requiredSkills.filter(s => lower.includes(s.toLowerCase())).length;
  return Math.round((matched / requiredSkills.length) * 100);
};

const mapJob = (job: ScrapedJob, mySkills: string[]): MappedJob => ({
  id: String(job.id),
  title: job.job_title,
  company: job.company_name || 'Unknown Company',
  location: job.location || 'Malaysia',
  salary: formatSalary(job.salary_min, job.salary_max, job.salary_text),
  postedDate: job.posted_date
    ? new Date(job.posted_date).toLocaleDateString('en-MY', { day: 'numeric', month: 'short', year: 'numeric' })
    : 'Recently',
  job_type: job.job_type || 'Full-time',
  requiredSkills: job.skills ?? [],
  source_url: job.source_url,
  category: job.job_category ?? 'General',
  matchScore: calcMatch(job.skills ?? [], mySkills),
});

export default function JobListingsPage() {
  const [rawJobs, setRawJobs] = useState<ScrapedJob[]>([]);
  const [mySkills, setMySkills] = useState<string[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [description, setDescription] = useState<string>('');
  const [descLoading, setDescLoading] = useState(false);

  const jobs = useMemo(() => rawJobs.map(j => mapJob(j, mySkills)), [rawJobs, mySkills]);
  const selectedJob = useMemo(() => jobs.find(j => j.id === selectedId) ?? null, [jobs, selectedId]);

  // Fetch full job detail (including description) when selection changes
  useEffect(() => {
    if (!selectedId) { setDescription(''); return; }
    setDescLoading(true);
    fetch(`http://localhost:8000/api/scrape-jobs/scraped/${selectedId}/`)
      .then(r => r.json())
      .then(data => setDescription(data.description ?? ''))
      .catch(() => setDescription(''))
      .finally(() => setDescLoading(false));
  }, [selectedId]);

  // Fetch student skills once on mount for match score calculation
  useEffect(() => {
    const token = localStorage.getItem('accessToken');
    if (!token) return;
    fetch('http://localhost:8000/api/accounts/student/skills/', {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(r => r.json())
      .then(data => {
        if (Array.isArray(data)) setMySkills(data.map((s: { skill_name: string }) => s.skill_name));
      })
      .catch(() => {});
  }, []);

  // Fetch jobs — debounced on search change
  useEffect(() => {
    const timer = setTimeout(() => {
      setIsLoading(true);
      const params = new URLSearchParams();
      if (search) params.set('search', search);
      fetch(`http://localhost:8000/api/scrape-jobs/scraped/?${params}`)
        .then(r => r.json())
        .then(data => {
          const list: ScrapedJob[] = Array.isArray(data) ? data : (data.results ?? []);
          setRawJobs(list);
          setSelectedId(prev => prev ?? (list[0] ? String(list[0].id) : null));
        })
        .catch(() => {})
        .finally(() => setIsLoading(false));
    }, search ? 400 : 0);
    return () => clearTimeout(timer);
  }, [search]);

  return (
    <DashboardLayout title="Job Marketplace">
      <div className="flex h-[calc(100vh-160px)] gap-6 relative">

        {/* Left — job list */}
        <div className="w-full lg:w-[450px] flex flex-col gap-4 overflow-hidden">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400" size={18} />
            <input
              type="text"
              placeholder="Search job title or company..."
              className="w-full h-11 pl-10 pr-4 bg-white border border-neutral-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
          </div>

          <div className="flex-1 overflow-y-auto pr-1 space-y-3">
            <div className="flex items-center gap-2 px-1">
              <Sparkles size={16} className="text-primary" />
              <p className="text-[10px] font-black text-neutral-400 uppercase tracking-widest">
                {jobs.length} jobs found
              </p>
            </div>

            {isLoading ? (
              <div className="flex-1 flex items-center justify-center py-20">
                <div className="w-8 h-8 border-4 border-primary/20 border-t-primary rounded-full animate-spin" />
              </div>
            ) : jobs.length > 0 ? jobs.map(job => (
              <Card
                key={job.id}
                className={cn('p-5 cursor-pointer transition-all border-l-4', selectedId === job.id ? 'border-l-primary bg-indigo-50/30' : 'border-l-transparent')}
                onClick={() => setSelectedId(job.id)}
              >
                <div className="flex gap-4">
                  <div
                    className="w-12 h-12 rounded-lg flex items-center justify-center text-white font-bold text-lg shrink-0"
                    style={{ backgroundColor: stringToColor(job.company) }}
                  >
                    {job.company[0]?.toUpperCase() ?? '?'}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-start justify-between gap-2">
                      <h4 className="font-bold text-neutral-900 leading-tight truncate">{job.title}</h4>
                      <Badge variant={job.matchScore > 70 ? 'success' : job.matchScore > 40 ? 'warning' : 'danger'} className="shrink-0">
                        {job.matchScore}%
                      </Badge>
                    </div>
                    <p className="text-sm font-medium text-neutral-600 mt-1 truncate">{job.company}</p>
                    <div className="flex items-center gap-3 mt-2">
                      <span className="flex items-center gap-1 text-[10px] uppercase font-bold text-neutral-400">
                        <MapPin size={10} /> {job.location}
                      </span>
                      <span className="flex items-center gap-1 text-[10px] uppercase font-bold text-neutral-400">
                        <Calendar size={10} /> {job.postedDate}
                      </span>
                    </div>
                    {job.requiredSkills.length > 0 && (
                      <div className="flex flex-wrap gap-1 mt-2">
                        {job.requiredSkills.slice(0, 4).map(skill => {
                          const has = mySkills.map(s => s.toLowerCase()).includes(skill.toLowerCase());
                          return (
                            <span key={skill} className={cn(
                              'px-2 py-0.5 rounded-full text-[10px] font-bold',
                              has ? 'bg-emerald-100 text-emerald-700' : 'bg-neutral-100 text-neutral-500'
                            )}>
                              {skill}
                            </span>
                          );
                        })}
                        {job.requiredSkills.length > 4 && (
                          <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-neutral-100 text-neutral-400">
                            +{job.requiredSkills.length - 4}
                          </span>
                        )}
                      </div>
                    )}
                    <div className="mt-3">
                      <a
                        href={job.source_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        onClick={e => e.stopPropagation()}
                        className="h-7 px-4 text-[10px] font-black uppercase tracking-wide inline-flex items-center gap-1 rounded-lg bg-primary text-white hover:bg-primary/90 transition-colors"
                      >
                        Apply <ExternalLink size={9} />
                      </a>
                    </div>
                  </div>
                </div>
              </Card>
            )) : (
              <div className="p-12 text-center">
                <Briefcase size={40} className="mx-auto text-neutral-200 mb-2" />
                <p className="text-sm font-bold text-neutral-500">No jobs found</p>
                <p className="text-xs text-neutral-400 mt-1">Try a different search term</p>
              </div>
            )}
          </div>
        </div>

        {/* Right — detail panel */}
        <div className="hidden lg:flex flex-1 bg-white border border-neutral-200 rounded-2xl overflow-hidden flex-col">
          {selectedJob ? (
            <>
              <div className="p-8 border-b border-neutral-100 bg-neutral-50/30">
                <div className="flex justify-between items-start mb-6">
                  <div className="flex gap-6">
                    <div
                      className="w-20 h-20 rounded-2xl flex items-center justify-center text-white font-bold text-3xl shrink-0"
                      style={{ backgroundColor: stringToColor(selectedJob.company) }}
                    >
                      {selectedJob.company[0]?.toUpperCase() ?? '?'}
                    </div>
                    <div>
                      <p className="text-lg font-semibold text-primary">{selectedJob.company}</p>
                      <h2 className="text-3xl font-black text-neutral-900 mb-1">{selectedJob.title}</h2>
                      <Badge variant="secondary">{selectedJob.category}</Badge>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Button variant="outline" className="h-11 px-4"><Bookmark size={20} /></Button>
                    <a href={selectedJob.source_url} target="_blank" rel="noopener noreferrer">
                      <Button className="h-11 px-8 flex items-center gap-2">
                        View on JobStreet <ExternalLink size={15} />
                      </Button>
                    </a>
                  </div>
                </div>

                <div className="grid grid-cols-3 gap-6 py-4 border-y border-neutral-100">
                  {[
                    { icon: DollarSign, label: 'Monthly Salary', value: selectedJob.salary, color: 'bg-emerald-50 text-success' },
                    { icon: MapPin, label: 'Location', value: selectedJob.location, color: 'bg-sky-50 text-secondary' },
                    { icon: Briefcase, label: 'Job Type', value: selectedJob.job_type || 'Full-time', color: 'bg-indigo-50 text-primary' },
                  ].map((item, i) => (
                    <div key={i} className="flex items-center gap-3">
                      <div className={cn('w-10 h-10 rounded-lg flex items-center justify-center', item.color)}>
                        <item.icon size={20} />
                      </div>
                      <div>
                        <p className="text-[10px] font-bold text-neutral-400 uppercase tracking-widest leading-none mb-1">{item.label}</p>
                        <p className="text-sm font-bold text-neutral-900">{item.value}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="flex-1 overflow-y-auto p-8 space-y-8">
                {selectedJob.requiredSkills.length > 0 && (
                  <section>
                    <h4 className="text-lg font-bold text-neutral-900 mb-4 flex items-center gap-2">
                      <div className="w-1 h-6 bg-primary rounded-full" /> Compatibility Check
                    </h4>
                    <div className="grid grid-cols-2 gap-4">
                      {selectedJob.requiredSkills.map(skill => {
                        const has = mySkills.map(s => s.toLowerCase()).includes(skill.toLowerCase());
                        return (
                          <div key={skill} className={cn('p-4 rounded-xl border flex items-center justify-between', has ? 'bg-emerald-50 border-emerald-100 text-success' : 'bg-neutral-50 border-neutral-100 text-neutral-400')}>
                            <span className="text-sm font-bold">{skill}</span>
                            {has ? <CheckCircle2 size={18} /> : <XCircle size={18} className="text-neutral-300" />}
                          </div>
                        );
                      })}
                    </div>
                  </section>
                )}

                <section>
                  <h4 className="text-lg font-bold text-neutral-900 mb-4 flex items-center gap-2">
                    <div className="w-1 h-6 bg-primary rounded-full" /> Job Description
                  </h4>
                  {descLoading ? (
                    <div className="flex items-center gap-2 text-sm text-neutral-400">
                      <div className="w-4 h-4 border-2 border-primary/20 border-t-primary rounded-full animate-spin" />
                      Loading description…
                    </div>
                  ) : description ? (
                    <div className="text-sm text-neutral-700 leading-relaxed whitespace-pre-line">
                      {description}
                    </div>
                  ) : (
                    <p className="text-sm text-neutral-400 italic">No description available.</p>
                  )}
                </section>

                <section>
                  <h4 className="text-lg font-bold text-neutral-900 mb-3 flex items-center gap-2">
                    <div className="w-1 h-6 bg-primary rounded-full" /> Source
                  </h4>
                  <p className="text-sm text-neutral-500">
                    This listing is sourced from{' '}
                    <a href={selectedJob.source_url} target="_blank" rel="noopener noreferrer" className="text-primary font-semibold hover:underline">
                      JobStreet ↗
                    </a>
                    . Click <strong>View on JobStreet</strong> to apply directly.
                  </p>
                </section>
              </div>
            </>
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center text-neutral-400">
              <Briefcase size={64} className="mb-4 opacity-10" />
              <p className="text-lg font-bold text-neutral-500">Pick a job from the list</p>
            </div>
          )}
        </div>
      </div>
    </DashboardLayout>
  );
}
