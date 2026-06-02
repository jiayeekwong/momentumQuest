'use client';

import { useState, useEffect } from 'react';
import { DashboardLayout } from '@/src/components/Layout';
import { Card, Badge } from '@/src/components/ui';
import { Users, Briefcase, GraduationCap, Bell, TrendingUp, CheckCircle2, AlertCircle, ChevronRight } from 'lucide-react';
import Link from 'next/link';
import { apiFetch } from '@/src/lib/apiFetch';

interface AdminStats {
  total_users: number;
  total_students: number;
  total_companies: number;
  pending_certificates: number;
  total_scraped_jobs: number;
  total_skills: number;
}

interface Announcement {
  id: number;
  title: string;
  admin_name: string | null;
  publish_time: string;
}

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

export default function AdminDashboardPage() {
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [announcements, setAnnouncements] = useState<Announcement[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    apiFetch('/api/dashboard/admin/')
      .then(r => r.json())
      .then(data => {
        setStats(data.stats ?? null);
        setAnnouncements(data.recent_announcements ?? []);
      })
      .catch(() => {})
      .finally(() => setIsLoading(false));
  }, []);

  const statCards = [
    { label: 'Total Students',   value: stats?.total_students   ?? '—', icon: Users,       color: 'bg-indigo-50 text-primary',  trend: 'Registered students' },
    { label: 'Companies',        value: stats?.total_companies  ?? '—', icon: Briefcase,    color: 'bg-sky-50 text-secondary',   trend: 'Registered companies' },
    { label: 'Scraped Jobs',     value: stats?.total_scraped_jobs ?? '—', icon: TrendingUp, color: 'bg-emerald-50 text-success', trend: 'Jobs in market data' },
    { label: 'Pending Reviews',  value: stats?.pending_certificates ?? '—', icon: AlertCircle, color: 'bg-amber-50 text-warning', trend: 'Certificates pending' },
  ];

  return (
    <DashboardLayout title="Admin Dashboard">
      <div className="max-w-6xl mx-auto space-y-8">
        <div>
          <h2 className="text-2xl font-bold text-neutral-900">Platform Overview</h2>
          <p className="text-neutral-500 mt-1">Monitor platform activity and manage pending approvals.</p>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-5">
          {statCards.map((stat) => (
            <Card key={stat.label} className="p-5 flex items-start gap-4">
              <div className={`w-11 h-11 rounded-xl flex items-center justify-center shrink-0 ${stat.color}`}>
                <stat.icon size={20} />
              </div>
              <div>
                <p className="text-[10px] font-black text-neutral-400 uppercase tracking-widest leading-tight">{stat.label}</p>
                {isLoading ? (
                  <div className="h-7 w-12 bg-neutral-100 animate-pulse rounded mt-1" />
                ) : (
                  <p className="text-2xl font-black text-neutral-900 mt-0.5">{stat.value}</p>
                )}
                <p className="text-[10px] font-semibold text-neutral-400 mt-0.5">{stat.trend}</p>
              </div>
            </Card>
          ))}
        </div>

        {/* Recent announcements */}
        <Card className="p-6">
            <div className="flex items-center justify-between mb-5">
              <h3 className="text-lg font-bold text-neutral-900">Recent Announcements</h3>
              {announcements.length > 0 && (
                <Badge variant="warning" className="text-[9px] font-black">{announcements.length}</Badge>
              )}
            </div>
            {isLoading ? (
              <div className="space-y-3">
                {[1, 2, 3].map(i => (
                  <div key={i} className="h-16 bg-neutral-100 animate-pulse rounded-xl" />
                ))}
              </div>
            ) : announcements.length > 0 ? (
              <div className="space-y-3">
                {announcements.map((item) => (
                  <div key={item.id} className="flex items-start gap-3 p-3 bg-neutral-50 rounded-xl border border-neutral-100">
                    <div className="w-8 h-8 bg-sky-50 text-secondary rounded-lg flex items-center justify-center shrink-0">
                      <Bell size={16} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-[10px] font-black text-neutral-400 uppercase tracking-widest">Announcement</p>
                      <p className="text-xs font-bold text-neutral-900 truncate">{item.title}</p>
                      <p className="text-[10px] text-neutral-400 font-medium mt-0.5">{timeAgo(item.publish_time)}</p>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-8 text-neutral-300">
                <Bell size={32} className="mb-2" />
                <p className="text-xs font-bold text-neutral-400">No announcements yet</p>
              </div>
            )}
        </Card>

        {/* Quick actions */}
        <Card className="p-6">
          <h3 className="text-lg font-bold text-neutral-900 mb-5">Quick Actions</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {[
              { label: 'Review Approvals',  href: '/approvals',         icon: CheckCircle2, color: 'bg-amber-50 text-warning' },
              { label: 'Manage Courses',    href: '/manage-courses',     icon: GraduationCap, color: 'bg-indigo-50 text-primary' },
              { label: 'Endorse Skills',    href: '/endorse',            icon: CheckCircle2, color: 'bg-emerald-50 text-success' },
              { label: 'Post Announcement', href: '/post-announcement',  icon: Bell,         color: 'bg-sky-50 text-secondary' },
            ].map((action) => (
              <Link key={action.label} href={action.href}>
                <div className="p-4 bg-neutral-50 rounded-xl border border-neutral-100 hover:border-primary/30 transition-all cursor-pointer group flex items-center gap-3">
                  <div className={`w-10 h-10 rounded-lg flex items-center justify-center shrink-0 ${action.color}`}>
                    <action.icon size={18} />
                  </div>
                  <span className="text-sm font-bold text-neutral-900 group-hover:text-primary transition-colors">{action.label}</span>
                  <ChevronRight size={14} className="ml-auto text-neutral-400 group-hover:text-primary transition-colors" />
                </div>
              </Link>
            ))}
          </div>
        </Card>
      </div>
    </DashboardLayout>
  );
}
