'use client';

import { useEffect, useState } from 'react';
import { apiFetch } from '@/src/lib/apiFetch';
import { DashboardLayout } from '@/src/components/Layout';
import { Card, Badge, Button } from '@/src/components/ui';
import { Briefcase, Users, CheckCircle2, TrendingUp, ChevronRight, Plus, Clock } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';
import Link from 'next/link';

const applicantData = [
  { day: 'Mon', count: 4 }, { day: 'Tue', count: 7 }, { day: 'Wed', count: 5 },
  { day: 'Thu', count: 9 }, { day: 'Fri', count: 12 }, { day: 'Sat', count: 3 }, { day: 'Sun', count: 2 },
];

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

export default function CompanyDashboardPage() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [recentApps, setRecentApps] = useState<RecentApp[]>([]);

  useEffect(() => {
    apiFetch('/api/dashboard/company/')
      .then(r => r.json())
      .then(setStats)
      .catch(() => {});

    apiFetch('/api/job-listings/applications/')
      .then(r => r.json())
      .then((data: RecentApp[]) => setRecentApps(Array.isArray(data) ? data.slice(0, 5) : []))
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
            { label: 'Active Listings',    value: stats?.active_listings    ?? '—', icon: Briefcase,    color: 'bg-indigo-50 text-primary' },
            { label: 'Total Applicants',   value: stats?.total_applications ?? '—', icon: Users,        color: 'bg-sky-50 text-secondary' },
            { label: 'Shortlisted',        value: stats?.shortlisted        ?? '—', icon: CheckCircle2, color: 'bg-emerald-50 text-success' },
          ].map((stat) => (
            <Card key={stat.label} className="p-5 flex items-center gap-4">
              <div className={`w-11 h-11 rounded-xl flex items-center justify-center shrink-0 ${stat.color}`}>
                <stat.icon size={20} />
              </div>
              <div>
                <p className="text-[10px] font-black text-neutral-400 uppercase tracking-widest">{stat.label}</p>
                <p className="text-2xl font-black text-neutral-900 mt-0.5">{stat.value}</p>
              </div>
            </Card>
          ))}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
          <Card className="lg:col-span-3 p-6">
            <div className="flex items-center justify-between mb-6">
              <div>
                <h3 className="text-lg font-bold text-neutral-900">Applicant Activity</h3>
                <p className="text-xs text-neutral-400 font-medium mt-0.5">New applicants this week</p>
              </div>
              <Badge variant="primary" className="text-[10px] font-black tracking-widest">
                <TrendingUp size={12} className="mr-1" /> This Week
              </Badge>
            </div>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={applicantData} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" vertical={false} />
                <XAxis dataKey="day" tick={{ fontSize: 11, fontWeight: 600, fill: '#9ca3af' }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 11, fontWeight: 600, fill: '#9ca3af' }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={{ borderRadius: 12, border: 'none', boxShadow: '0 4px 20px rgba(0,0,0,0.1)', fontSize: 12 }} />
                <Bar dataKey="count" fill="#4f46e5" radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </Card>

          <Card className="lg:col-span-2 p-6 flex flex-col">
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
        </div>

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
      </div>
    </DashboardLayout>
  );
}
