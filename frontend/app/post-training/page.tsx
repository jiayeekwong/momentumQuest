'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { GraduationCap, Clock, Plus, X, CheckCircle2, ExternalLink } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { DashboardLayout } from '@/src/components/Layout';
import { Card, Button, Input } from '@/src/components/ui';

const courseTypes = ['Course', 'Workshop', 'Webinar', 'Bootcamp', 'Certification'];
const levels = ['Beginner', 'Intermediate', 'Advanced', 'All Levels'];

export default function PostTrainingPage() {
  const router = useRouter();
  const [submitted, setSubmitted] = useState(false);

  const [title, setTitle] = useState('');
  const [provider, setProvider] = useState('');
  const [courseType, setCourseType] = useState('');
  const [level, setLevel] = useState('');
  const [duration, setDuration] = useState('');
  const [url, setUrl] = useState('');
  const [description, setDescription] = useState('');
  const [skillInput, setSkillInput] = useState('');
  const [skills, setSkills] = useState<string[]>([]);

  const addSkill = () => {
    const trimmed = skillInput.trim();
    if (trimmed && !skills.includes(trimmed)) {
      setSkills((prev) => [...prev, trimmed]);
      setSkillInput('');
    }
  };

  const removeSkill = (skill: string) => setSkills((prev) => prev.filter((s) => s !== skill));

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitted(true);
    setTimeout(() => router.push('/company-dashboard'), 2500);
  };

  return (
    <DashboardLayout title="Post Training">
      <div className="max-w-3xl mx-auto">
        <AnimatePresence mode="wait">
          {!submitted ? (
            <motion.div key="form" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
              <div className="mb-8">
                <h2 className="text-2xl font-bold text-neutral-900">Submit a Training Resource</h2>
                <p className="text-neutral-500 mt-1">Share relevant courses or workshops with students on the platform.</p>
              </div>

              <Card className="p-8">
                <form onSubmit={handleSubmit} className="space-y-6">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <Input label="Course Title" placeholder="e.g. NLP Specialization" value={title} onChange={(e) => setTitle(e.target.value)} required />
                    <Input label="Provider / Platform" placeholder="e.g. Coursera, Udemy" value={provider} onChange={(e) => setProvider(e.target.value)} required />
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div className="space-y-2">
                      <label className="text-[10px] font-black text-neutral-900 uppercase tracking-widest block">Course Type</label>
                      <select value={courseType} onChange={(e) => setCourseType(e.target.value)} required
                        className="w-full h-10 px-3 bg-white border border-neutral-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20">
                        <option value="">Select type</option>
                        {courseTypes.map((t) => <option key={t}>{t}</option>)}
                      </select>
                    </div>
                    <div className="space-y-2">
                      <label className="text-[10px] font-black text-neutral-900 uppercase tracking-widest block">Level</label>
                      <select value={level} onChange={(e) => setLevel(e.target.value)} required
                        className="w-full h-10 px-3 bg-white border border-neutral-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20">
                        <option value="">Select level</option>
                        {levels.map((l) => <option key={l}>{l}</option>)}
                      </select>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <Input label="Duration" placeholder="e.g. 40 hours / 6 weeks" value={duration} onChange={(e) => setDuration(e.target.value)} icon={<Clock size={16} />} required />
                    <Input label="Course URL" type="url" placeholder="https://..." value={url} onChange={(e) => setUrl(e.target.value)} icon={<ExternalLink size={16} />} />
                  </div>

                  <div className="space-y-2">
                    <label className="text-[10px] font-black text-neutral-900 uppercase tracking-widest block">Description</label>
                    <textarea value={description} onChange={(e) => setDescription(e.target.value)}
                      className="w-full h-28 p-4 bg-white border border-neutral-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
                      placeholder="What will students learn from this training?" />
                  </div>

                  <div className="space-y-3">
                    <label className="text-[10px] font-black text-neutral-900 uppercase tracking-widest block">Skills Covered</label>
                    <div className="flex gap-2">
                      <input value={skillInput} onChange={(e) => setSkillInput(e.target.value)}
                        onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), addSkill())}
                        placeholder="Type a skill and press Enter"
                        className="flex-1 h-10 px-3 bg-white border border-neutral-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20" />
                      <Button type="button" variant="outline" size="sm" className="h-10" onClick={addSkill}><Plus size={16} /></Button>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {skills.map((skill) => (
                        <span key={skill} className="flex items-center gap-1.5 px-3 py-1.5 bg-indigo-50 text-primary rounded-full text-xs font-bold">
                          {skill}
                          <button type="button" onClick={() => removeSkill(skill)} className="hover:text-danger"><X size={12} /></button>
                        </span>
                      ))}
                    </div>
                  </div>

                  <div className="flex gap-4 pt-2">
                    <Button type="button" variant="outline" fullWidth onClick={() => router.back()}>Cancel</Button>
                    <Button type="submit" fullWidth><GraduationCap size={16} className="mr-2" /> Submit Training</Button>
                  </div>
                </form>
              </Card>
            </motion.div>
          ) : (
            <motion.div key="success" initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} className="py-20 text-center">
              <div className="w-24 h-24 bg-emerald-50 text-success rounded-full flex items-center justify-center mx-auto mb-6">
                <CheckCircle2 size={48} />
              </div>
              <h3 className="text-2xl font-black text-neutral-900">Training Submitted!</h3>
              <p className="text-neutral-500 mt-2">Your resource is pending admin approval. Redirecting...</p>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </DashboardLayout>
  );
}
