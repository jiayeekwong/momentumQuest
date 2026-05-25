'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Bell, Users, Briefcase, GraduationCap, CheckCircle2 } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { DashboardLayout } from '@/src/components/Layout';
import { Card, Button, Input } from '@/src/components/ui';
import { cn } from '@/src/lib/utils';

const audiences = [
  { id: 'all', label: 'Everyone', icon: Users, desc: 'All students and companies' },
  { id: 'students', label: 'Students Only', icon: GraduationCap, desc: 'Only student accounts' },
  { id: 'companies', label: 'Companies Only', icon: Briefcase, desc: 'Only company accounts' },
];

const categories = ['Career Event', 'Job Opportunity', 'Training', 'Platform Update', 'General'];

export default function PostAnnouncementPage() {
  const router = useRouter();
  const [submitted, setSubmitted] = useState(false);

  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const [category, setCategory] = useState('');
  const [audience, setAudience] = useState('all');
  const [pinned, setPinned] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitted(true);
    setTimeout(() => router.push('/admin-dashboard'), 2500);
  };

  return (
    <DashboardLayout title="Post Announcement">
      <div className="max-w-3xl mx-auto">
        <AnimatePresence mode="wait">
          {!submitted ? (
            <motion.div key="form" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
              <div className="mb-8">
                <h2 className="text-2xl font-bold text-neutral-900">Create Announcement</h2>
                <p className="text-neutral-500 mt-1">Broadcast important updates to platform users.</p>
              </div>

              <Card className="p-8">
                <form onSubmit={handleSubmit} className="space-y-6">
                  <Input label="Announcement Title" placeholder="e.g. Career Fair 2026 — June Edition" value={title} onChange={(e) => setTitle(e.target.value)} required />

                  <div className="space-y-2">
                    <label className="text-[10px] font-black text-neutral-900 uppercase tracking-widest block">Category</label>
                    <div className="flex flex-wrap gap-2">
                      {categories.map((cat) => (
                        <button key={cat} type="button" onClick={() => setCategory(cat)}
                          className={cn('px-4 py-2 rounded-full text-xs font-bold border transition-all', category === cat ? 'bg-primary text-white border-primary' : 'bg-white text-neutral-600 border-neutral-200 hover:border-primary/40')}>
                          {cat}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="space-y-2">
                    <label className="text-[10px] font-black text-neutral-900 uppercase tracking-widest block">Target Audience</label>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                      {audiences.map((a) => (
                        <div key={a.id} onClick={() => setAudience(a.id)}
                          className={cn('p-4 border-2 rounded-xl cursor-pointer transition-all flex flex-col gap-2', audience === a.id ? 'border-primary bg-indigo-50/50' : 'border-neutral-100 hover:border-neutral-200')}>
                          <a.icon className={audience === a.id ? 'text-primary' : 'text-neutral-400'} size={20} />
                          <span className={cn('text-sm font-bold', audience === a.id ? 'text-primary' : 'text-neutral-900')}>{a.label}</span>
                          <span className="text-[10px] text-neutral-400 font-medium">{a.desc}</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="space-y-2">
                    <label className="text-[10px] font-black text-neutral-900 uppercase tracking-widest block">Announcement Body</label>
                    <textarea required value={body} onChange={(e) => setBody(e.target.value)}
                      className="w-full h-40 p-4 bg-white border border-neutral-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 resize-none"
                      placeholder="Write the full announcement content here..." />
                  </div>

                  <div className="flex items-center gap-3 p-4 bg-neutral-50 rounded-xl border border-neutral-100">
                    <input type="checkbox" id="pinned" checked={pinned} onChange={(e) => setPinned(e.target.checked)}
                      className="w-4 h-4 accent-indigo-600" />
                    <label htmlFor="pinned" className="text-sm font-bold text-neutral-900 cursor-pointer">
                      Pin this announcement
                      <span className="text-xs font-medium text-neutral-400 ml-2">— Shows at the top of users&apos; dashboards</span>
                    </label>
                  </div>

                  <div className="flex gap-4 pt-2">
                    <Button type="button" variant="outline" fullWidth onClick={() => router.back()}>Cancel</Button>
                    <Button type="submit" fullWidth>
                      <Bell size={16} className="mr-2" /> Publish Announcement
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
              <h3 className="text-2xl font-black text-neutral-900">Announcement Published!</h3>
              <p className="text-neutral-500 mt-2">Your announcement has been sent to {audience === 'all' ? 'all users' : audience}. Redirecting...</p>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </DashboardLayout>
  );
}
