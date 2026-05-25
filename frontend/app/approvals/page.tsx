'use client';

import { useState } from 'react';
import { CheckCircle2, XCircle, Clock, GraduationCap, Bell, Filter } from 'lucide-react';
import { DashboardLayout } from '@/src/components/Layout';
import { Card, Badge, Button } from '@/src/components/ui';
import { cn } from '@/src/lib/utils';

type ApprovalType = 'training' | 'announcement' | 'endorsement';
type ApprovalStatus = 'pending' | 'approved' | 'rejected';

type ApprovalItem = {
  id: string; type: ApprovalType; title: string; submittedBy: string;
  submittedDate: string; status: ApprovalStatus; details: string;
};

const mockItems: ApprovalItem[] = [
  { id: '1', type: 'training', title: 'Big Data with Spark & Hadoop', submittedBy: 'Nexus AI', submittedDate: 'May 21, 2026', status: 'pending', details: 'Udacity Nanodegree — 96h · Skills: Apache Spark, Hadoop, PySpark' },
  { id: '2', type: 'announcement', title: 'Career Fair 2026 — June Edition', submittedBy: 'FinTrack', submittedDate: 'May 20, 2026', status: 'pending', details: 'Announcing our annual career fair on June 15. Open to all students.' },
  { id: '3', type: 'training', title: 'Advanced SQL Masterclass', submittedBy: 'Global Retail Co', submittedDate: 'May 18, 2026', status: 'approved', details: 'Coursera Course — 20h · Skills: SQL, PostgreSQL, Data Warehousing' },
  { id: '4', type: 'announcement', title: 'Internship Drive — Q3 2026', submittedBy: 'SoftSystems', submittedDate: 'May 15, 2026', status: 'rejected', details: 'Promoted internship opportunities for Q3 2026 intake.' },
];

const typeIcons: Record<ApprovalType, React.ElementType> = {
  training: GraduationCap, announcement: Bell, endorsement: CheckCircle2,
};

const typeColors: Record<ApprovalType, string> = {
  training: 'bg-indigo-50 text-primary', announcement: 'bg-sky-50 text-secondary', endorsement: 'bg-emerald-50 text-success',
};

const statusVariants: Record<ApprovalStatus, 'neutral' | 'success' | 'danger'> = {
  pending: 'neutral', approved: 'success', rejected: 'danger',
};

export default function ApprovalsPage() {
  const [items, setItems] = useState<ApprovalItem[]>(mockItems);
  const [filter, setFilter] = useState<'All' | ApprovalStatus>('All');

  const update = (id: string, status: ApprovalStatus) =>
    setItems((prev) => prev.map((item) => item.id === id ? { ...item, status } : item));

  const filtered = items.filter((i) => filter === 'All' || i.status === filter);

  const pendingCount = items.filter((i) => i.status === 'pending').length;

  return (
    <DashboardLayout title="Approvals">
      <div className="max-w-4xl mx-auto space-y-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h2 className="text-2xl font-bold text-neutral-900 flex items-center gap-3">
              Pending Approvals
              {pendingCount > 0 && <Badge variant="warning" className="text-xs font-black">{pendingCount} pending</Badge>}
            </h2>
            <p className="text-neutral-500 mt-1 text-sm">Review and approve training submissions and announcements.</p>
          </div>
          <div className="flex gap-1 p-1 bg-neutral-100 rounded-xl">
            {(['All', 'pending', 'approved', 'rejected'] as const).map((f) => (
              <button key={f} onClick={() => setFilter(f)}
                className={cn('px-4 py-2 text-xs font-bold rounded-lg transition-all capitalize', filter === f ? 'bg-white shadow-sm text-primary' : 'text-neutral-500 hover:text-neutral-900')}>
                {f}
              </button>
            ))}
          </div>
        </div>

        <div className="space-y-4">
          {filtered.map((item) => {
            const Icon = typeIcons[item.type];
            return (
              <Card key={item.id} className="p-6 hover:border-primary/20 transition-all">
                <div className="flex flex-col md:flex-row md:items-start gap-5">
                  <div className={cn('w-12 h-12 rounded-xl flex items-center justify-center shrink-0', typeColors[item.type])}>
                    <Icon size={22} />
                  </div>
                  <div className="flex-1">
                    <div className="flex flex-col md:flex-row md:items-start justify-between gap-2 mb-1">
                      <div>
                        <p className="text-[10px] font-black text-neutral-400 uppercase tracking-widest capitalize mb-0.5">{item.type}</p>
                        <h3 className="text-base font-bold text-neutral-900">{item.title}</h3>
                      </div>
                      <Badge variant={statusVariants[item.status]} className="capitalize text-[10px] font-black tracking-widest shrink-0">{item.status}</Badge>
                    </div>
                    <p className="text-xs font-semibold text-neutral-500 mb-1">By {item.submittedBy} · {item.submittedDate}</p>
                    <p className="text-sm text-neutral-600 leading-relaxed">{item.details}</p>
                    {item.status === 'pending' && (
                      <div className="flex gap-3 mt-4">
                        <Button size="sm" className="h-9 text-xs bg-success hover:bg-success/90 text-white flex items-center gap-1.5"
                          onClick={() => update(item.id, 'approved')}>
                          <CheckCircle2 size={14} /> Approve
                        </Button>
                        <Button size="sm" variant="outline" className="h-9 text-xs text-danger border-danger/30 hover:bg-danger/5 flex items-center gap-1.5"
                          onClick={() => update(item.id, 'rejected')}>
                          <XCircle size={14} /> Reject
                        </Button>
                      </div>
                    )}
                  </div>
                </div>
              </Card>
            );
          })}
        </div>

        {filtered.length === 0 && (
          <div className="py-20 text-center">
            <div className="w-20 h-20 bg-neutral-100 rounded-full flex items-center justify-center mx-auto mb-4 text-neutral-300">
              <Clock size={40} />
            </div>
            <h3 className="text-xl font-bold text-neutral-900">All clear!</h3>
            <p className="text-neutral-500 mt-1">No items matching this filter.</p>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
