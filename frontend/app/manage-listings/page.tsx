'use client';

import { useState } from 'react';
import { Plus, Eye, Users, Clock, Pencil, Trash2, ToggleLeft, ToggleRight } from 'lucide-react';
import { DashboardLayout } from '@/src/components/Layout';
import { Card, Badge, Button } from '@/src/components/ui';
import Link from 'next/link';

type Listing = {
  id: string; title: string; applicants: number; views: number;
  closing: string; status: 'active' | 'closed' | 'draft';
};

const mockListings: Listing[] = [
  { id: '1', title: 'Data Scientist', applicants: 12, views: 340, closing: 'May 30, 2026', status: 'active' },
  { id: '2', title: 'Product Analyst', applicants: 7, views: 180, closing: 'Jun 5, 2026', status: 'active' },
  { id: '3', title: 'BI Developer', applicants: 0, views: 45, closing: 'Jun 20, 2026', status: 'draft' },
  { id: '4', title: 'Marketing Intern', applicants: 24, views: 600, closing: 'Apr 30, 2026', status: 'closed' },
];

const statusVariants: Record<string, 'success' | 'neutral' | 'warning'> = {
  active: 'success', draft: 'warning', closed: 'neutral',
};

export default function ManageListingsPage() {
  const [listings, setListings] = useState<Listing[]>(mockListings);

  const toggleStatus = (id: string) => {
    setListings((prev) => prev.map((l) =>
      l.id === id ? { ...l, status: l.status === 'active' ? 'closed' : 'active' } : l
    ));
  };

  const deleteListing = (id: string) => setListings((prev) => prev.filter((l) => l.id !== id));

  return (
    <DashboardLayout title="Manage Listings">
      <div className="max-w-5xl mx-auto space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-bold text-neutral-900">Job Listings</h2>
            <p className="text-neutral-500 mt-1 text-sm">{listings.filter((l) => l.status === 'active').length} active listings</p>
          </div>
          <Link href="/post-job">
            <Button className="h-11 px-6"><Plus size={16} className="mr-2" /> Post New Job</Button>
          </Link>
        </div>

        <div className="space-y-4">
          {listings.map((listing) => (
            <Card key={listing.id} className="p-6 hover:border-primary/30 transition-all group">
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div className="flex-1">
                  <div className="flex items-center gap-3 mb-1">
                    <h3 className="text-lg font-bold text-neutral-900 group-hover:text-primary transition-colors">{listing.title}</h3>
                    <Badge variant={statusVariants[listing.status]} className="capitalize text-[9px] font-black tracking-widest">{listing.status}</Badge>
                  </div>
                  <div className="flex flex-wrap items-center gap-5 text-xs font-semibold text-neutral-500">
                    <span className="flex items-center gap-1.5"><Users size={13} /> {listing.applicants} applicants</span>
                    <span className="flex items-center gap-1.5"><Eye size={13} /> {listing.views} views</span>
                    <span className="flex items-center gap-1.5"><Clock size={13} /> Closes {listing.closing}</span>
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <Link href="/review-applications">
                    <Button variant="outline" size="sm" className="h-9 text-xs">
                      <Users size={14} className="mr-1.5" /> View Applicants
                    </Button>
                  </Link>
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-9 text-xs"
                    onClick={() => toggleStatus(listing.id)}
                    title={listing.status === 'active' ? 'Close listing' : 'Activate listing'}
                  >
                    {listing.status === 'active'
                      ? <ToggleRight size={16} className="text-success" />
                      : <ToggleLeft size={16} className="text-neutral-400" />}
                  </Button>
                  <Button variant="outline" size="sm" className="h-9 w-9 p-0">
                    <Pencil size={14} />
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-9 w-9 p-0 text-danger hover:bg-danger/5 hover:border-danger/30"
                    onClick={() => deleteListing(listing.id)}
                  >
                    <Trash2 size={14} />
                  </Button>
                </div>
              </div>
            </Card>
          ))}
        </div>

        {listings.length === 0 && (
          <div className="py-20 text-center">
            <div className="w-20 h-20 bg-neutral-100 rounded-full flex items-center justify-center mx-auto mb-4 text-neutral-300">
              <Plus size={40} />
            </div>
            <h3 className="text-xl font-bold text-neutral-900">No listings yet</h3>
            <p className="text-neutral-500 mt-1">Post your first job to start receiving applications.</p>
            <Link href="/post-job"><Button className="mt-6">Post a Job</Button></Link>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
