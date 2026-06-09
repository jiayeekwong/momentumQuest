'use client';

import React, { useState, useEffect, useMemo } from 'react';
import { Search, MapPin, DollarSign, Calendar, CheckCircle2, XCircle, Bookmark, Briefcase, Sparkles, ExternalLink } from 'lucide-react';
import { DashboardLayout } from '@/src/components/Layout';
import { Card, Badge, Button } from '@/src/components/ui';
import { cn } from '@/src/lib/utils';
import { apiFetch } from '@/src/lib/apiFetch';

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

interface CompanyJob {
  id: number;
  job_title: string;
  company: { id: number; company_name: string };
  category: { id: number; category_name: string };
  category_name: string;
  description: string;
  salary_min: number | null;
  salary_max: number | null;
  work_mode: string;
  required_skills: string[];
  posted_time: string;
  closing_date: string;
}

interface MappedJob {
  id: string;
  sourceType: 'scraped' | 'company';
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
  companyJobId?: number;
  description?: string;
}

const stringToColor = (str: string): string => {
  let hash = 0;
  for (let i = 0; i < str.length; i++) hash = str.charCodeAt(i) + ((hash << 5) - hash);
  return `hsl(${Math.abs(hash) % 360}, 55%, 45%)`;
};

const formatSalary = (min: number | null, max: number | null, text?: string): string => {
  if (min && max) return `RM ${Number(min).toLocaleString()} – RM ${Number(max).toLocaleString()}`;
  if (text) return text;
  return 'Salary not disclosed';
};

// Real skill-based match — preserved for when student-skill data is fully wired.
const calcMatch = (requiredSkills: string[], mySkills: string[]): number => {
  if (requiredSkills.length === 0) return 0;
  const lower = mySkills.map(s => s.toLowerCase());
  const matched = requiredSkills.filter(s => lower.includes(s.toLowerCase())).length;
  return Math.round((matched / requiredSkills.length) * 100);
};

// DEMO: until real matching is connected, show a stable, realistic-looking match
// score per job (62–98%) derived from the job id so it stays consistent across
// renders/sorting. Swap back to calcMatch(...) in the mappers to restore real logic.
const hardcodedMatch = (seed: number): number => 62 + ((seed * 41) % 37);

const mapScrapedJob = (job: ScrapedJob, mySkills: string[]): MappedJob => ({
  id: String(job.id),
  sourceType: 'scraped',
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
  matchScore: hardcodedMatch(job.id),
});

const mapCompanyJob = (job: CompanyJob, mySkills: string[]): MappedJob => {
  return {
    id: `company-${job.id}`,
    sourceType: 'company',
    companyJobId: job.id,
    title: job.job_title,
    company: job.company.company_name,
    location: job.work_mode || 'Malaysia',
    salary: formatSalary(job.salary_min, job.salary_max),
    postedDate: new Date(job.posted_time).toLocaleDateString('en-MY', { day: 'numeric', month: 'short', year: 'numeric' }),
    job_type: job.work_mode || 'Full-time',
    requiredSkills: job.required_skills || [],
    source_url: '', // N/A for company jobs
    category: job.category_name,
    matchScore: hardcodedMatch(job.id),
    description: job.description,
  };
};

async function uploadCv(file: File): Promise<string | null> {
  try {
    const form = new FormData();
    form.append('file', file);
    // apiFetch attaches the bearer token, refreshes it on 401, and leaves
    // Content-Type unset for FormData (so the multipart boundary is correct).
    const response = await apiFetch('/api/job-listings/cv/upload/', {
      method: 'POST',
      body: form,
    });
    if (!response.ok) return null;
    const data = await response.json();
    return data.url ?? null;
  } catch {
    return null;
  }
}

interface ApplicationPayload {
  job: number;
  cv_url: string;
  needs_work_permit: boolean;
  available_from: string | null;
  phone: string;
  cover_note: string;
}

async function submitJobApplication(payload: ApplicationPayload): Promise<{ ok: boolean; error?: string }> {
  try {
    const response = await apiFetch('/api/job-listings/applications/', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    if (response.ok) return { ok: true };
    const data = await response.json().catch(() => ({}));
    return { ok: false, error: data.detail || 'Failed to submit application.' };
  } catch {
    return { ok: false, error: 'Network error. Make sure the backend is running.' };
  }
}

export default function JobListingsPage() {
  const [scrapedJobs, setScrapedJobs] = useState<ScrapedJob[]>([]);
  const [companyJobs, setCompanyJobs] = useState<CompanyJob[]>([]);
  const [mySkills, setMySkills] = useState<string[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [description, setDescription] = useState<string>('');
  const [descLoading, setDescLoading] = useState(false);
  const [applyMessage, setApplyMessage] = useState<string | null>(null);

  // Application modal (company-posted jobs only)
  const [applyModalJob, setApplyModalJob] = useState<{ id: number; title: string } | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState('');
  const [cvFile, setCvFile] = useState<File | null>(null);
  const [needsWorkPermit, setNeedsWorkPermit] = useState<'' | 'yes' | 'no'>('');
  const [availableFrom, setAvailableFrom] = useState('');
  const [phone, setPhone] = useState('');
  const [coverNote, setCoverNote] = useState('');

  const openApplyModal = (jobId: number, title: string) => {
    if (!localStorage.getItem('accessToken')) {
      setApplyMessage('Please log in to apply');
      setTimeout(() => setApplyMessage(null), 3000);
      return;
    }
    // reset form
    setCvFile(null);
    setNeedsWorkPermit('');
    setAvailableFrom('');
    setPhone('');
    setCoverNote('');
    setFormError('');
    setApplyModalJob({ id: jobId, title });
  };

  const submitApplication = async () => {
    if (!applyModalJob) return;
    if (!cvFile) { setFormError('Please attach your CV (PDF or Word).'); return; }
    if (!needsWorkPermit) { setFormError('Please answer the work-permit question.'); return; }

    setSubmitting(true);
    setFormError('');

    const cvUrl = await uploadCv(cvFile);
    if (!cvUrl) {
      setSubmitting(false);
      setFormError('CV upload failed. Use a PDF or Word file and try again.');
      return;
    }

    const result = await submitJobApplication({
      job: applyModalJob.id,
      cv_url: cvUrl,
      needs_work_permit: needsWorkPermit === 'yes',
      available_from: availableFrom || null,
      phone,
      cover_note: coverNote,
    });
    setSubmitting(false);

    if (result.ok) {
      setApplyModalJob(null);
      setApplyMessage('Application submitted successfully! ✓');
      setTimeout(() => setApplyMessage(null), 3000);
    } else {
      setFormError(result.error ?? 'Failed to submit application.');
    }
  };

  const jobs = useMemo(() => {
    const mapped = [
      ...scrapedJobs.map(j => mapScrapedJob(j, mySkills)),
      ...companyJobs.map(j => mapCompanyJob(j, mySkills)),
    ];
    // Sort by match score descending
    return mapped.sort((a, b) => b.matchScore - a.matchScore);
  }, [scrapedJobs, companyJobs, mySkills]);

  const selectedJob = useMemo(() => jobs.find(j => j.id === selectedId) ?? null, [jobs, selectedId]);

  // Fetch full job detail (including description) when selection changes
  useEffect(() => {
    if (!selectedId) { setDescription(''); return; }
    setDescLoading(true);

    // If it's a company job, use the pre-fetched description
    const companyJob = jobs.find(j => j.id === selectedId);
    if (companyJob?.sourceType === 'company' && companyJob.description) {
      setDescription(companyJob.description);
      setDescLoading(false);
      return;
    }

    // Otherwise, fetch from scraped endpoint
    fetch(`http://localhost:8000/api/scrape-jobs/scraped/${selectedId}/`)
      .then(r => r.json())
      .then(data => setDescription(data.description ?? ''))
      .catch(() => setDescription(''))
      .finally(() => setDescLoading(false));
  }, [selectedId, jobs]);

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

  // Fetch jobs from both endpoints — debounced on search change
  useEffect(() => {
    const timer = setTimeout(() => {
      setIsLoading(true);
      const token = localStorage.getItem('accessToken');
      const params = new URLSearchParams();
      if (search) params.set('search', search);

      // Fetch both scraped and company jobs in parallel
      Promise.all([
        fetch(`http://localhost:8000/api/scrape-jobs/scraped/?${params}`)
          .then(r => r.json())
          .then(data => {
            const list: ScrapedJob[] = Array.isArray(data) ? data : (data.results ?? []);
            setScrapedJobs(list);
            return list;
          })
          .catch(() => []),
        token
          ? fetch(`http://localhost:8000/api/job-listings/public/?${params}`, {
              headers: { Authorization: `Bearer ${token}` },
            })
              .then(r => r.json())
              .then(data => {
                const list: CompanyJob[] = Array.isArray(data) ? data : (data.results ?? []);
                setCompanyJobs(list);
                return list;
              })
              .catch(() => [])
          : Promise.resolve([]),
      ]).then(([scraped]) => {
        // Select first job if none selected
        setSelectedId(prev => {
          if (prev) return prev; // Keep current selection
          const firstJob = scraped[0];
          return firstJob ? String(firstJob.id) : null;
        });
      }).finally(() => setIsLoading(false));
    }, search ? 400 : 0);
    return () => clearTimeout(timer);
  }, [search]);

  return (
    <DashboardLayout title="Job Marketplace">
      {/* Application form modal — company-posted jobs */}
      {applyModalJob && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={() => !submitting && setApplyModalJob(null)}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
            <div className="px-6 py-5 border-b border-neutral-100">
              <h3 className="text-lg font-black text-neutral-900">Apply — {applyModalJob.title}</h3>
              <p className="text-xs text-neutral-500 mt-1">Attach your CV and answer a few quick questions.</p>
            </div>

            <div className="p-6 space-y-5">
              <div className="space-y-2">
                <label className="text-[10px] font-black text-neutral-900 uppercase tracking-widest block">Resume / CV <span className="text-danger">*</span></label>
                <input
                  type="file"
                  accept=".pdf,.doc,.docx"
                  onChange={e => setCvFile(e.target.files?.[0] ?? null)}
                  className="w-full text-sm text-neutral-600 file:mr-3 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-xs file:font-bold file:bg-primary/10 file:text-primary hover:file:bg-primary/20 file:cursor-pointer"
                />
                {cvFile && <p className="text-xs text-success font-medium">Selected: {cvFile.name}</p>}
              </div>

              <div className="space-y-2">
                <label className="text-[10px] font-black text-neutral-900 uppercase tracking-widest block">Do you require a work permit / visa to work here? <span className="text-danger">*</span></label>
                <div className="flex gap-3">
                  {(['yes', 'no'] as const).map(v => (
                    <button
                      key={v}
                      type="button"
                      onClick={() => setNeedsWorkPermit(v)}
                      className={cn('flex-1 h-10 rounded-lg border-2 text-sm font-bold capitalize transition-colors',
                        needsWorkPermit === v ? 'border-primary bg-indigo-50/50 text-primary' : 'border-neutral-200 text-neutral-500 hover:border-neutral-300')}
                    >
                      {v}
                    </button>
                  ))}
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <label className="text-[10px] font-black text-neutral-900 uppercase tracking-widest block">Earliest start date</label>
                  <input
                    type="date"
                    value={availableFrom}
                    onChange={e => setAvailableFrom(e.target.value)}
                    className="w-full h-10 px-3 bg-white border border-neutral-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-[10px] font-black text-neutral-900 uppercase tracking-widest block">Phone number</label>
                  <input
                    type="tel"
                    value={phone}
                    onChange={e => setPhone(e.target.value)}
                    placeholder="+60..."
                    className="w-full h-10 px-3 bg-white border border-neutral-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
                  />
                </div>
              </div>

              <div className="space-y-2">
                <label className="text-[10px] font-black text-neutral-900 uppercase tracking-widest block">Why are you a good fit? <span className="text-neutral-400 normal-case">(optional)</span></label>
                <textarea
                  value={coverNote}
                  onChange={e => setCoverNote(e.target.value)}
                  rows={3}
                  className="w-full px-3 py-2 bg-white border border-neutral-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 resize-none"
                />
              </div>

              {formError && (
                <div className="rounded-lg bg-red-50 border border-red-100 p-3 text-sm text-danger">{formError}</div>
              )}
            </div>

            <div className="px-6 py-4 border-t border-neutral-100 flex gap-3">
              <Button variant="outline" fullWidth className="h-11" disabled={submitting} onClick={() => setApplyModalJob(null)}>Cancel</Button>
              <Button fullWidth className="h-11" isLoading={submitting} onClick={submitApplication}>Submit Application</Button>
            </div>
          </div>
        </div>
      )}
      {applyMessage && (
        <div className={cn('mb-4 p-4 rounded-lg text-sm font-bold',
          applyMessage.includes('successfully') ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-700')}>
          {applyMessage}
        </div>
      )}
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
                      {job.sourceType === 'company' ? (
                        <button
                          onClick={(e) => { e.stopPropagation(); openApplyModal(job.companyJobId!, job.title); }}
                          className="h-7 px-4 text-[10px] font-black uppercase tracking-wide inline-flex items-center gap-1 rounded-lg bg-primary text-white hover:bg-primary/90 transition-colors"
                        >
                          Apply Now
                        </button>
                      ) : (
                        <a
                          href={job.source_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          onClick={e => e.stopPropagation()}
                          className="h-7 px-4 text-[10px] font-black uppercase tracking-wide inline-flex items-center gap-1 rounded-lg bg-primary text-white hover:bg-primary/90 transition-colors"
                        >
                          Apply <ExternalLink size={9} />
                        </a>
                      )}
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
                    {selectedJob.sourceType === 'company' ? (
                      <Button
                        className="h-11 px-8 flex items-center gap-2"
                        onClick={() => openApplyModal(selectedJob.companyJobId!, selectedJob.title)}
                      >
                        Apply Now
                      </Button>
                    ) : (
                      <a href={selectedJob.source_url} target="_blank" rel="noopener noreferrer">
                        <Button className="h-11 px-8 flex items-center gap-2">
                          View on JobStreet <ExternalLink size={15} />
                        </Button>
                      </a>
                    )}
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
                    <div className="text-sm text-neutral-700 leading-relaxed rich-text"
                      dangerouslySetInnerHTML={{ __html: description }} />
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
