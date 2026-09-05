'use client';

/**
 * The full MomentumQuest privacy notice.
 *
 * Deliberately a top-level route outside every route group, and outside
 * DashboardLayout: acknowledging this notice is a precondition of creating an
 * account, so it has to be readable by someone who does not have one. Anything
 * wrapped in DashboardLayout redirects an unauthenticated visitor to /login.
 *
 * The text is fetched rather than hardcoded. A new notice version is then a
 * backend change alone, and the page can never drift out of sync with the
 * version students are actually recorded as having accepted.
 */

import Link from 'next/link';
import { ArrowLeft, ShieldCheck } from 'lucide-react';
import { Logo } from '@/src/components/Logo';
import { usePrivacyNotice } from '@/src/lib/privacyNotice';

function formatDate(iso: string) {
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return iso;
  return parsed.toLocaleDateString('en-MY', { day: 'numeric', month: 'long', year: 'numeric' });
}

export default function PrivacyNoticePage() {
  const { notice, isLoading, error } = usePrivacyNotice();

  return (
    <div className="min-h-screen bg-neutral-50">
      <header className="border-b border-neutral-200 bg-white">
        <div className="mx-auto flex max-w-3xl items-center justify-between gap-4 px-6 py-4">
          <Logo size="sm" />
          <Link
            href="/signup"
            className="flex items-center gap-1.5 text-sm font-semibold text-primary hover:underline"
          >
            <ArrowLeft size={16} /> Back to sign up
          </Link>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-6 py-10">
        <div className="mb-8 flex items-start gap-4">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-indigo-50 text-primary">
            <ShieldCheck size={22} />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-neutral-900">
              Personal Data Privacy Notice
            </h1>
            {notice && (
              <p className="mt-1 text-sm text-neutral-500">
                Version {notice.version} · Effective {formatDate(notice.effective_date)}
              </p>
            )}
          </div>
        </div>

        {isLoading && (
          <div className="space-y-4">
            {[0, 1, 2, 3].map(i => (
              <div key={i} className="h-24 animate-pulse rounded-2xl bg-neutral-100" />
            ))}
          </div>
        )}

        {error && (
          <div className="rounded-lg border border-red-100 bg-red-50 p-3 text-sm text-danger">
            The privacy notice could not be loaded. Please try again shortly.
          </div>
        )}

        {notice && (
          <article className="space-y-8 rounded-2xl border border-neutral-100 bg-white p-8">
            {notice.sections.map(section => (
              <section key={section.heading} className="space-y-3">
                <h2 className="text-base font-bold text-neutral-900">{section.heading}</h2>
                {section.blocks.map((block, i) =>
                  block.type === 'list' ? (
                    <ul key={i} className="list-disc space-y-1 pl-6 text-sm text-neutral-600">
                      {block.items?.map(item => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                  ) : (
                    <p key={i} className="text-sm leading-relaxed text-neutral-600">
                      {block.text}
                    </p>
                  )
                )}
              </section>
            ))}

            {notice.contact_email && (
              <section className="space-y-2 border-t border-neutral-100 pt-6">
                <h2 className="text-base font-bold text-neutral-900">Contact</h2>
                <p className="text-sm text-neutral-600">
                  Questions about this notice or your personal data can be sent to{' '}
                  <a
                    href={`mailto:${notice.contact_email}`}
                    className="font-semibold text-primary hover:underline"
                  >
                    {notice.contact_email}
                  </a>
                  .
                </p>
              </section>
            )}
          </article>
        )}
      </main>
    </div>
  );
}
