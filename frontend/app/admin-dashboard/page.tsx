'use client';

import { DashboardLayout } from '@/src/components/Layout';
import { Card, Badge } from '@/src/components/ui';
import { Users, Briefcase, GraduationCap, Bell, TrendingUp, CheckCircle2, Clock, AlertCircle, ChevronRight } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';
import Link from 'next/link';

const registrationData = [
  { month: 'Jan', students: 42, companies: 8 }, { month: 'Feb', students: 58, companies: 11 },
  { month: 'Mar', students: 71, companies: 14 }, { month: 'Apr', students: 65, companies: 9 },
  { month: 'May', students: 89, companies: 17 }, { month: 'Jun', students: 95, companies: 20 },
];

const pendingItems = [
  { type: 'Skill Endorsement', name: 'Aisha Rahman — NLP', time: '2h ago', icon: CheckCircle2 },
  { type: 'Training Approval', name: 'Big Data with Spark (Nexus AI)', time: '5h ago', icon: GraduationCap },
  { type: 'Announcement', name: 'Career Fair 2026', time: '1d ago', icon: Bell },
  { type: 'Skill Endorsement', name: 'Marcus Lee — Apache Spark', time: '1d ago', icon: CheckCircle2 },
];

export default function AdminDashboardPage() {
  return (
    <DashboardLayout title="Admin Dashboard">
      <div className="max-w-6xl mx-auto space-y-8">
        <div>
          <h2 className="text-2xl font-bold text-neutral-900">Platform Overview</h2>
          <p className="text-neutral-500 mt-1">Monitor platform activity and manage pending approvals.</p>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-5">
          {[
            { label: 'Total Students', value: '420', icon: Users, color: 'bg-indigo-50 text-primary', trend: '+24 this month' },
            { label: 'Companies', value: '68', icon: Briefcase, color: 'bg-sky-50 text-secondary', trend: '+5 this month' },
            { label: 'Active Jobs', value: '134', icon: TrendingUp, color: 'bg-emerald-50 text-success', trend: '+18 this month' },
            { label: 'Pending Reviews', value: '12', icon: AlertCircle, color: 'bg-amber-50 text-warning', trend: 'Requires attention' },
          ].map((stat) => (
            <Card key={stat.label} className="p-5 flex items-start gap-4">
              <div className={`w-11 h-11 rounded-xl flex items-center justify-center shrink-0 ${stat.color}`}>
                <stat.icon size={20} />
              </div>
              <div>
                <p className="text-[10px] font-black text-neutral-400 uppercase tracking-widest leading-tight">{stat.label}</p>
                <p className="text-2xl font-black text-neutral-900 mt-0.5">{stat.value}</p>
                <p className="text-[10px] font-semibold text-neutral-400 mt-0.5">{stat.trend}</p>
              </div>
            </Card>
          ))}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
          {/* Registration trend */}
          <Card className="lg:col-span-3 p-6">
            <div className="flex items-center justify-between mb-6">
              <div>
                <h3 className="text-lg font-bold text-neutral-900">Registration Trend</h3>
                <p className="text-xs text-neutral-400 font-medium mt-0.5">New students vs companies (6 months)</p>
              </div>
            </div>
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={registrationData} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="month" tick={{ fontSize: 11, fontWeight: 600, fill: '#9ca3af' }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 11, fontWeight: 600, fill: '#9ca3af' }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={{ borderRadius: 12, border: 'none', boxShadow: '0 4px 20px rgba(0,0,0,0.1)', fontSize: 12 }} />
                <Line type="monotone" dataKey="students" stroke="#4f46e5" strokeWidth={3} dot={false} name="Students" />
                <Line type="monotone" dataKey="companies" stroke="#0ea5e9" strokeWidth={3} dot={false} name="Companies" />
              </LineChart>
            </ResponsiveContainer>
            <div className="flex items-center gap-6 mt-4">
              <span className="flex items-center gap-2 text-xs font-bold text-neutral-600"><span className="w-4 h-1 bg-primary rounded-full inline-block" /> Students</span>
              <span className="flex items-center gap-2 text-xs font-bold text-neutral-600"><span className="w-4 h-1 bg-secondary rounded-full inline-block" /> Companies</span>
            </div>
          </Card>

          {/* Pending actions */}
          <Card className="lg:col-span-2 p-6">
            <div className="flex items-center justify-between mb-5">
              <h3 className="text-lg font-bold text-neutral-900">Pending Actions</h3>
              <Badge variant="warning" className="text-[9px] font-black">{pendingItems.length} items</Badge>
            </div>
            <div className="space-y-3">
              {pendingItems.map((item, i) => (
                <div key={i} className="flex items-start gap-3 p-3 bg-neutral-50 rounded-xl border border-neutral-100">
                  <div className="w-8 h-8 bg-amber-50 text-warning rounded-lg flex items-center justify-center shrink-0">
                    <item.icon size={16} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-[10px] font-black text-neutral-400 uppercase tracking-widest">{item.type}</p>
                    <p className="text-xs font-bold text-neutral-900 truncate">{item.name}</p>
                    <p className="text-[10px] text-neutral-400 font-medium mt-0.5">{item.time}</p>
                  </div>
                </div>
              ))}
            </div>
          </Card>
        </div>

        {/* Quick actions */}
        <Card className="p-6">
          <h3 className="text-lg font-bold text-neutral-900 mb-5">Quick Actions</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {[
              { label: 'Review Approvals', href: '/approvals', icon: Clock, color: 'bg-amber-50 text-warning' },
              { label: 'Manage Courses', href: '/manage-courses', icon: GraduationCap, color: 'bg-indigo-50 text-primary' },
              { label: 'Endorse Skills', href: '/endorse', icon: CheckCircle2, color: 'bg-emerald-50 text-success' },
              { label: 'Post Announcement', href: '/post-announcement', icon: Bell, color: 'bg-sky-50 text-secondary' },
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
