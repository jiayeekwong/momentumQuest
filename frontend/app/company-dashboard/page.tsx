'use client';

import { useAuth } from '@/src/context/AuthContext';
import { DashboardLayout } from '@/src/components/Layout';
import { Card, Badge, Button } from '@/src/components/ui';
import { Briefcase, Users, Eye, TrendingUp, ChevronRight, Plus, Clock, CheckCircle2 } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';
import Link from 'next/link';

const applicantData = [
  { day: 'Mon', count: 4 }, { day: 'Tue', count: 7 }, { day: 'Wed', count: 5 },
  { day: 'Thu', count: 9 }, { day: 'Fri', count: 12 }, { day: 'Sat', count: 3 }, { day: 'Sun', count: 2 },
];

const recentApplicants = [
  { name: 'Aisha Rahman', role: 'Data Scientist', date: 'May 20, 2026', status: 'shortlisted' },
  { name: 'Tan Wei Liang', role: 'Data Scientist', date: 'May 19, 2026', status: 'pending' },
  { name: 'Priya Nair', role: 'Product Analyst', date: 'May 18, 2026', status: 'shortlisted' },
  { name: 'Marcus Lee', role: 'Data Scientist', date: 'May 17, 2026', status: 'rejected' },
];

const statusVariants: Record<string, 'neutral' | 'primary' | 'warning' | 'danger' | 'success'> = {
  pending: 'neutral', shortlisted: 'primary', rejected: 'danger', accepted: 'success',
};

const activeListings = [
  { title: 'Data Scientist', applicants: 12, views: 340, closing: 'May 30, 2026' },
  { title: 'Product Analyst', applicants: 7, views: 180, closing: 'Jun 5, 2026' },
];

export default function CompanyDashboardPage() {
  const { user } = useAuth();
  const companyName = user?.name ?? 'Your Company';

  return (
    <DashboardLayout title="Company Dashboard">
      <div className="max-w-6xl mx-auto space-y-8">
        {/* Header */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h2 className="text-2xl font-bold text-neutral-900">Welcome back, {companyName}</h2>
            <p className="text-neutral-500 mt-1">Here&apos;s an overview of your recruitment activity.</p>
          </div>
          <Link href="/post-job">
            <Button className="h-11 px-6"><Plus size={16} className="mr-2" /> Post a Job</Button>
          </Link>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-1 sm:grid-cols-4 gap-5">
          {[
            { label: 'Active Listings', value: '2', icon: Briefcase, color: 'bg-indigo-50 text-primary' },
            { label: 'Total Applicants', value: '19', icon: Users, color: 'bg-sky-50 text-secondary' },
            { label: 'Shortlisted', value: '6', icon: CheckCircle2, color: 'bg-emerald-50 text-success' },
            { label: 'Profile Views', value: '520', icon: Eye, color: 'bg-amber-50 text-warning' },
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
          {/* Applicant trend */}
          <Card className="lg:col-span-3 p-6">
            <div className="flex items-center justify-between mb-6">
              <div>
                <h3 className="text-lg font-bold text-neutral-900">Applicant Activity</h3>
                <p className="text-xs text-neutral-400 font-medium mt-0.5">New applicants this week</p>
              </div>
              <Badge variant="primary" className="text-[10px] font-black tracking-widest">
                <TrendingUp size={12} className="mr-1" /> +42% WoW
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

          {/* Active listings */}
          <Card className="lg:col-span-2 p-6">
            <div className="flex items-center justify-between mb-5">
              <h3 className="text-lg font-bold text-neutral-900">Active Listings</h3>
              <Link href="/manage-listings">
                <Button variant="ghost" size="sm" className="text-primary text-xs font-bold">
                  Manage <ChevronRight size={14} />
                </Button>
              </Link>
            </div>
            <div className="space-y-4">
              {activeListings.map((listing) => (
                <div key={listing.title} className="p-4 bg-neutral-50 rounded-xl border border-neutral-100">
                  <h4 className="font-bold text-neutral-900 text-sm">{listing.title}</h4>
                  <div className="flex items-center gap-4 mt-2 text-xs font-semibold text-neutral-500">
                    <span className="flex items-center gap-1"><Users size={11} /> {listing.applicants} applicants</span>
                    <span className="flex items-center gap-1"><Eye size={11} /> {listing.views} views</span>
                  </div>
                  <div className="flex items-center gap-1 mt-2 text-xs font-medium text-neutral-400">
                    <Clock size={11} /> Closes {listing.closing}
                  </div>
                </div>
              ))}
            </div>
          </Card>
        </div>

        {/* Recent applicants */}
        <Card className="p-6">
          <div className="flex items-center justify-between mb-5">
            <h3 className="text-lg font-bold text-neutral-900">Recent Applicants</h3>
            <Link href="/review-applications">
              <Button variant="ghost" size="sm" className="text-primary text-xs font-bold">
                Review All <ChevronRight size={14} className="ml-1" />
              </Button>
            </Link>
          </div>
          <div className="divide-y divide-neutral-100">
            {recentApplicants.map((app) => (
              <div key={app.name} className="py-4 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-full bg-gradient-to-br from-primary to-secondary flex items-center justify-center text-white text-sm font-black">
                    {app.name[0]}
                  </div>
                  <div>
                    <p className="text-sm font-bold text-neutral-900">{app.name}</p>
                    <p className="text-xs text-neutral-500 font-medium">{app.role} · {app.date}</p>
                  </div>
                </div>
                <Badge variant={statusVariants[app.status]} className="capitalize px-3 text-[10px] tracking-widest font-black">{app.status}</Badge>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </DashboardLayout>
  );
}
