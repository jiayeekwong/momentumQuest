'use client';

import { useRouter } from 'next/navigation';
import { Briefcase } from 'lucide-react';
import { DashboardLayout } from '@/src/components/Layout';
import { Card } from '@/src/components/ui';
import { PostJobModal } from '@/src/components/company/PostJobModal';

/**
 * Backward-compatible entry point for bookmarks and old links.
 *
 * All visible company entry points use PostJobModal directly. Keeping this
 * route on the same component prevents the old full-page form from drifting
 * away from the dashboard and Manage Listings experience.
 */
export default function PostJobPage() {
  const router = useRouter();

  return (
    <DashboardLayout title="Post a Job">
      <Card className="mx-auto max-w-xl p-10 text-center">
        <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-indigo-50 text-primary">
          <Briefcase size={26} />
        </div>
        <h1 className="text-xl font-bold text-neutral-900">Create a Job Listing</h1>
        <p className="mt-2 text-sm text-neutral-500">
          Complete the job details in the posting form.
        </p>
      </Card>

      <PostJobModal
        open
        onClose={() => router.replace('/manage-listings')}
      />
    </DashboardLayout>
  );
}
