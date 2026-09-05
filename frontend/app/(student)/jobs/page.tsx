'use client';

import { useState, useEffect, useMemo } from 'react';
import { Search, MapPin, DollarSign, Calendar, CheckCircle2, XCircle, AlertCircle, Bookmark, Briefcase, Sparkles, ExternalLink, ChevronDown } from 'lucide-react';
import { DashboardLayout } from '@/src/components/Layout';
import { Card, Badge, Button, Checkbox } from '@/src/components/ui';
import { cn } from '@/src/lib/utils';
import { apiFetch, API_BASE } from '@/src/lib/apiFetch';
import { usePrivacyNotice } from '@/src/lib/privacyNotice';
import { RichText } from '@/src/lib/richText';

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
  required_skill_levels: { skill: string; required_level: string }[];
  // Proficiency-weighted, computed server-side against the logged-in student.
  // Null when the advert lists no skills, so the UI can show nothing at all
  // rather than a misleading 0%.
  match_score: number | null;
  is_saved: boolean;
  // A saved listing can lapse. It stays in the student's list, labelled, in
  // preference to disappearing as though the bookmark had failed.
  status: 'ACTIVE' | 'CLOSED' | 'DRAFT';
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
  required_skill_levels: { skill: string; required_level: string }[];
  match_score: number | null;
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
  requiredSkillLevels: { skill: string; required_level: string }[];
  source_url: string;
  category: string;
  matchScore: number | null;
  companyJobId?: number;
  description?: string;
  // Bookmarking is offered on scraped listings only: a company listing is
  // applied to from this page, so a shortlist adds nothing there.
  isSaved: boolean;
  isClosed: boolean;
}

// Mirrors backend/job_listings/matching.py: Beginner 1, Intermediate 2,
// Advanced 3, and a skill scores min(student, required). The per-skill verdict
// below has to use the same scale as the percentage shown beside it — when it
// was a name-only check, a student holding every skill at Beginner saw a green
// tick on each one next to a 33% match.
const PROFICIENCY_VALUE: Record<string, number> = {
  BEGINNER: 1,
  INTERMEDIATE: 2,
  ADVANCED: 3,
};

type SkillVerdict = 'met' | 'partial' | 'missing';

const skillVerdict = (
  requiredLevel: string | undefined,
  studentLevel: string | undefined,
): SkillVerdict => {
  if (!studentLevel) return 'missing';
  // No stated requirement means holding the skill is all that is asked.
  if (!requiredLevel) return 'met';
  const held = PROFICIENCY_VALUE[studentLevel] ?? 0;
  const needed = PROFICIENCY_VALUE[requiredLevel] ?? 0;
  return held >= needed ? 'met' : 'partial';
};

const LEVEL_LABEL: Record<string, string> = {
  BEGINNER: 'Beginner',
  INTERMEDIATE: 'Intermediate',
  ADVANCED: 'Advanced',
};

const requiredLevelFor = (job: MappedJob, skill: string): string | undefined =>
  job.requiredSkillLevels.find(
    row => row.skill.toLowerCase() === skill.toLowerCase()
  )?.required_level;

const stringToColor = (str: string): string => {
  let hash = 0;
  for (let i = 0; i < str.length; i++) hash = str.charCodeAt(i) + ((hash << 5) - hash);
  return `hsl(${Math.abs(hash) % 360}, 55%, 45%)`;
};

// The state or federal territory an advert sits in, which is the unit a
// student actually chooses between. The raw strings are far too granular to
// put in a menu: 119 distinct values across the current feed, where "Kuala
// Lumpur", "Kuala Lumpur (Hybrid)" and "Bangsar South, Kuala Lumpur" are one
// place written three ways. Picking any single spelling would have hidden the
// other two.
//
// The portal writes them as "<area>, <state>" with an optional work-mode
// suffix, so the trailing bracket goes and the last comma-separated part is
// the state. A string with neither -- "Penang", or a company advert's
// "Remote" -- is already the whole answer and is returned as it stands.
const regionOf = (location: string): string => {
  const withoutMode = location.replace(/\s*\([^)]*\)\s*$/, '').trim();
  if (!withoutMode) return '';
  return withoutMode.split(',').pop()!.trim();
};

const formatSalary = (min: number | null, max: number | null, text?: string): string => {
  if (min && max) return `RM ${Number(min).toLocaleString()} – RM ${Number(max).toLocaleString()}`;
  if (text) return text;
  return 'Salary not disclosed';
};

// The match score is no longer computed here. It used to be a client-side
// count of overlapping skill names, which ignored proficiency and disagreed
// with the score the employer saw for the same pairing. Both sides now read
// job_listings/matching.py, and the API returns the result as match_score.

const mapScrapedJob = (job: ScrapedJob): MappedJob => ({
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
  requiredSkillLevels: job.required_skill_levels ?? [],
  source_url: job.source_url,
  category: job.job_category ?? 'General',
  matchScore: job.match_score,
  isSaved: job.is_saved ?? false,
  isClosed: job.status === 'CLOSED',
});

const mapCompanyJob = (job: CompanyJob): MappedJob => {
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
    isSaved: false,
    isClosed: false,
    requiredSkills: job.required_skills || [],
    requiredSkillLevels: job.required_skill_levels ?? [],
    source_url: '', // N/A for company jobs
    category: job.category_name,
    matchScore: job.match_score,
    description: job.description,
  };
};

interface ParsedSkill {
  skill_id: number;
  skill_name: string;
  skill_category: string;
}

interface ParsedCv {
  readable: boolean;
  skills: ParsedSkill[];
  education: string[];
  experience: string[];
  detail: string;
  cv_parse_receipt: string;
}

// The CV is read on the server and deleted immediately; only what the student
// confirms below is ever stored. So this returns extracted content, not a URL
// to a file that is now sitting somewhere.
async function parseCv(file: File): Promise<{ data?: ParsedCv; error?: string }> {
  try {
    const form = new FormData();
    form.append('file', file);
    // The server refuses to read the file without this. It is sent only from
    // the branch where the student has ticked the box.
    form.append('cv_processing_ack', 'true');
    // apiFetch attaches the bearer token, refreshes it on 401, and leaves
    // Content-Type unset for FormData (so the multipart boundary is correct).
    const response = await apiFetch('/api/job-listings/cv/parse/', {
      method: 'POST',
      body: form,
    });
    const data = await response.json();
    if (!response.ok) return { error: data.detail ?? 'We could not read that CV.' };
    return { data };
  } catch {
    return { error: 'We could not read that CV. Please try again.' };
  }
}

/**
 * The extracted lines, every one of them, each editable and removable.
 *
 * Every line is rendered rather than the first few: the list is what gets sent
 * to an employer, so a line the student cannot see is a line they cannot
 * withhold. The container scrolls instead of truncating.
 */
function EditableLines({
  label,
  lines,
  onChange,
}: {
  label: string;
  lines: string[];
  onChange: (next: string[]) => void;
}) {
  if (lines.length === 0) return null;

  const update = (index: number, value: string) =>
    onChange(lines.map((line, i) => (i === index ? value : line)));

  const remove = (index: number) =>
    onChange(lines.filter((_, i) => i !== index));

  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between">
        <p className="text-[10px] font-black uppercase tracking-widest text-neutral-400">
          {label}
        </p>
        <p className="text-[10px] text-neutral-400">
          {lines.length} {lines.length === 1 ? 'line' : 'lines'} · edit or remove any
        </p>
      </div>
      <ul className="max-h-48 space-y-1 overflow-y-auto pr-1">
        {lines.map((line, index) => (
          <li key={index} className="flex items-center gap-1.5">
            <input
              type="text"
              value={line}
              aria-label={`${label} line ${index + 1}`}
              onChange={e => update(index, e.target.value)}
              className="h-8 flex-1 rounded border border-neutral-200 bg-white px-2 text-xs
                         text-neutral-700 focus:border-primary focus:outline-none
                         focus:ring-1 focus:ring-primary/20"
            />
            <button
              type="button"
              onClick={() => remove(index)}
              aria-label={`Remove ${label.toLowerCase()} line ${index + 1}`}
              className="shrink-0 rounded p-1 text-neutral-400 transition-colors
                         hover:bg-red-50 hover:text-danger"
            >
              <XCircle size={14} />
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

interface ApplicationPayload {
  job: number;
  // Proof that this application was built from a CV the student consented to
  // having read. Issued by the parse endpoint, opaque here, and short-lived.
  cv_parse_receipt: string;
  applicant_snapshot: {
    skills: { skill_id: number }[];
    education: string[];
    experience: string[];
  };
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
  // Keyed by lowercased skill name -> the student's proficiency. The level is
  // what makes the per-skill verdict agree with the match percentage.
  const [myLevels, setMyLevels] = useState<Record<string, string>>({});
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  // Empty means every location. Held here rather than sent to the API --
  // see the locationOptions comment below for why this one is client-side
  // while search is not.
  const [location, setLocation] = useState('');
  // A shortlist tab rather than a separate page: the student is already
  // looking at jobs, and the saved ones are the same objects with the same
  // detail panel beside them.
  const [view, setView] = useState<'all' | 'saved'>('all');
  const [savingId, setSavingId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [fetchedDescription, setFetchedDescription] =
    useState<{ id: string; text: string } | null>(null);
  const [applyMessage, setApplyMessage] = useState<string | null>(null);

  // Application modal (company-posted jobs only)
  const [applyModalJob, setApplyModalJob] = useState<{ id: number; title: string } | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [cvProcessingAck, setCvProcessingAck] = useState(false);
  // The confirmed lines, seeded from what the parser proposed. Held separately
  // from parsedCv so that what is submitted is what the student has actually
  // seen and approved, rather than the parser's untouched output.
  const [educationLines, setEducationLines] = useState<string[]>([]);
  const [experienceLines, setExperienceLines] = useState<string[]>([]);
  // The consent wording and the notice version recorded against it must
  // come from the same place. A stale local copy would mean recording a
  // student as having agreed to text they never saw.
  const { notice } = usePrivacyNotice();
  const [formError, setFormError] = useState('');
  const [cvFile, setCvFile] = useState<File | null>(null);
  // Parsed content awaiting the student's confirmation. Nothing is stored
  // until they submit, and the CV file itself never was.
  const [parsedCv, setParsedCv] = useState<ParsedCv | null>(null);
  const [parsingCv, setParsingCv] = useState(false);
  const [excludedSkillIds, setExcludedSkillIds] = useState<number[]>([]);
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
    setCvProcessingAck(false);
    setEducationLines([]);
    setExperienceLines([]);
    setApplyModalJob({ id: jobId, title });
  };

  // Unchecked by default and reset with the rest of the form. The file input
  // is disabled until it is ticked, so a CV cannot be sent before the student
  // has agreed to it being read.
  const cvAckGiven = cvProcessingAck && Boolean(notice);

  const submitApplication = async () => {
    if (!applyModalJob) return;
    if (!parsedCv) { setFormError('Please attach your CV and confirm what we found.'); return; }
    if (!needsWorkPermit) { setFormError('Please answer the work-permit question.'); return; }

    setSubmitting(true);
    setFormError('');

    const result = await submitJobApplication({
      job: applyModalJob.id,
      cv_parse_receipt: parsedCv.cv_parse_receipt,
      applicant_snapshot: {
        skills: parsedCv.skills
          .filter(skill => !excludedSkillIds.includes(skill.skill_id))
          .map(skill => ({ skill_id: skill.skill_id })),
        // The confirmed lines, not the parser's originals: anything the
        // student edited or removed must not reach the employer.
        education: educationLines.map(line => line.trim()).filter(Boolean),
        experience: experienceLines.map(line => line.trim()).filter(Boolean),
      },
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

  /** Bookmark or un-bookmark a scraped listing. */
  const toggleSaved = async (job: MappedJob) => {
    if (job.sourceType !== 'scraped') return;
    setSavingId(job.id);
    // Optimistic: the button answers immediately and is put back if the
    // request fails. A bookmark that waits on a round trip feels broken.
    const next = !job.isSaved;
    setScrapedJobs(prev => prev.map(
      row => String(row.id) === job.id ? { ...row, is_saved: next } : row));
    try {
      const res = await apiFetch(`/api/scrape-jobs/scraped/${job.id}/save/`, {
        method: next ? 'POST' : 'DELETE',
      });
      if (!res.ok) throw new Error('save failed');
    } catch {
      setScrapedJobs(prev => prev.map(
        row => String(row.id) === job.id ? { ...row, is_saved: !next } : row));
    } finally {
      setSavingId(null);
    }
  };

  const mappedJobs = useMemo(
    () => [
      ...scrapedJobs.map(mapScrapedJob),
      ...companyJobs.map(mapCompanyJob),
    ],
    [scrapedJobs, companyJobs]
  );

  // The locations actually present in the results, so every option returns
  // something and the student is never offered a place with no adverts in it.
  //
  // Built from mappedJobs rather than from the filtered list, or choosing one
  // location would collapse the menu to that single entry and strand the
  // student there.
  //
  // Filtered on the client, unlike search. The scraped endpoint does take
  // ?location=, but the company endpoint reads no query parameters at all, so
  // a server-side filter would narrow the scraped half of the list and hand
  // back every company advert regardless -- which reads as a broken filter
  // rather than a partial one. Both halves are already in memory here.
  const locationOptions = useMemo(() => {
    // Keyed by lowercase so one region cannot appear twice under two
    // spellings; the first spelling seen is the one displayed.
    const tally = new Map<string, { label: string; count: number }>();
    for (const job of mappedJobs) {
      const region = regionOf(job.location);
      if (!region) continue;
      const key = region.toLowerCase();
      const row = tally.get(key);
      if (row) row.count += 1;
      else tally.set(key, { label: region, count: 1 });
    }
    // Busiest first, so the places with jobs in them are at the top of the
    // menu; ties fall back to alphabetical to keep the order stable.
    return [...tally.values()].sort(
      (a, b) => b.count - a.count || a.label.localeCompare(b.label)
    );
  }, [mappedJobs]);

  const jobs = useMemo(() => {
    const wanted = location.trim().toLowerCase();
    const visible = mappedJobs.filter(job => {
      if (view === 'saved' && !job.isSaved) return false;
      if (wanted && regionOf(job.location).toLowerCase() !== wanted) return false;
      return true;
    });
    // Scored jobs first, best match first. Unmatched jobs keep the order the
    // API returned them in (newest first) rather than being ranked arbitrarily.
    return visible.sort((a, b) => {
      if (a.matchScore === null && b.matchScore === null) return 0;
      if (a.matchScore === null) return 1;
      if (b.matchScore === null) return -1;
      return b.matchScore - a.matchScore;
    });
  }, [mappedJobs, view, location]);

  const savedCount = useMemo(
    () => scrapedJobs.filter(job => job.is_saved).length, [scrapedJobs]);

  // Keep the detail panel pointing at something that is actually in the list.
  //
  // Selection used to be seeded from the scraped results alone, so a search
  // matching only company adverts left the panel empty; and a selection that
  // survived into a result set no longer containing it left it empty too.
  // Both are the same question -- is the current selection still on screen --
  // so both are answered here, against the merged list the user can see.
  //
  // Derived rather than synced back into state by an effect. selectedId holds
  // only what the student actually clicked; which job is *shown* is a question
  // about the current list, and answering it during render means there is no
  // pass where the panel points at a job that has been filtered away.
  const selectedJob = useMemo(
    () => jobs.find(job => job.id === selectedId) ?? jobs[0] ?? null,
    [jobs, selectedId]
  );
  // What the rest of the page should read: the job on screen, which is not the
  // clicked one when that has been filtered out from under it.
  const activeId = selectedJob?.id ?? null;

  // Company jobs arrive with their description already; only scraped ones need
  // a second request. Both the text and the loading flag are derived rather
  // than set inside the effect, which also stops a stale description showing
  // while a new one loads.
  const needsDescriptionFetch = Boolean(selectedJob) && !selectedJob?.description;
  const descLoading = needsDescriptionFetch && fetchedDescription?.id !== activeId;
  const description =
    selectedJob?.description ??
    (fetchedDescription?.id === activeId ? fetchedDescription.text : '');

  useEffect(() => {
    if (!activeId || !needsDescriptionFetch) return;
    let cancelled = false;

    fetch(`${API_BASE}/api/scrape-jobs/scraped/${activeId}/`)
      .then(r => r.json())
      .then(data => {
        if (!cancelled) setFetchedDescription({ id: activeId, text: data.description ?? '' });
      })
      .catch(() => {
        if (!cancelled) setFetchedDescription({ id: activeId, text: '' });
      });

    return () => { cancelled = true; };
  }, [activeId, needsDescriptionFetch]);

  // Fetch the student's skills and proficiencies once on mount. Both the
  // per-skill verdict and the level captions read from this.
  useEffect(() => {
    if (!localStorage.getItem('accessToken')) return;
    apiFetch('/api/auth/student/skills/')
      .then(r => r.json())
      .then((data: { skill_name: string; skill_level: string }[]) => {
        if (!Array.isArray(data)) return;
        setMyLevels(Object.fromEntries(
          data.map(row => [row.skill_name.toLowerCase(), row.skill_level])
        ));
      })
      .catch(() => {});
  }, []);

  // Fetch jobs from both endpoints — debounced on search change
  useEffect(() => {
    const timer = setTimeout(() => {
      setIsLoading(true);
      const params = new URLSearchParams();
      if (search) params.set('search', search);

      // Both requests go through apiFetch so they carry the bearer token. The
      // scraped endpoint is public, but match_score is computed against the
      // logged-in student — fetching it anonymously returned null for every
      // scraped job, which is most of the feed.
      Promise.all([
        apiFetch(`/api/scrape-jobs/scraped/?${params}`)
          .then(r => r.json())
          .then(data => {
            const list: ScrapedJob[] = Array.isArray(data) ? data : (data.results ?? []);
            setScrapedJobs(list);
            return list;
          })
          .catch(() => []),
        apiFetch(`/api/job-listings/public/?${params}`)
          .then(r => r.json())
          .then(data => {
            const list: CompanyJob[] = Array.isArray(data) ? data : (data.results ?? []);
            setCompanyJobs(list);
            return list;
          })
          .catch(() => []),
      ]).finally(() => setIsLoading(false));
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

                <div className="rounded-lg border border-neutral-200 bg-neutral-50 p-3">
                  <Checkbox
                    checked={cvProcessingAck}
                    disabled={!notice}
                    onChange={e => setCvProcessingAck(e.target.checked)}
                    label={
                      <>
                        {notice?.cv_notice?.acknowledgement
                          ?? notice?.consent_statements?.CV_PROCESSING_CONSENT
                          ?? 'Loading…'}{' '}
                        <a
                          href="/privacy-notice"
                          target="_blank"
                          rel="noopener noreferrer"
                          className="font-semibold text-primary hover:underline"
                          onClick={e => e.stopPropagation()}
                        >
                          How we use your CV
                        </a>
                      </>
                    }
                  />
                </div>

                <input
                  type="file"
                  accept=".pdf"
                  disabled={!cvAckGiven}
                  onChange={async e => {
                    const file = e.target.files?.[0] ?? null;
                    setCvFile(file);
                    setParsedCv(null);
                    setExcludedSkillIds([]);
                    setEducationLines([]);
                    setExperienceLines([]);
                    if (!file) return;
                    setParsingCv(true);
                    setFormError('');
                    const { data, error } = await parseCv(file);
                    setParsingCv(false);
                    if (error) {
                      setFormError(error);
                      setEducationLines([]);
                      setExperienceLines([]);
                    } else {
                      setParsedCv(data ?? null);
                      setEducationLines(data?.education ?? []);
                      setExperienceLines(data?.experience ?? []);
                    }
                  }}
                  className="w-full text-sm text-neutral-600 file:mr-3 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-xs file:font-bold file:bg-primary/10 file:text-primary hover:file:bg-primary/20 file:cursor-pointer disabled:opacity-50 disabled:file:cursor-not-allowed"
                />
                <p className="text-xs text-neutral-500">
                  {cvAckGiven
                    ? 'PDF only, 10MB maximum.'
                    : 'Tick the box above to attach your CV.'}
                </p>
                {parsingCv && <p className="text-xs text-neutral-500">Reading your CV…</p>}

                {parsedCv && (
                  <div className="rounded-lg border border-neutral-200 bg-neutral-50 p-4 space-y-3">
                    <p className="text-xs font-bold text-neutral-900">
                      Check what we found. Untick anything that is wrong.
                    </p>

                    <div>
                      <p className="text-[10px] font-black text-neutral-400 uppercase tracking-widest mb-1">Skills</p>
                      {parsedCv.skills.length === 0 ? (
                        <p className="text-xs text-neutral-500">
                          No skills we recognise were found in this CV.
                        </p>
                      ) : (
                        <div className="flex flex-wrap gap-2">
                          {parsedCv.skills.map(skill => {
                            const excluded = excludedSkillIds.includes(skill.skill_id);
                            return (
                              <button
                                key={skill.skill_id}
                                type="button"
                                onClick={() => setExcludedSkillIds(prev =>
                                  excluded
                                    ? prev.filter(id => id !== skill.skill_id)
                                    : [...prev, skill.skill_id])}
                                className={cn(
                                  'px-3 py-1.5 rounded-full text-xs font-bold border transition-colors',
                                  excluded
                                    ? 'bg-white text-neutral-400 border-neutral-200 line-through'
                                    : 'bg-indigo-50 text-primary border-indigo-100'
                                )}
                              >
                                {skill.skill_name}
                              </button>
                            );
                          })}
                        </div>
                      )}
                    </div>

                    <EditableLines
                      label="Education"
                      lines={educationLines}
                      onChange={setEducationLines}
                    />

                    <EditableLines
                      label="Experience"
                      lines={experienceLines}
                      onChange={setExperienceLines}
                    />
                  </div>
                )}
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

            <div className="px-6 py-4 border-t border-neutral-100 space-y-3">
              {/* The disclosure, stated where the decision is made. Deliberately
                  not a checkbox: pressing Submit is the affirmative act, and a
                  tick box in front of a button the student has already chosen to
                  press adds friction without adding information. The company is
                  not named here — the record identifies it through the
                  application, so the audit trail loses nothing. */}
              <p className="text-xs leading-relaxed text-neutral-500">
                {notice?.application_disclosure
                  || 'By submitting, you agree that the information in this '
                     + 'application will be shared with the employer for '
                     + 'recruitment purposes.'}
              </p>
              <div className="flex gap-3">
                <Button variant="outline" fullWidth className="h-11" disabled={submitting} onClick={() => setApplyModalJob(null)}>Cancel</Button>
                <Button fullWidth className="h-11" isLoading={submitting} onClick={submitApplication}>Submit Application</Button>
              </div>
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
          {/* The shortlist sits beside the search rather than on its own
              page: the student is already looking at jobs, and a saved one is
              the same card with the same detail panel next to it. */}
          <div className="flex items-center gap-1 rounded-xl bg-neutral-100 p-1">
            {([
              { key: 'all' as const, label: 'All jobs' },
              { key: 'saved' as const, label: `Saved${savedCount ? ` (${savedCount})` : ''}` },
            ]).map(tab => (
              <button
                key={tab.key}
                type="button"
                onClick={() => setView(tab.key)}
                className={cn(
                  'flex-1 h-9 rounded-lg text-sm font-bold transition-colors',
                  view === tab.key
                    ? 'bg-white text-primary shadow-sm'
                    : 'text-neutral-500 hover:text-neutral-800',
                )}
              >
                {tab.label}
              </button>
            ))}
          </div>

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

          {/* Hidden until there is more than one place to choose between: a
              menu whose only entry is the one location already shown on every
              card is a control that cannot change anything. */}
          {locationOptions.length > 1 && (
            <div className="relative">
              <MapPin className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400" size={18} />
              <select
                aria-label="Filter by location"
                value={location}
                onChange={e => setLocation(e.target.value)}
                className="w-full h-11 pl-10 pr-10 bg-white border border-neutral-300 rounded-xl text-sm font-semibold text-neutral-700 appearance-none cursor-pointer focus:outline-none focus:ring-2 focus:ring-primary/20"
              >
                <option value="">All locations</option>
                {locationOptions.map(option => (
                  <option key={option.label} value={option.label}>
                    {option.label} ({option.count})
                  </option>
                ))}
              </select>
              <ChevronDown
                className="absolute right-3 top-1/2 -translate-y-1/2 text-neutral-400 pointer-events-none"
                size={16}
              />
            </div>
          )}

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
                className={cn('p-5 cursor-pointer transition-all border-l-4', activeId === job.id ? 'border-l-primary bg-indigo-50/30' : 'border-l-transparent')}
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
                      {job.matchScore !== null && (
                        <Badge
                          variant={job.matchScore > 70 ? 'success' : job.matchScore > 40 ? 'warning' : 'danger'}
                          className="shrink-0"
                        >
                          {job.matchScore}% match
                        </Badge>
                      )}
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
                          const verdict = skillVerdict(
                            requiredLevelFor(job, skill),
                            myLevels[skill.toLowerCase()],
                          );
                          return (
                            <span key={skill} className={cn(
                              'px-2 py-0.5 rounded-full text-[10px] font-bold',
                              verdict === 'met' && 'bg-emerald-100 text-emerald-700',
                              verdict === 'partial' && 'bg-amber-100 text-amber-700',
                              verdict === 'missing' && 'bg-neutral-100 text-neutral-500',
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
                {/* The location filter is named when it is the reason the list
                    is empty. "Nothing saved yet" beside a filtered-out
                    shortlist told the student their bookmarks were gone. */}
                {view === 'saved' ? (
                  <>
                    <Bookmark size={40} className="mx-auto text-neutral-200 mb-2" />
                    <p className="text-sm font-bold text-neutral-500">
                      {location ? `Nothing saved in ${location}` : 'Nothing saved yet'}
                    </p>
                    <p className="text-xs text-neutral-400 mt-1">
                      {location
                        ? 'Choose All locations to see the rest of your saved jobs.'
                        : 'Open a job and press the bookmark to keep it here.'}
                    </p>
                  </>
                ) : (
                  <>
                    <Briefcase size={40} className="mx-auto text-neutral-200 mb-2" />
                    <p className="text-sm font-bold text-neutral-500">No jobs found</p>
                    <p className="text-xs text-neutral-400 mt-1">
                      {location
                        ? `No jobs in ${location} match your search. Try another location.`
                        : 'Try a different search term'}
                    </p>
                  </>
                )}
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
                    {selectedJob.sourceType === 'scraped' && (
                      <Button
                        variant="outline"
                        className="h-11 px-4"
                        onClick={() => toggleSaved(selectedJob)}
                        isLoading={savingId === selectedJob.id}
                        aria-pressed={selectedJob.isSaved}
                        title={selectedJob.isSaved ? 'Remove from saved' : 'Save this job'}
                      >
                        <Bookmark
                          size={20}
                          className={selectedJob.isSaved ? 'text-primary' : ''}
                          fill={selectedJob.isSaved ? 'currentColor' : 'none'}
                        />
                      </Button>
                    )}
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
                        const requiredLevel = requiredLevelFor(selectedJob, skill);
                        const studentLevel = myLevels[skill.toLowerCase()];
                        const verdict = skillVerdict(requiredLevel, studentLevel);
                        return (
                          <div key={skill} className={cn(
                            'p-4 rounded-xl border flex items-center justify-between gap-3',
                            verdict === 'met' && 'bg-emerald-50 border-emerald-100 text-success',
                            verdict === 'partial' && 'bg-amber-50 border-amber-100 text-amber-700',
                            verdict === 'missing' && 'bg-neutral-50 border-neutral-100 text-neutral-400',
                          )}>
                            <div className="min-w-0">
                              <span className="text-sm font-bold block truncate">{skill}</span>
                              {verdict === 'partial' && (
                                <span className="text-[11px] font-semibold">
                                  You are {LEVEL_LABEL[studentLevel!] ?? studentLevel} · asks for{' '}
                                  {LEVEL_LABEL[requiredLevel!] ?? requiredLevel}
                                </span>
                              )}
                              {verdict === 'met' && requiredLevel && (
                                <span className="text-[11px] font-semibold opacity-70">
                                  {LEVEL_LABEL[requiredLevel] ?? requiredLevel} required
                                </span>
                              )}
                            </div>
                            {verdict === 'met' && <CheckCircle2 size={18} className="shrink-0" />}
                            {verdict === 'partial' && <AlertCircle size={18} className="shrink-0" />}
                            {verdict === 'missing' && <XCircle size={18} className="text-neutral-300 shrink-0" />}
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
                    <RichText className="text-sm text-neutral-700 leading-relaxed rich-text"
                      html={description} />
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
