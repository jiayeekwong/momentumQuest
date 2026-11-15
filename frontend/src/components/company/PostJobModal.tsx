'use client';

import { useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { Briefcase, Calendar, CheckCircle2, MapPin, Plus, X } from 'lucide-react';
import { apiFetch, API_BASE } from '@/src/lib/apiFetch';
import { Button, Input } from '@/src/components/ui';
import { RichTextEditor } from '@/src/components/RichTextEditor';

type SkillLevel = 'BEGINNER' | 'INTERMEDIATE' | 'ADVANCED';

interface RequiredSkill {
  name: string;
  level: SkillLevel | null;
}

interface JobCategory {
  id: number;
  category_name: string;
}

export interface PostedJob {
  id: number;
  job_title: string;
  applicants_count: number;
  closing_date: string | null;
  status: string;
  work_mode: string;
  experience_level: string;
  posted_time: string;
}

interface PostJobModalProps {
  open: boolean;
  onClose: () => void;
  onCreated?: (job: PostedJob) => void;
}

const workModes = ['On-site', 'Hybrid', 'Remote'];
const experienceLevels = ['Entry Level', 'Mid Level', 'Senior Level', 'Internship'];
const skillLevels: { value: SkillLevel; label: string }[] = [
  { value: 'BEGINNER', label: 'Beginner' },
  { value: 'INTERMEDIATE', label: 'Intermediate' },
  { value: 'ADVANCED', label: 'Advanced' },
];

function formatApiError(data: unknown): string {
  if (!data || typeof data !== 'object') {
    return 'Could not post this job. Please try again.';
  }
  const record = data as Record<string, unknown>;
  if (typeof record.detail === 'string') return record.detail;

  const parts = Object.entries(record).map(([field, value]) => {
    const text = Array.isArray(value) ? value.join(' ') : String(value);
    const label = field.replace(/_/g, ' ').replace(/^./, char => char.toUpperCase());
    return field === 'non_field_errors' ? text : `${label}: ${text}`;
  });
  return parts.join(' • ') || 'Could not post this job. Please try again.';
}

export function PostJobModal({ open, onClose, onCreated }: PostJobModalProps) {
  const [categories, setCategories] = useState<JobCategory[]>([]);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [title, setTitle] = useState('');
  const [categoryId, setCategoryId] = useState('');
  const [salaryMin, setSalaryMin] = useState('');
  const [salaryMax, setSalaryMax] = useState('');
  const [workMode, setWorkMode] = useState('');
  const [experience, setExperience] = useState('');
  const [closing, setClosing] = useState('');
  const [description, setDescription] = useState('');
  const [skillInput, setSkillInput] = useState('');
  const [skills, setSkills] = useState<RequiredSkill[]>([]);
  const [skillLevel, setSkillLevel] = useState<SkillLevel>('INTERMEDIATE');
  const successTimer = useRef<number | null>(null);

  useEffect(() => {
    if (!open || categories.length > 0) return;
    fetch(`${API_BASE}/api/scrape-jobs/categories/`)
      .then(response => response.json())
      .then(data => setCategories(Array.isArray(data) ? data : (data.results ?? [])))
      .catch(() => {});
  }, [open, categories.length]);

  useEffect(() => {
    if (!open) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !submitting) onClose();
    };
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [open, submitting, onClose]);

  useEffect(() => () => {
    if (successTimer.current !== null) window.clearTimeout(successTimer.current);
  }, []);

  const resetForm = () => {
    setSubmitted(false);
    setError('');
    setTitle('');
    setCategoryId('');
    setSalaryMin('');
    setSalaryMax('');
    setWorkMode('');
    setExperience('');
    setClosing('');
    setDescription('');
    setSkillInput('');
    setSkills([]);
    setSkillLevel('INTERMEDIATE');
  };

  const addSkill = () => {
    const trimmed = skillInput.trim();
    if (!trimmed || skills.some(skill => skill.name.toLowerCase() === trimmed.toLowerCase())) {
      return;
    }
    setSkills(current => [...current, { name: trimmed, level: skillLevel }]);
    setSkillInput('');
  };

  const close = () => {
    if (!submitting) onClose();
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError('');

    if (!description || description === '<p></p>') {
      setError('Job description cannot be empty.');
      return;
    }

    setSubmitting(true);
    const payload: Record<string, unknown> = {
      job_title: title,
      description,
      work_mode: workMode,
      experience_level: experience,
      closing_date: closing || null,
      required_skills: skills.map(skill => ({
        name: skill.name,
        level: skill.level,
      })),
    };
    if (categoryId) payload.category = Number(categoryId);
    if (salaryMin) payload.salary_min = Number(salaryMin);
    if (salaryMax) payload.salary_max = Number(salaryMax);

    try {
      const response = await apiFetch('/api/job-listings/jobs/', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      const data = await response.json().catch(() => null);

      if (response.status !== 201) {
        setError(formatApiError(data));
        return;
      }

      const job = data as PostedJob;
      onCreated?.(job);
      setSubmitted(true);
      successTimer.current = window.setTimeout(() => {
        resetForm();
        onClose();
      }, 1800);
    } catch {
      setError('Network error. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          key="post-job-backdrop"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-black/40 px-4 py-8 backdrop-blur-sm"
          onMouseDown={event => {
            if (event.target === event.currentTarget) close();
          }}
        >
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-labelledby="post-job-modal-title"
            initial={{ scale: 0.95, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.95, opacity: 0 }}
            transition={{ type: 'spring', stiffness: 300, damping: 30 }}
            className="my-auto w-full max-w-2xl overflow-hidden rounded-2xl bg-white shadow-2xl"
          >
            {submitted ? (
              <div className="p-10 text-center sm:p-14">
                <div className="mx-auto mb-5 flex h-20 w-20 items-center justify-center rounded-full bg-emerald-50 text-success">
                  <CheckCircle2 size={42} />
                </div>
                <h2 id="post-job-modal-title" className="text-2xl font-black text-neutral-900">
                  Job Posted Successfully!
                </h2>
                <p className="mt-2 text-sm text-neutral-500">
                  Your listing is now live and visible to students.
                </p>
              </div>
            ) : (
              <>
                <div className="flex items-start justify-between gap-4 border-b border-neutral-100 p-6 sm:p-7">
                  <div>
                    <h2 id="post-job-modal-title" className="text-2xl font-bold text-neutral-900">
                      Post a Job Listing
                    </h2>
                    <p className="mt-1 text-sm text-neutral-500">
                      Add the role details students need before applying.
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={close}
                    disabled={submitting}
                    aria-label="Close post job form"
                    className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-neutral-400 transition-colors hover:bg-neutral-100 hover:text-neutral-700 disabled:opacity-40"
                  >
                    <X size={20} />
                  </button>
                </div>

                <form onSubmit={handleSubmit}>
                  <div className="max-h-[calc(100vh-220px)] space-y-6 overflow-y-auto p-6 sm:p-7">
                    {error && (
                      <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm font-medium text-red-700">
                        {error}
                      </div>
                    )}

                    <Input label="Job Title" placeholder="e.g. Junior Data Scientist" value={title} onChange={event => setTitle(event.target.value)} required />

                    <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
                      <div className="space-y-2">
                        <label className="block text-[10px] font-black uppercase tracking-widest text-neutral-900">Category</label>
                        <select value={categoryId} onChange={event => setCategoryId(event.target.value)}
                          className="h-10 w-full rounded-lg border border-neutral-300 bg-white px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/20">
                          <option value="">Select category</option>
                          {categories.map(category => (
                            <option key={category.id} value={category.id}>{category.category_name}</option>
                          ))}
                        </select>
                      </div>
                      <div className="space-y-2">
                        <label className="block text-[10px] font-black uppercase tracking-widest text-neutral-900">Experience Level</label>
                        <select value={experience} onChange={event => setExperience(event.target.value)} required
                          className="h-10 w-full rounded-lg border border-neutral-300 bg-white px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/20">
                          <option value="">Select level</option>
                          {experienceLevels.map(level => <option key={level}>{level}</option>)}
                        </select>
                      </div>
                    </div>

                    <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
                      <Input label="Salary Min (RM)" type="number" min="0" placeholder="e.g. 3000" value={salaryMin} onChange={event => setSalaryMin(event.target.value)} />
                      <Input label="Salary Max (RM)" type="number" min="0" placeholder="e.g. 6000" value={salaryMax} onChange={event => setSalaryMax(event.target.value)} />
                    </div>

                    <div className="space-y-2">
                      <label className="block text-[10px] font-black uppercase tracking-widest text-neutral-900">Work Mode</label>
                      <div className="grid grid-cols-3 gap-2">
                        {workModes.map(mode => (
                          <button key={mode} type="button" onClick={() => setWorkMode(mode)}
                            className={`rounded-lg border py-2 text-xs font-bold transition-all ${workMode === mode ? 'border-primary bg-primary text-white' : 'border-neutral-200 bg-white text-neutral-600 hover:border-primary/40'}`}>
                            <MapPin size={12} className="mr-1 inline" />{mode}
                          </button>
                        ))}
                      </div>
                    </div>

                    <Input label="Application Closing Date" type="date" value={closing} onChange={event => setClosing(event.target.value)} required icon={<Calendar size={16} />} />

                    <div className="space-y-2">
                      <label className="block text-[10px] font-black uppercase tracking-widest text-neutral-900">Job Description</label>
                      <RichTextEditor value={description} onChange={setDescription} minHeight={150} />
                    </div>

                    <div className="space-y-3">
                      <div>
                        <label className="block text-[10px] font-black uppercase tracking-widest text-neutral-900">Required Skills</label>
                        <p className="mt-1 text-xs text-neutral-500">Set the proficiency candidates need for each skill.</p>
                      </div>
                      <div className="flex flex-col gap-2 sm:flex-row">
                        <input value={skillInput} onChange={event => setSkillInput(event.target.value)}
                          onKeyDown={event => event.key === 'Enter' && (event.preventDefault(), addSkill())}
                          placeholder="Type a skill and press Enter"
                          className="h-10 min-w-0 flex-1 rounded-lg border border-neutral-300 bg-white px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/20" />
                        <select value={skillLevel} onChange={event => setSkillLevel(event.target.value as SkillLevel)}
                          aria-label="Required proficiency for the next skill"
                          className="h-10 rounded-lg border border-neutral-300 bg-white px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/20">
                          {skillLevels.map(level => (
                            <option key={level.value} value={level.value}>{level.label}</option>
                          ))}
                        </select>
                        <Button type="button" variant="outline" className="h-10" onClick={addSkill} aria-label="Add required skill">
                          <Plus size={16} /> <span className="sm:hidden">Add skill</span>
                        </Button>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {skills.map(skill => (
                          <span key={skill.name} className="flex items-center gap-1.5 rounded-full bg-indigo-50 py-1.5 pl-3 pr-2 text-xs font-bold text-primary">
                            {skill.name}
                            <select
                              value={skill.level ?? ''}
                              onChange={event => setSkills(current => current.map(entry =>
                                entry.name === skill.name
                                  ? { ...entry, level: event.target.value ? event.target.value as SkillLevel : null }
                                  : entry))}
                              aria-label={`Required proficiency for ${skill.name}`}
                              className="cursor-pointer bg-transparent text-[10px] font-black uppercase tracking-wider focus:outline-none"
                            >
                              <option value="">Not stated</option>
                              {skillLevels.map(level => (
                                <option key={level.value} value={level.value}>{level.label}</option>
                              ))}
                            </select>
                            <button type="button" onClick={() => setSkills(current => current.filter(entry => entry.name !== skill.name))}
                              aria-label={`Remove ${skill.name}`} className="hover:text-danger">
                              <X size={12} />
                            </button>
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>

                  <div className="flex gap-3 border-t border-neutral-100 p-5 sm:px-7">
                    <Button type="button" variant="outline" fullWidth onClick={close} disabled={submitting}>Cancel</Button>
                    <Button type="submit" fullWidth isLoading={submitting} disabled={submitting}>
                      <Briefcase size={16} /> {submitting ? 'Posting...' : 'Post Job'}
                    </Button>
                  </div>
                </form>
              </>
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
