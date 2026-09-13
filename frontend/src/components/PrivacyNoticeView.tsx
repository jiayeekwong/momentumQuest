'use client';

/**
 * The privacy notice as the reader sees it.
 *
 * Starts from `initialNotice`, the snapshot rendered into the page's HTML at
 * build time, so the full text is present before any JavaScript runs and before
 * any request succeeds. /privacy-notice is the privacy-policy URL given to
 * Google, and a reviewer with scripts disabled -- or one who arrives while the
 * free API instance is asleep -- must still find a complete notice there.
 *
 * Once loaded it asks the API for the current notice and shows that instead,
 * because the backend is canonical: a notice published after this build, or a
 * contact address changed in production, appears without a redeploy. If the
 * request fails the snapshot simply stays. There is no error state here on
 * purpose -- replacing a readable legal document with "could not be loaded"
 * would turn a slow API into a missing privacy policy.
 */

import { useEffect, useState } from 'react';
import { ShieldCheck } from 'lucide-react';
import { fetchPrivacyNotice, type PrivacyNotice } from '@/src/lib/privacyNotice';

function formatDate(iso: string) {
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return iso;
  // UTC, because the effective date is a calendar date and not an instant.
  // "2026-09-01" parses as UTC midnight, so formatting it in the reader's own
  // zone showed "31 August 2026" to anyone west of Greenwich -- and, now that
  // the server renders this too, made the server and browser disagree.
  return parsed.toLocaleDateString('en-MY', {
    day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC',
  });
}

export function PrivacyNoticeView({ initialNotice }: { initialNotice: PrivacyNotice }) {
  const [notice, setNotice] = useState<PrivacyNotice>(initialNotice);

  useEffect(() => {
    let cancelled = false;
    fetchPrivacyNotice()
      .then(live => { if (!cancelled) setNotice(live); })
      // Keep the snapshot. See the note above.
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  return (
    <>
      <div className="mb-8 flex items-start gap-4">
        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-indigo-50 text-primary">
          <ShieldCheck size={22} />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-neutral-900">
            Personal Data Privacy Notice
          </h1>
          <p className="mt-1 text-sm text-neutral-500">
            Version {notice.version} · Effective {formatDate(notice.effective_date)}
          </p>
        </div>
      </div>

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
    </>
  );
}
