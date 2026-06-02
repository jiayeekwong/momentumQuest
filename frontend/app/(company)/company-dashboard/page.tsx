'use client';

import { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { apiFetch } from '@/src/lib/apiFetch';
import { DashboardLayout } from '@/src/components/Layout';
import { Card, Badge, Button } from '@/src/components/ui';
import { Briefcase, Users, CheckCircle2, ChevronRight, Plus, Clock, Bell, X, FileText, ExternalLink } from 'lucide-react';
import Link from 'next/link';

const statusVariants: Record<string, 'neutral' | 'primary' | 'warning' | 'danger' | 'success'> = {
  PENDING: 'neutral', SHORTLISTED: 'primary', REJECTED: 'danger', ACCEPTED: 'success',
};

interface DashboardStats {
  company_name: string;
  active_listings: number;
  total_applications: number;
  shortlisted: number;
}

interface RecentApp {
  id: number;
  student_name: string;
  job_title: string;
  applied_time: string;
  status: string;
}

interface Announcement {
  id: number;
  title: string;
  message: string;
  categories: string[];
  supporting_doc: string | null;
  publish_time: string;
}

function isImageUrl(url: string): boolean {
  return /\.(jpg|jpeg|png|gif|webp|svg)(\?|$)/i.test(url);
}

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

// ─── Announcement Detail Modal ────────────────────────────────────────────

function AnnouncementModal({ a, onClose }: { a: Announcement; onClose: () => void }) {
  return (
    <motion.div key="detail-backdrop"
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm px-4 py-8 overflow-y-auto"
      onClick={onClose}>
      <motion.div
        initial={{ scale: 0.96, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.96, opacity: 0 }}
        transition={{ type: 'spring', stiffness: 300, damping: 30 }}
        className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl my-auto"
        onClick={e => e.stopPropagation()}>

        <div className="flex items-start justify-between gap-4 p-7 border-b border-neutral-100">
          <div className="flex-1 min-w-0">
            <div className="flex flex-wrap items-center gap-2 mb-3">
              {a.categories?.map(cat => (
                <Badge key={cat} variant="primary" className="text-[9px] font-black tracking-widest">{cat}</Badge>
              ))}
            </div>
            <h2 className="text-xl font-black text-neutral-900 leading-tight">{a.title}</h2>
            <p className="text-[11px] text-neutral-400 font-medium mt-2">Published {timeAgo(a.publish_time)}</p>
          </div>
          <button onClick={onClose} className="w-8 h-8 shrink-0 flex items-center justify-center rounded-lg hover:bg-neutral-100 text-neutral-400">
            <X size={18} />
          </button>
        </div>

        <div className="p-7 space-y-5">
          <div className="text-sm text-neutral-700 leading-relaxed announcement-body"
            dangerouslySetInnerHTML={{ __html: a.message }} />

          {a.supporting_doc && (
            <div className="border border-neutral-200 rounded-xl overflow-hidden">
              {isImageUrl(a.supporting_doc) ? (
                <img src={a.supporting_doc} alt="Attachment" className="w-full max-h-80 object-contain bg-neutral-50" />
              ) : (
                <a href={a.supporting_doc} target="_blank" rel="noopener noreferrer"
                  className="flex items-center gap-3 p-4 hover:bg-neutral-50 transition-colors">
                  <div className="w-10 h-10 bg-indigo-50 rounded-lg flex items-center justify-center text-primary shrink-0">
                    <FileText size={20} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-bold text-neutral-900">Attached Document</p>
                    <p className="text-xs text-neutral-400 truncate">{a.supporting_doc}</p>
                  </div>
                  <ExternalLink size={15} className="text-neutral-400 shrink-0" />
                </a>
              )}
            </div>
          )}
        </div>

        <div className="px-7 pb-7">
          <Button variant="outline" fullWidth onClick={onClose}>Close</Button>
        </div>
      </motion.div>
    </motion.div>
  );
}

export default function CompanyDashboardPage() {
  const [stats,              setStats]              = useState<DashboardStats | null>(null);
  const [recentApps,         setRecentApps]         = useState<RecentApp[]>([]);
  const [announcements,      setAnnouncements]      = useState<Announcement[]>([]);
  const [selectedAnnouncement, setSelectedAnnouncement] = useState<Announcement | null>(null);

  useEffect(() => {
    apiFetch('/api/dashboard/company/')
      .then(r => r.json())
      .then(setStats)
      .catch(() => {});

    apiFetch('/api/job-listings/company/applications/')
      .then(r => r.json())
      .then((data: RecentApp[]) => setRecentApps(Array.isArray(data) ? data.slice(0, 5) : []))
      .catch(() => {});

    apiFetch('/api/dashboard/announcements/')
      .then(r => r.json())
      .then((data: Announcement[]) => setAnnouncements(Array.isArray(data) ? data.slice(0, 4) : []))
      .catch(() => {});
  }, []);

  const companyName = stats?.company_name ?? 'Your Company';

  return (
    <DashboardLayout title="Company Dashboard">
      <div className="max-w-6xl mx-auto space-y-8">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h2 className="text-2xl font-bold text-neutral-900">Welcome back, {companyName}</h2>
            <p className="text-neutral-500 mt-1">Here&apos;s an overview of your recruitment activity.</p>
          </div>
          <Link href="/post-job">
            <Button className="h-11 px-6"><Plus size={16} className="mr-2" /> Post a Job</Button>
          </Link>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-5">
          {[
            { label: 'Active Listings',  value: stats?.active_listings    ?? '—', icon: Briefcase,    color: 'bg-indigo-50 text-primary' },
            { label: 'Total Applicants', value: stats?.total_applications ?? '—', icon: Users,        color: 'bg-sky-50 text-secondary' },
            { label: 'Shortlisted',      value: stats?.shortlisted        ?? '—', icon: CheckCircle2, color: 'bg-emerald-50 text-success' },
          ].map((stat) => (
            <Card key={stat.label} className="p-5 flex items-center gap-3 overflow-hidden">
              <div className={`w-11 h-11 rounded-xl flex items-center justify-center shrink-0 ${stat.color}`}>
                <stat.icon size={20} />
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-[10px] font-black text-neutral-400 uppercase tracking-wide leading-tight break-words">{stat.label}</p>
                <p className="text-2xl font-black text-neutral-900 mt-0.5 truncate">{stat.value}</p>
              </div>
            </Card>
          ))}
        </div>

        <Card className="p-6 flex flex-col">
          <div className="flex items-center justify-between mb-5">
            <h3 className="text-lg font-bold text-neutral-900">Active Listings</h3>
            <Link href="/manage-listings">
              <Button variant="ghost" size="sm" className="text-primary text-xs font-bold">
                Manage <ChevronRight size={14} />
              </Button>
            </Link>
          </div>
          <div className="flex-1 flex flex-col items-center justify-center text-center py-4">
            <p className="text-5xl font-black text-primary">{stats?.active_listings ?? '—'}</p>
            <p className="text-sm font-medium text-neutral-500 mt-2">active job listings</p>
            <Link href="/post-job" className="mt-4">
              <Button variant="outline" size="sm" className="h-9 text-xs">
                <Plus size={14} className="mr-1.5" /> Post New Job
              </Button>
            </Link>
          </div>
        </Card>

        <Card className="p-6">
          <div className="flex items-center justify-between mb-5">
            <h3 className="text-lg font-bold text-neutral-900">Recent Applicants</h3>
            <Link href="/review-applications">
              <Button variant="ghost" size="sm" className="text-primary text-xs font-bold">
                Review All <ChevronRight size={14} className="ml-1" />
              </Button>
            </Link>
          </div>
          {recentApps.length > 0 ? (
            <div className="divide-y divide-neutral-100">
              {recentApps.map((app) => (
                <div key={app.id} className="py-4 flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-9 h-9 rounded-full bg-gradient-to-br from-primary to-secondary flex items-center justify-center text-white text-sm font-black">
                      {app.student_name[0]}
                    </div>
                    <div>
                      <p className="text-sm font-bold text-neutral-900">{app.student_name}</p>
                      <p className="text-xs text-neutral-500 font-medium">
                        {app.job_title} · {new Date(app.applied_time).toLocaleDateString('en-MY', { day: 'numeric', month: 'short', year: 'numeric' })}
                      </p>
                    </div>
                  </div>
                  <Badge variant={statusVariants[app.status] ?? 'neutral'} className="capitalize px-3 text-[10px] tracking-widest font-black">
                    {app.status.toLowerCase()}
                  </Badge>
                </div>
              ))}
            </div>
          ) : (
            <div className="py-12 text-center">
              <Clock size={32} className="mx-auto text-neutral-200 mb-2" />
              <p className="text-sm font-bold text-neutral-500">No applications yet</p>
              <p className="text-xs text-neutral-400 mt-1">Applications will appear here once students apply</p>
            </div>
          )}
        </Card>

        {/* Announcements */}
        <Card className="p-6">
          <div className="flex items-center gap-2 mb-5">
            <Bell size={18} className="text-primary" />
            <h3 className="text-lg font-bold text-neutral-900">Platform Announcements</h3>
          </div>
          {announcements.length > 0 ? (
            <div className="space-y-4">
              {announcements.map((a) => (
                <div key={a.id} className="pb-4 border-b border-neutral-100 last:border-none last:pb-0">
                  <div className="flex items-start justify-between gap-2 mb-1">
                    <button type="button" onClick={() => setSelectedAnnouncement(a)}
                      className="text-left text-sm font-bold text-neutral-900 hover:text-primary hover:underline underline-offset-2 transition-colors">
                      {a.title}
                    </button>
                    {a.categories?.length > 0 && (
                      <Badge variant="primary" className="text-[9px] shrink-0">{a.categories[0]}</Badge>
                    )}
                  </div>
                  <div
                    className="text-xs text-neutral-500 leading-relaxed announcement-body"
                    dangerouslySetInnerHTML={{ __html: a.message }}
                  />
                  <p className="text-[10px] text-neutral-400 font-medium mt-1.5">{timeAgo(a.publish_time)}</p>
                </div>
              ))}
            </div>
          ) : (
            <div className="py-8 text-center">
              <Bell size={28} className="mx-auto text-neutral-200 mb-2" />
              <p className="text-sm font-bold text-neutral-500">No announcements</p>
            </div>
          )}
        </Card>
      </div>

      {/* Announcement detail modal */}
      <AnimatePresence>
        {selectedAnnouncement && (
          <AnnouncementModal a={selectedAnnouncement} onClose={() => setSelectedAnnouncement(null)} />
        )}
      </AnimatePresence>
    </DashboardLayout>
  );
}
