'use client';

import { useAuth } from '@/src/context/AuthContext';
import { DashboardLayout } from '@/src/components/Layout';
import { Card, Badge, Button } from '@/src/components/ui';
import { Briefcase, Target, TrendingUp, Bell, ChevronRight, Sparkles, ArrowUpRight } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';
import Link from 'next/link';

const trendData = [
  { month: 'Jan', demand: 62 }, { month: 'Feb', demand: 68 }, { month: 'Mar', demand: 71 },
  { month: 'Apr', demand: 75 }, { month: 'May', demand: 80 }, { month: 'Jun', demand: 85 },
];

const announcements = [
  { id: 1, title: 'New Data Science Internships', body: 'Nexus AI just posted 3 new openings for fresh graduates.', tag: 'Jobs', tagVariant: 'primary' as const, time: '2h ago' },
  { id: 2, title: 'Resume Workshop This Friday', body: 'Career Services is hosting a live CV review session at 2PM.', tag: 'Event', tagVariant: 'warning' as const, time: '1d ago' },
  { id: 3, title: 'NLP Certification — 30% Off', body: 'Coursera is offering a limited discount on the NLP Specialization.', tag: 'Training', tagVariant: 'success' as const, time: '3d ago' },
];

const recentApplications = [
  { id: '1', title: 'Data Scientist', company: 'Nexus AI', status: 'shortlisted' },
  { id: '2', title: 'Product Analyst', company: 'FinTrack', status: 'shortlisted' },
  { id: '3', title: 'Junior Data Analyst', company: 'HealthTech', status: 'pending' },
];

const statusVariants: Record<string, 'neutral' | 'primary' | 'warning' | 'danger' | 'success'> = {
  pending: 'neutral', shortlisted: 'primary', interview: 'warning', rejected: 'danger', accepted: 'success',
};

export default function DashboardPage() {
  const { user } = useAuth();
  const firstName = user?.name?.split(' ')[0] ?? 'there';

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
            { label: 'Profile Views', value: '24', icon: TrendingUp, color: 'bg-amber-50 text-warning', trend: '+8 this week' },
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
            <div className="space-y-4 flex-1 overflow-y-auto">
              {announcements.map((a) => (
                <div key={a.id} className="flex gap-3 pb-4 border-b border-neutral-100 last:border-none last:pb-0">
                  <div className="flex-1">
                    <div className="flex items-start justify-between gap-2">
                      <p className="text-sm font-bold text-neutral-900 leading-tight">{a.title}</p>
                      <Badge variant={a.tagVariant} className="text-[9px] shrink-0">{a.tag}</Badge>
                    </div>
                    <p className="text-xs text-neutral-500 mt-1 leading-relaxed">{a.body}</p>
                    <p className="text-[10px] text-neutral-400 font-medium mt-1.5">{a.time}</p>
                  </div>
                </div>
              ))}
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
    </DashboardLayout>
  );
}
