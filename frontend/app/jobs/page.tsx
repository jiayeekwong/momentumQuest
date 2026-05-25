'use client';

import React, { useState } from 'react';
import { Search, MapPin, DollarSign, Calendar, CheckCircle2, XCircle, Bookmark, Upload, Briefcase, Sparkles } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { DashboardLayout } from '@/src/components/Layout';
import { Card, Badge, Button, Input } from '@/src/components/ui';
import { cn } from '@/src/lib/utils';
import { JobListing } from '@/src/types';

const mockJobs: JobListing[] = [
  { id: '1', title: 'Junior Data Scientist', company: 'Nexus AI', companyLogo: 'https://api.dicebear.com/7.x/initials/svg?seed=NX', category: 'Data Science', salary: 'RM5,000 – RM7,500', closingDate: '20 May 2026', matchScore: 85, description: 'Join our advanced analytics team. Build exploratory models and visualise insights for healthcare clients.', requiredSkills: ['Python', 'SQL', 'Scikit-Learn', 'Tableau', 'NLP'] },
  { id: '2', title: 'Product Analyst', company: 'FinTrack', companyLogo: 'https://api.dicebear.com/7.x/initials/svg?seed=FT', category: 'Analytics', salary: 'RM4,200 – RM6,000', closingDate: '25 May 2026', matchScore: 68, description: 'Translate user behaviour data into actionable product features for a fintech platform.', requiredSkills: ['SQL', 'Excel', 'User Research', 'A/B Testing'] },
  { id: '3', title: 'BI Lead', company: 'Global Retail Co', companyLogo: 'https://api.dicebear.com/7.x/initials/svg?seed=GR', category: 'Management', salary: 'RM8,000 – RM12,000', closingDate: '15 May 2026', matchScore: 42, description: 'Lead BI strategic initiatives across 5 countries. Cloud warehousing and stakeholder management required.', requiredSkills: ['PowerBI', 'Snowflake', 'Dbt', 'Management'] },
];

const mySkills = ['Python', 'SQL', 'Tableau', 'Excel', 'Communication'];

export default function JobListingsPage() {
  const [selectedJob, setSelectedJob] = useState<JobListing | null>(mockJobs[0]);
  const [search, setSearch] = useState('');
  const [showApplyModal, setShowApplyModal] = useState(false);
  const [isSubmitted, setIsSubmitted] = useState(false);

  const filtered = mockJobs.filter(j =>
    j.title.toLowerCase().includes(search.toLowerCase()) ||
    j.company.toLowerCase().includes(search.toLowerCase())
  );

  const handleApply = (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitted(true);
    setTimeout(() => { setShowApplyModal(false); setIsSubmitted(false); }, 2000);
  };

  return (
    <DashboardLayout title="Job Marketplace">
      <div className="flex h-[calc(100vh-160px)] gap-6 relative">
        {/* Left */}
        <div className="w-full lg:w-[450px] flex flex-col gap-4 overflow-hidden">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400" size={18} />
            <input
              type="text"
              placeholder="Search job title or company..."
              className="w-full h-11 pl-10 pr-4 bg-white border border-neutral-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>

          <div className="flex-1 overflow-y-auto pr-1 space-y-3">
            <div className="flex items-center gap-2 px-1">
              <Sparkles size={16} className="text-primary" />
              <p className="text-[10px] font-black text-neutral-400 uppercase tracking-widest">Recommended for you</p>
            </div>
            {filtered.length > 0 ? filtered.map((job) => (
              <Card
                key={job.id}
                className={cn('p-5 cursor-pointer transition-all border-l-4', selectedJob?.id === job.id ? 'border-l-primary bg-indigo-50/30' : 'border-l-transparent')}
                onClick={() => setSelectedJob(job)}
              >
                <div className="flex gap-4">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={job.companyLogo} alt={job.company} className="w-12 h-12 rounded-lg border border-neutral-100" />
                  <div className="flex-1">
                    <div className="flex items-start justify-between">
                      <h4 className="font-bold text-neutral-900 leading-tight">{job.title}</h4>
                      <Badge variant={(job.matchScore ?? 0) > 70 ? 'success' : (job.matchScore ?? 0) > 40 ? 'warning' : 'danger'}>
                        {job.matchScore}%
                      </Badge>
                    </div>
                    <p className="text-sm font-medium text-neutral-600 mt-1">{job.company}</p>
                    <div className="flex items-center justify-between mt-3">
                      <div className="flex items-center gap-3">
                        <span className="flex items-center gap-1 text-[10px] uppercase font-bold text-neutral-400"><MapPin size={10} /> Remote</span>
                        <span className="flex items-center gap-1 text-[10px] uppercase font-bold text-neutral-400"><Calendar size={10} /> {job.closingDate}</span>
                      </div>
                      <Button size="sm" className="h-7 text-[10px] px-3" onClick={(e) => { e.stopPropagation(); setSelectedJob(job); setShowApplyModal(true); }}>Apply</Button>
                    </div>
                  </div>
                </div>
              </Card>
            )) : (
              <div className="p-12 text-center"><Briefcase size={40} className="mx-auto text-neutral-200 mb-2" /><p className="text-sm font-bold text-neutral-500">No jobs found</p></div>
            )}
          </div>
        </div>

        {/* Right detail */}
        <div className="hidden lg:flex flex-1 bg-white border border-neutral-200 rounded-2xl overflow-hidden flex-col">
          {selectedJob ? (
            <>
              <div className="p-8 border-b border-neutral-100 bg-neutral-50/30">
                <div className="flex justify-between items-start mb-6">
                  <div className="flex gap-6">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={selectedJob.companyLogo} alt={selectedJob.company} className="w-20 h-20 rounded-2xl shadow-sm border border-white" />
                    <div>
                      <p className="text-lg font-semibold text-primary">{selectedJob.company}</p>
                      <h2 className="text-3xl font-black text-neutral-900 mb-1">{selectedJob.title}</h2>
                      <Badge variant="secondary">{selectedJob.category}</Badge>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Button variant="outline" className="h-11 px-4"><Bookmark size={20} /></Button>
                    <Button onClick={() => setShowApplyModal(true)} className="h-11 px-10">Apply Now</Button>
                  </div>
                </div>
                <div className="grid grid-cols-3 gap-6 py-4 border-y border-neutral-100">
                  {[
                    { icon: DollarSign, label: 'Monthly Salary', value: selectedJob.salary, color: 'bg-emerald-50 text-success' },
                    { icon: MapPin, label: 'Work Mode', value: 'Hybrid / Remote', color: 'bg-sky-50 text-secondary' },
                    { icon: Briefcase, label: 'Experience', value: 'Entry Level', color: 'bg-indigo-50 text-primary' },
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
                <section>
                  <h4 className="text-lg font-bold text-neutral-900 mb-4 flex items-center gap-2"><div className="w-1 h-6 bg-primary rounded-full" /> Job Description</h4>
                  <p className="text-neutral-600 leading-relaxed">{selectedJob.description}</p>
                </section>
                <section>
                  <h4 className="text-lg font-bold text-neutral-900 mb-4 flex items-center gap-2"><div className="w-1 h-6 bg-primary rounded-full" /> Compatibility Check</h4>
                  <div className="grid grid-cols-2 gap-4">
                    {selectedJob.requiredSkills.map((skill) => {
                      const has = mySkills.includes(skill);
                      return (
                        <div key={skill} className={cn('p-4 rounded-xl border flex items-center justify-between', has ? 'bg-emerald-50 border-emerald-100 text-success' : 'bg-neutral-50 border-neutral-100 text-neutral-400')}>
                          <span className="text-sm font-bold">{skill}</span>
                          {has ? <CheckCircle2 size={18} /> : <XCircle size={18} className="text-neutral-300" />}
                        </div>
                      );
                    })}
                  </div>
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

      {/* Apply Modal */}
      <AnimatePresence>
        {showApplyModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="absolute inset-0 bg-neutral-900/60 backdrop-blur-sm" onClick={() => setShowApplyModal(false)} />
            <motion.div initial={{ opacity: 0, scale: 0.95, y: 20 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.95 }} className="relative w-full max-w-xl bg-white rounded-2xl shadow-2xl overflow-hidden">
              {!isSubmitted ? (
                <>
                  <div className="p-6 border-b border-neutral-100 flex items-center justify-between bg-neutral-50/50">
                    <div>
                      <h3 className="text-xl font-bold text-neutral-900">Apply for Job</h3>
                      <p className="text-xs text-neutral-600">{selectedJob?.title} @ {selectedJob?.company}</p>
                    </div>
                    <button onClick={() => setShowApplyModal(false)} className="p-2 hover:bg-neutral-100 rounded-lg text-neutral-400"><XCircle size={24} /></button>
                  </div>
                  <form onSubmit={handleApply} className="p-8 space-y-6">
                    <div className="border-2 border-dashed border-neutral-200 rounded-xl p-8 text-center hover:border-primary transition-colors cursor-pointer group bg-neutral-50/30">
                      <Upload className="mx-auto text-neutral-300 group-hover:text-primary mb-4" size={32} />
                      <p className="text-sm font-bold text-neutral-900">Drag &amp; Drop CV or Click to Browse</p>
                      <p className="text-xs text-neutral-400 mt-1">PDF, DOCX (Max 5MB)</p>
                    </div>
                    <div>
                      <label className="text-[10px] font-black text-neutral-900 uppercase tracking-widest block mb-2">Cover Note (Optional)</label>
                      <textarea className="w-full h-32 p-4 bg-white border border-neutral-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary/20" placeholder="Why are you the perfect fit?" />
                    </div>
                    <div className="flex gap-4">
                      <Button type="button" variant="outline" fullWidth onClick={() => setShowApplyModal(false)}>Cancel</Button>
                      <Button type="submit" fullWidth>Submit Application</Button>
                    </div>
                  </form>
                </>
              ) : (
                <div className="p-12 text-center space-y-6">
                  <div className="w-20 h-20 bg-emerald-50 text-success rounded-full flex items-center justify-center mx-auto">
                    <CheckCircle2 size={40} />
                  </div>
                  <div>
                    <h3 className="text-2xl font-black text-neutral-900">Application Submitted!</h3>
                    <p className="text-neutral-600 mt-2">Your profile has been sent to {selectedJob?.company}.</p>
                  </div>
                  <Button fullWidth onClick={() => { setShowApplyModal(false); setIsSubmitted(false); }}>Track Application</Button>
                </div>
              )}
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </DashboardLayout>
  );
}
