'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Briefcase, MapPin, Calendar, Plus, X, CheckCircle2 } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { DashboardLayout } from '@/src/components/Layout';
import { Card, Button, Input } from '@/src/components/ui';
import { apiFetch } from '@/src/lib/apiFetch';

const workModes = ['On-site', 'Hybrid', 'Remote'];
const experienceLevels = ['Entry Level', 'Mid Level', 'Senior Level', 'Internship'];

interface JobCategory { id: number; category_name: string; }

export default function PostJobPage() {
  const router = useRouter();
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const [title, setTitle] = useState('');
  const [categoryId, setCategoryId] = useState('');
  const [salaryMin, setSalaryMin] = useState('');
  const [salaryMax, setSalaryMax] = useState('');
  const [workMode, setWorkMode] = useState('');
  const [experience, setExperience] = useState('');
  const [closing, setClosing] = useState('');
  const [description, setDescription] = useState('');
  const [skillInput, setSkillInput] = useState('');
  const [skills, setSkills] = useState<string[]>([]);
  const [categories, setCategories] = useState<JobCategory[]>([]);

  useEffect(() => {
    fetch('http://localhost:8000/api/scrape-jobs/categories/')
      .then(r => r.json())
      .then(data => setCategories(Array.isArray(data) ? data : (data.results ?? [])))
      .catch(() => {});
  }, []);

  const addSkill = () => {
    const trimmed = skillInput.trim();
    if (trimmed && !skills.includes(trimmed)) {
      setSkills(prev => [...prev, trimmed]);
      setSkillInput('');
    }
  };

  const removeSkill = (skill: string) => setSkills(prev => prev.filter(s => s !== skill));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setIsSubmitting(true);

    const payload: Record<string, unknown> = {
      job_title:        title,
      description,
      work_mode:        workMode,
      experience_level: experience,
      closing_date:     closing || null,
      required_skills:  skills,
    };
    if (categoryId) payload.category = Number(categoryId);
    if (salaryMin)  payload.salary_min = Number(salaryMin);
    if (salaryMax)  payload.salary_max = Number(salaryMax);

    try {
      const res = await apiFetch('/api/job-listings/jobs/', {
        method: 'POST',
        body: JSON.stringify(payload),
      });

      if (res.status === 201) {
        setSubmitted(true);
        setTimeout(() => router.push('/manage-listings'), 2500);
      } else {
        const data = await res.json();
        setError(JSON.stringify(data));
      }
    } catch {
      setError('Network error. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <DashboardLayout title="Post a Job">
      <div className="max-w-3xl mx-auto">
        <AnimatePresence mode="wait">
          {!submitted ? (
            <motion.div key="form" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
              <div className="mb-8">
                <h2 className="text-2xl font-bold text-neutral-900">Create a Job Listing</h2>
                <p className="text-neutral-500 mt-1">Fill in the details below to post a new job opening.</p>
              </div>

              <Card className="p-8">
                {error && (
                  <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-xl text-sm text-red-700 font-medium">
                    {error}
                  </div>
                )}
                <form onSubmit={handleSubmit} className="space-y-6">
                  <Input label="Job Title" placeholder="e.g. Junior Data Scientist" value={title} onChange={e => setTitle(e.target.value)} required />

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div className="space-y-2">
                      <label className="text-[10px] font-black text-neutral-900 uppercase tracking-widest block">Category</label>
                      <select value={categoryId} onChange={e => setCategoryId(e.target.value)}
                        className="w-full h-10 px-3 bg-white border border-neutral-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20">
                        <option value="">Select category</option>
                        {categories.map(c => <option key={c.id} value={c.id}>{c.category_name}</option>)}
                      </select>
                    </div>
                    <div className="space-y-2">
                      <label className="text-[10px] font-black text-neutral-900 uppercase tracking-widest block">Experience Level</label>
                      <select value={experience} onChange={e => setExperience(e.target.value)} required
                        className="w-full h-10 px-3 bg-white border border-neutral-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20">
                        <option value="">Select level</option>
                        {experienceLevels.map(l => <option key={l}>{l}</option>)}
                      </select>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <Input label="Salary Min (RM)" type="number" placeholder="e.g. 3000" value={salaryMin} onChange={e => setSalaryMin(e.target.value)} />
                    <Input label="Salary Max (RM)" type="number" placeholder="e.g. 6000" value={salaryMax} onChange={e => setSalaryMax(e.target.value)} />
                  </div>

                  <div className="space-y-2">
                    <label className="text-[10px] font-black text-neutral-900 uppercase tracking-widest block">Work Mode</label>
                    <div className="flex gap-2">
                      {workModes.map(mode => (
                        <button key={mode} type="button" onClick={() => setWorkMode(mode)}
                          className={`flex-1 py-2 rounded-lg text-xs font-bold border transition-all ${workMode === mode ? 'bg-primary text-white border-primary' : 'bg-white text-neutral-600 border-neutral-200 hover:border-primary/40'}`}>
                          <MapPin size={12} className="inline mr-1" />{mode}
                        </button>
                      ))}
                    </div>
                  </div>

                  <Input label="Application Closing Date" type="date" value={closing} onChange={e => setClosing(e.target.value)} required icon={<Calendar size={16} />} />

                  <div className="space-y-2">
                    <label className="text-[10px] font-black text-neutral-900 uppercase tracking-widest block">Job Description</label>
                    <textarea required value={description} onChange={e => setDescription(e.target.value)}
                      className="w-full h-36 p-4 bg-white border border-neutral-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
                      placeholder="Describe the role, responsibilities, and what you're looking for..." />
                  </div>

                  <div className="space-y-3">
                    <label className="text-[10px] font-black text-neutral-900 uppercase tracking-widest block">Required Skills</label>
                    <div className="flex gap-2">
                      <input value={skillInput} onChange={e => setSkillInput(e.target.value)}
                        onKeyDown={e => e.key === 'Enter' && (e.preventDefault(), addSkill())}
                        placeholder="Type a skill and press Enter"
                        className="flex-1 h-10 px-3 bg-white border border-neutral-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20" />
                      <Button type="button" variant="outline" size="sm" className="h-10" onClick={addSkill}>
                        <Plus size={16} />
                      </Button>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {skills.map(skill => (
                        <span key={skill} className="flex items-center gap-1.5 px-3 py-1.5 bg-indigo-50 text-primary rounded-full text-xs font-bold">
                          {skill}
                          <button type="button" onClick={() => removeSkill(skill)} className="hover:text-danger"><X size={12} /></button>
                        </span>
                      ))}
                    </div>
                  </div>

                  <div className="flex gap-4 pt-2">
                    <Button type="button" variant="outline" fullWidth onClick={() => router.back()}>Cancel</Button>
                    <Button type="submit" fullWidth disabled={isSubmitting}>
                      <Briefcase size={16} className="mr-2" /> {isSubmitting ? 'Posting...' : 'Post Job'}
                    </Button>
                  </div>
                </form>
              </Card>
            </motion.div>
          ) : (
            <motion.div key="success" initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} className="py-20 text-center">
              <div className="w-24 h-24 bg-emerald-50 text-success rounded-full flex items-center justify-center mx-auto mb-6">
                <CheckCircle2 size={48} />
              </div>
              <h3 className="text-2xl font-black text-neutral-900">Job Posted Successfully!</h3>
              <p className="text-neutral-500 mt-2">Your listing is now live. Redirecting to manage listings...</p>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </DashboardLayout>
  );
}
