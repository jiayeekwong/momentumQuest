'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { GraduationCap, Clock, CheckCircle2, XCircle, AlertCircle, BookOpen } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { DashboardLayout } from '@/src/components/Layout';
import { Card, Badge, Button, Input } from '@/src/components/ui';
import { apiFetch } from '@/src/lib/apiFetch';
import { cn } from '@/src/lib/utils';

interface TrainingProgramme {
  id: number;
  title: string;
  skill: string | null;
  programme_duration: string;
  description: string;
  approval_status: 'PENDING' | 'APPROVED' | 'REJECTED';
  submission_time: string;
}

const statusConfig = {
  PENDING:  { variant: 'warning'  as const, icon: AlertCircle,   label: 'Pending Review' },
  APPROVED: { variant: 'success'  as const, icon: CheckCircle2,  label: 'Approved' },
  REJECTED: { variant: 'danger'   as const, icon: XCircle,       label: 'Rejected' },
};

export default function PostTrainingPage() {
  const router = useRouter();
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const [title, setTitle] = useState('');
  const [skillName, setSkillName] = useState('');
  const [duration, setDuration] = useState('');
  const [description, setDescription] = useState('');

  const [programmes, setProgrammes] = useState<TrainingProgramme[]>([]);
  const [isLoadingList, setIsLoadingList] = useState(true);

  const fetchProgrammes = useCallback(() => {
    apiFetch('/api/resources/training/')
      .then(r => r.json())
      .then(data => setProgrammes(Array.isArray(data) ? data : []))
      .catch(() => {})
      .finally(() => setIsLoadingList(false));
  }, []);

  useEffect(() => { fetchProgrammes(); }, [fetchProgrammes]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setIsSubmitting(true);

    try {
      const res = await apiFetch('/api/resources/training/', {
        method: 'POST',
        body: JSON.stringify({
          title,
          description,
          skill_name:         skillName.trim() || undefined,
          programme_duration: duration,
        }),
      });

      if (res.status === 201) {
        const newProgramme = await res.json();
        setProgrammes(prev => [newProgramme, ...prev]);
        setSubmitted(true);
        setTimeout(() => {
          setSubmitted(false);
          setTitle('');
          setSkillName('');
          setDuration('');
          setDescription('');
        }, 2500);
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

  const formatDate = (d: string) =>
    new Date(d).toLocaleDateString('en-MY', { day: 'numeric', month: 'short', year: 'numeric' });

  return (
    <DashboardLayout title="Post Training">
      <div className="max-w-3xl mx-auto space-y-10">

        {/* ── My Submissions ── */}
        <div>
          <div className="flex items-center gap-2 mb-4">
            <BookOpen size={18} className="text-primary" />
            <h3 className="text-lg font-bold text-neutral-900">My Submissions</h3>
            <span className="ml-auto text-xs font-bold text-neutral-400">{programmes.length} total</span>
          </div>

          {isLoadingList ? (
            <div className="flex items-center justify-center py-12">
              <div className="w-7 h-7 border-4 border-primary/20 border-t-primary rounded-full animate-spin" />
            </div>
          ) : programmes.length === 0 ? (
            <Card className="p-10 text-center">
              <GraduationCap size={36} className="mx-auto text-neutral-200 mb-3" />
              <p className="text-sm font-bold text-neutral-500">No submissions yet</p>
              <p className="text-xs text-neutral-400 mt-1">Programmes you submit will appear here with their review status.</p>
            </Card>
          ) : (
            <div className="space-y-3">
              {programmes.map(prog => {
                const config = statusConfig[prog.approval_status];
                const Icon = config.icon;
                return (
                  <Card key={prog.id} className="p-5">
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-3 flex-wrap">
                          <h4 className="font-bold text-neutral-900 truncate">{prog.title}</h4>
                          {prog.skill && (
                            <span className="px-2 py-0.5 bg-indigo-50 text-primary rounded-full text-[10px] font-bold">
                              {prog.skill}
                            </span>
                          )}
                        </div>
                        <div className="flex flex-wrap items-center gap-4 mt-2 text-xs font-semibold text-neutral-500">
                          {prog.programme_duration && (
                            <span className="flex items-center gap-1">
                              <Clock size={11} /> {prog.programme_duration}
                            </span>
                          )}
                          <span>Submitted {formatDate(prog.submission_time)}</span>
                        </div>
                        {prog.description && (
                          <p className="text-xs text-neutral-400 mt-2 line-clamp-2">{prog.description}</p>
                        )}
                      </div>
                      <div className="shrink-0">
                        <Badge variant={config.variant} className={cn('flex items-center gap-1.5 px-3 py-1.5 text-[10px] font-black tracking-widest')}>
                          <Icon size={12} /> {config.label}
                        </Badge>
                      </div>
                    </div>
                  </Card>
                );
              })}
            </div>
          )}
        </div>

        {/* ── Form ── */}
        <AnimatePresence mode="wait">
          {!submitted ? (
            <motion.div key="form" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
              <div className="mb-8">
                <h2 className="text-2xl font-bold text-neutral-900">Submit a Training Programme</h2>
                <p className="text-neutral-500 mt-1">Share a training opportunity with students. It will be visible after admin approval.</p>
              </div>

              <Card className="p-8">
                {error && (
                  <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-xl text-sm text-red-700 font-medium">
                    {error}
                  </div>
                )}
                <form onSubmit={handleSubmit} className="space-y-6">
                  <Input label="Programme Title" placeholder="e.g. React Web Development Bootcamp" value={title}
                    onChange={e => setTitle(e.target.value)} required />

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <Input label="Related Skill" placeholder="e.g. React, Python, SQL" value={skillName}
                      onChange={e => setSkillName(e.target.value)} />
                    <Input label="Duration" placeholder="e.g. 6 weeks / 40 hours" value={duration}
                      onChange={e => setDuration(e.target.value)} icon={<Clock size={16} />} required />
                  </div>

                  <div className="space-y-2">
                    <label className="text-[10px] font-black text-neutral-900 uppercase tracking-widest block">Description</label>
                    <textarea value={description} onChange={e => setDescription(e.target.value)}
                      className="w-full h-36 p-4 bg-white border border-neutral-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
                      placeholder="What will students learn? Who is this for? Any prerequisites?" />
                  </div>

                  <div className="flex gap-4 pt-2">
                    <Button type="button" variant="outline" fullWidth onClick={() => router.back()}>Cancel</Button>
                    <Button type="submit" fullWidth disabled={isSubmitting}>
                      <GraduationCap size={16} className="mr-2" /> {isSubmitting ? 'Submitting...' : 'Submit Training'}
                    </Button>
                  </div>
                </form>
              </Card>
            </motion.div>
          ) : (
            <motion.div key="success" initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} className="py-16 text-center">
              <div className="w-24 h-24 bg-emerald-50 text-success rounded-full flex items-center justify-center mx-auto mb-6">
                <CheckCircle2 size={48} />
              </div>
              <h3 className="text-2xl font-black text-neutral-900">Training Submitted!</h3>
              <p className="text-neutral-500 mt-2">Your programme is pending admin approval.</p>
            </motion.div>
          )}
        </AnimatePresence>

      </div>
    </DashboardLayout>
  );
}
