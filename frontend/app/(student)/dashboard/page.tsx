'use client';

import { useAuth } from '@/src/context/AuthContext';
import { DashboardLayout } from '@/src/components/Layout';
import { Card, Badge, Button } from '@/src/components/ui';
import { Briefcase, Target, Star, Bell, ChevronRight, Sparkles, ArrowUpRight, X, FileText, ExternalLink, Paperclip } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';
import { motion, AnimatePresence } from 'motion/react';
import Link from 'next/link';
import { useEffect, useState } from 'react';

const trendData = [
  { month: 'Jan', demand: 62 }, { month: 'Feb', demand: 68 }, { month: 'Mar', demand: 71 },
  { month: 'Apr', demand: 75 }, { month: 'May', demand: 80 }, { month: 'Jun', demand: 85 },
];


const recentApplications = [
  { id: '1', title: 'Data Scientist', company: 'Nexus AI', status: 'shortlisted' },
  { id: '2', title: 'Product Analyst', company: 'FinTrack', status: 'shortlisted' },
  { id: '3', title: 'Junior Data Analyst', company: 'HealthTech', status: 'pending' },
];

const statusVariants: Record<string, 'neutral' | 'primary' | 'warning' | 'danger' | 'success'> = {
  pending: 'neutral', shortlisted: 'primary', interview: 'warning', rejected: 'danger', accepted: 'success',
};

interface Announcement {
  id: number;
  title: string;
  message: string;
  categories: string[];
  supporting_doc: string | null;
  publish_time: string;
}

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function AnnouncementDetailModal({ a, onClose }: { a: Announcement; onClose: () => void }) {
  const isImage = (url: string) => /\.(jpg|jpeg|png|gif|webp)(\?|$)/i.test(url);

  return (
    <motion.div
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm px-4 py-8 overflow-y-auto"
      onClick={onClose}>
      <motion.div
        initial={{ scale: 0.96, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.96, opacity: 0 }}
        transition={{ type: 'spring', stiffness: 300, damping: 30 }}
        className="bg-white rounded-2xl shadow-2xl w-full max-w-xl my-auto"
        onClick={e => e.stopPropagation()}>

        {/* Header */}
        <div className="flex items-start justify-between gap-4 p-6 border-b border-neutral-100">
          <div className="flex-1 min-w-0">
            {a.categories?.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mb-2">
                {a.categories.map(cat => (
                  <Badge key={cat} variant="primary" className="text-[9px] font-black tracking-widest">{cat}</Badge>
                ))}
              </div>
            )}
            <h2 className="text-lg font-black text-neutral-900 leading-tight">{a.title}</h2>
            <p className="text-[10px] text-neutral-400 font-medium mt-1">{timeAgo(a.publish_time)}</p>
          </div>
          <button onClick={onClose}
            className="w-8 h-8 shrink-0 flex items-center justify-center rounded-lg hover:bg-neutral-100 text-neutral-400">
            <X size={17} />
          </button>
        </div>

        {/* Body */}
        <div className="p-6 space-y-4">
          <div
            className="text-sm text-neutral-700 leading-relaxed announcement-body"
            dangerouslySetInnerHTML={{ __html: a.message }}
          />

          {/* Attachment */}
          {a.supporting_doc && (
            <div className="border border-neutral-200 rounded-xl overflow-hidden mt-2">
              {isImage(a.supporting_doc) ? (
                <img src={a.supporting_doc} alt="Attachment" className="w-full max-h-72 object-contain bg-neutral-50" />
              ) : (
                <a href={a.supporting_doc} target="_blank" rel="noopener noreferrer"
                  className="flex items-center gap-3 p-4 hover:bg-neutral-50 transition-colors">
                  <div className="w-10 h-10 bg-indigo-50 rounded-lg flex items-center justify-center text-primary shrink-0">
                    <FileText size={20} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-bold text-neutral-900">Attached Document</p>
                    <p className="text-xs text-neutral-400">Click to open</p>
                  </div>
                  <ExternalLink size={14} className="text-neutral-400 shrink-0" />
                </a>
              )}
            </div>
          )}
        </div>

        <div className="px-6 pb-6">
          <Button variant="outline" fullWidth onClick={onClose}>Close</Button>
        </div>
      </motion.div>
    </motion.div>
  );
}

export default function DashboardPage() {
  const { user } = useAuth();
  const firstName = user?.name?.split(' ')[0] ?? 'there';
  const [skillsCount,          setSkillsCount]          = useState<number | null>(null);
  const [announcements,        setAnnouncements]        = useState<Announcement[]>([]);
  const [selectedAnnouncement, setSelectedAnnouncement] = useState<Announcement | null>(null);

  useEffect(() => {
    const token = localStorage.getItem('accessToken');
    if (!token) return;
    fetch('http://localhost:8000/api/dashboard/student/', {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => r.json())
      .then((data) => {
        setSkillsCount(data.skills_count ?? 0);
        setAnnouncements(data.announcements ?? []);
      })
      .catch(() => {});
  }, []);

  return (
    <DashboardLayout title="Dashboard">
      <div className="max-w-6xl mx-auto space-y-8">
        {/* Hero greeting */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h2 className="text-2xl font-bold text-neutral-900">Good morning, {firstName} 👋</h2>
            <p className="text-neutral-500 mt-1">Here&apos;s what&apos;s happening with your career today.</p>
          </div>
          <Link href="/jobs">
            <Button className="h-11 px-6">
              <Sparkles size={16} className="mr-2" /> Browse Jobs
            </Button>
          </Link>
        </div>

        {/* Stat cards */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-5">
          {[
            { label: 'Applications Sent', value: '3', icon: Briefcase, color: 'bg-indigo-50 text-primary', trend: '+1 this week' },
            { label: 'Skill Match Score', value: '72%', icon: Target, color: 'bg-emerald-50 text-success', trend: '+5% vs last month' },
            { label: 'Skills in Profile', value: skillsCount !== null ? String(skillsCount) : '—', icon: Star, color: 'bg-amber-50 text-warning', trend: 'from your profile' },
          ].map((stat) => (
            <Card key={stat.label} className="p-6 flex items-start gap-5">
              <div className={`w-12 h-12 rounded-xl flex items-center justify-center shrink-0 ${stat.color}`}>
                <stat.icon size={22} />
              </div>
              <div>
                <p className="text-[10px] font-black text-neutral-400 uppercase tracking-widest">{stat.label}</p>
                <p className="text-3xl font-black text-neutral-900 mt-1">{stat.value}</p>
                <p className="text-xs font-medium text-success mt-1 flex items-center gap-1">
                  <ArrowUpRight size={12} />{stat.trend}
                </p>
              </div>
            </Card>
          ))}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
          {/* Job demand trend */}
          <Card className="lg:col-span-3 p-6">
            <div className="flex items-center justify-between mb-6">
              <div>
                <h3 className="text-lg font-bold text-neutral-900">Data Analyst Demand Trend</h3>
                <p className="text-xs text-neutral-400 font-medium mt-0.5">Industry demand index (last 6 months)</p>
              </div>
              <Badge variant="success" className="text-[10px] font-black tracking-widest">TRENDING UP</Badge>
            </div>
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={trendData} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="month" tick={{ fontSize: 11, fontWeight: 600, fill: '#9ca3af' }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 11, fontWeight: 600, fill: '#9ca3af' }} axisLine={false} tickLine={false} domain={[50, 100]} />
                <Tooltip contentStyle={{ borderRadius: 12, border: 'none', boxShadow: '0 4px 20px rgba(0,0,0,0.1)', fontSize: 12 }} />
                <Line type="monotone" dataKey="demand" stroke="#4f46e5" strokeWidth={3} dot={{ fill: '#4f46e5', strokeWidth: 0, r: 5 }} activeDot={{ r: 7 }} />
              </LineChart>
            </ResponsiveContainer>
          </Card>

          {/* Announcements */}
          <Card className="lg:col-span-2 p-6 flex flex-col">
            <div className="flex items-center justify-between mb-5">
              <h3 className="text-lg font-bold text-neutral-900 flex items-center gap-2">
                <Bell size={18} className="text-primary" /> Announcements
              </h3>
            </div>
            <div className="space-y-1 flex-1 overflow-y-auto">
              {announcements.length > 0 ? announcements.map((a) => (
                <button key={a.id} type="button" onClick={() => setSelectedAnnouncement(a)}
                  className="w-full flex items-center justify-between gap-3 px-3 py-3 rounded-xl hover:bg-neutral-50 transition-colors text-left group">
                  <div className="flex items-center gap-2.5 min-w-0">
                    <div className="w-2 h-2 rounded-full bg-primary shrink-0" />
                    <p className="text-sm font-semibold text-neutral-900 truncate group-hover:text-primary transition-colors">
                      {a.title}
                    </p>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    {a.categories?.length > 0 && (
                      <Badge variant="primary" className="text-[9px] hidden sm:inline-flex">{a.categories[0]}</Badge>
                    )}
                    {a.supporting_doc && <Paperclip size={11} className="text-neutral-400" />}
                    <span className="text-[10px] text-neutral-400 font-medium whitespace-nowrap">{timeAgo(a.publish_time)}</span>
                  </div>
                </button>
              )) : (
                <div className="flex flex-col items-center justify-center py-8 text-neutral-300">
                  <Bell size={28} className="mb-2" />
                  <p className="text-xs font-bold text-neutral-400">No announcements</p>
                </div>
              )}
            </div>
          </Card>
        </div>

        {/* Recent applications */}
        <Card className="p-6">
          <div className="flex items-center justify-between mb-5">
            <h3 className="text-lg font-bold text-neutral-900">Recent Applications</h3>
            <Link href="/applications">
              <Button variant="ghost" size="sm" className="text-primary text-xs font-bold">
                View All <ChevronRight size={14} className="ml-1" />
              </Button>
            </Link>
          </div>
          <div className="divide-y divide-neutral-100">
            {recentApplications.map((app) => (
              <div key={app.id} className="py-4 flex items-center justify-between">
                <div>
                  <p className="text-sm font-bold text-neutral-900">{app.title}</p>
                  <p className="text-xs font-medium text-neutral-500">{app.company}</p>
                </div>
                <Badge variant={statusVariants[app.status]} className="capitalize px-3 py-1 text-[10px] tracking-widest font-black">{app.status}</Badge>
              </div>
            ))}
          </div>
        </Card>
      </div>

      {/* Announcement detail modal */}
      <AnimatePresence>
        {selectedAnnouncement && (
          <AnnouncementDetailModal
            a={selectedAnnouncement}
            onClose={() => setSelectedAnnouncement(null)}
          />
        )}
      </AnimatePresence>
    </DashboardLayout>
  );
}
