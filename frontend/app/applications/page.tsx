'use client';

import { useState } from 'react';
import { Search, Filter, Clock, MapPin, ChevronRight, FileText } from 'lucide-react';
import { DashboardLayout } from '@/src/components/Layout';
import { Card, Badge, Button } from '@/src/components/ui';
import { cn } from '@/src/lib/utils';

const applications = [
  { id: '1', title: 'Data Scientist', company: 'Nexus AI', date: 'May 02, 2026', status: 'shortlisted', unread: true },
  { id: '2', title: 'Product Analyst', company: 'FinTrack', date: 'April 28, 2026', status: 'shortlisted', unread: false },
  { id: '3', title: 'Junior Data Analyst', company: 'HealthTech', date: 'April 22, 2026', status: 'pending', unread: false },
  { id: '4', title: 'Analytics Intern', company: 'SoftSystems', date: 'April 15, 2026', status: 'rejected', unread: false },
];

const statusVariants: Record<string, 'neutral' | 'primary' | 'warning' | 'danger' | 'success'> = {
  pending: 'neutral', shortlisted: 'primary', interview: 'warning', rejected: 'danger', accepted: 'success',
};

export default function MyApplicationsPage() {
  const [filter, setFilter] = useState('All');

  const filtered = applications.filter(a => filter === 'All' || a.status.toLowerCase() === filter.toLowerCase());

  return (
    <DashboardLayout title="My Applications">
      <div className="max-w-5xl mx-auto space-y-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex p-1 bg-neutral-100 rounded-xl">
            {['All', 'Pending', 'Shortlisted', 'Rejected'].map((tab) => (
              <button key={tab} onClick={() => setFilter(tab)} className={cn('px-4 py-2 text-xs font-bold rounded-lg transition-all', filter === tab ? 'bg-white shadow-sm text-primary' : 'text-neutral-500 hover:text-neutral-900')}>
                {tab}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-3">
            <div className="relative flex-1 md:w-64">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400" size={16} />
              <input type="text" placeholder="Search applications..." className="w-full h-10 pl-10 pr-4 bg-white border border-neutral-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20" />
            </div>
            <Button variant="outline" size="sm" className="h-10"><Filter size={18} className="mr-2" /> Filter</Button>
          </div>
        </div>

        <div className="space-y-4">
          {filtered.map((app) => (
            <Card key={app.id} className="p-0 overflow-hidden hover:border-primary/30 transition-all group">
              <div className="p-6 flex flex-col md:flex-row md:items-center justify-between gap-6">
                <div className="flex items-start gap-4">
                  <div className="w-14 h-14 rounded-xl bg-neutral-100 flex items-center justify-center text-neutral-400">
                    <FileText size={24} />
                  </div>
                  <div className="relative">
                    {app.unread && <span className="absolute -top-1 -right-1 w-2.5 h-2.5 bg-primary rounded-full border-2 border-white animate-pulse" />}
                    <h3 className="text-lg font-bold text-neutral-900 group-hover:text-primary transition-colors">{app.title}</h3>
                    <p className="text-sm font-semibold text-neutral-600">{app.company}</p>
                    <div className="flex items-center gap-4 mt-2">
                      <span className="flex items-center gap-1.5 text-xs text-neutral-400"><Clock size={14} /> Applied on {app.date}</span>
                      <span className="flex items-center gap-1.5 text-xs text-neutral-400"><MapPin size={14} /> Hybrid</span>
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-6">
                  <Badge variant={statusVariants[app.status]} className="capitalize px-4 py-1.5 text-[10px] tracking-widest font-black">{app.status}</Badge>
                  <Button variant="outline" className="h-11 px-6 group-hover:bg-primary group-hover:text-white group-hover:border-primary transition-all">
                    View Details <ChevronRight size={16} className="ml-2" />
                  </Button>
                </div>
              </div>
            </Card>
          ))}
        </div>

        {filtered.length === 0 && (
          <div className="py-20 text-center">
            <div className="w-20 h-20 bg-neutral-100 rounded-full flex items-center justify-center mx-auto mb-4 text-neutral-300"><FileText size={40} /></div>
            <h3 className="text-xl font-bold text-neutral-900">No applications found</h3>
            <p className="text-neutral-500 mt-1">Start your career journey by applying for relevant jobs.</p>
            <Button className="mt-6">Browse Job Listings</Button>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
