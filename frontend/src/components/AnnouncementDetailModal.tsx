/** The announcement detail view, shared by the pages that show announcements.
 *
 *  It lived inside the post-announcement page, so the admin dashboard listed
 *  announcements as plain text with nothing to click: the detail existed but
 *  only one page could reach it. Moved here rather than copied, so the two
 *  cannot drift into showing different things about the same announcement.
 */

'use client';

import { motion } from 'framer-motion';
import { Clock, ExternalLink, FileText, X } from 'lucide-react';

import { Badge, Button } from '@/src/components/ui';
import { RichText } from '@/src/lib/richText';

export interface Announcement {
  id: number;
  title: string;
  message: string;
  categories: string[];
  audience: string;
  admin_name: string | null;
  supporting_doc: string | null;
  publish_time: string;
}

export const AUDIENCE_LABELS: Record<string, string> = {
  EVERYONE: 'Everyone', STUDENTS: 'Students Only', COMPANIES: 'Companies Only',
};

export function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

export function isImageUrl(url: string): boolean {
  return /\.(jpg|jpeg|png|gif|webp|svg)(\?|$)/i.test(url);
}

// ─── Detail Modal ─────────────────────────────────────────────────────────────

export default function AnnouncementDetailModal({ announcement: a, onClose }: { announcement: Announcement; onClose: () => void }) {
  return (
    <motion.div key="detail-backdrop"
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm px-4 py-8 overflow-y-auto"
      onClick={onClose}>
      <motion.div
        initial={{ scale: 0.96, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.96, opacity: 0 }}
        transition={{ type: 'spring', stiffness: 300, damping: 30 }}
        className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl my-auto"
        onClick={e => e.stopPropagation()}>

        {/* Header */}
        <div className="flex items-start justify-between gap-4 p-7 border-b border-neutral-100">
          <div className="flex-1 min-w-0">
            <div className="flex flex-wrap items-center gap-2 mb-3">
              {a.categories?.map(cat => (
                <Badge key={cat} variant="primary" className="text-[9px] font-black tracking-widest">{cat}</Badge>
              ))}
              <Badge variant="neutral" className="text-[9px] font-black tracking-widest">
                {AUDIENCE_LABELS[a.audience] ?? a.audience}
              </Badge>
            </div>
            <h2 className="text-xl font-black text-neutral-900 leading-tight">{a.title}</h2>
            <p className="text-[11px] text-neutral-400 font-medium mt-2 flex items-center gap-1">
              <Clock size={11} /> Published {timeAgo(a.publish_time)} · by {a.admin_name ?? 'Admin'}
            </p>
          </div>
          <button onClick={onClose}
            className="w-8 h-8 shrink-0 flex items-center justify-center rounded-lg hover:bg-neutral-100 text-neutral-400">
            <X size={18} />
          </button>
        </div>

        {/* Body */}
        <div className="p-7 space-y-5">
          <RichText
            className="text-sm text-neutral-700 leading-relaxed announcement-body"
            html={a.message}
          />

          {/* Attachment — image inline, other URLs as link */}
          {a.supporting_doc && (
            <div className="border border-neutral-200 rounded-xl overflow-hidden">
              {isImageUrl(a.supporting_doc) ? (
                <img src={a.supporting_doc} alt="Attachment" className="w-full max-h-80 object-contain bg-neutral-50" />
              ) : (
                <a href={a.supporting_doc} target="_blank" rel="noopener noreferrer"
                  className="flex items-center gap-3 p-4 hover:bg-neutral-50 transition-colors">
                  <div className="w-10 h-10 bg-indigo-50 rounded-lg flex items-center justify-center text-primary shrink-0">
                    <FileText size={20} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-bold text-neutral-900">Attached Document</p>
                    <p className="text-xs text-neutral-400 truncate">{a.supporting_doc}</p>
                  </div>
                  <ExternalLink size={15} className="text-neutral-400 shrink-0" />
                </a>
              )}
            </div>
          )}
        </div>

        <div className="px-7 pb-7">
          <Button variant="outline" fullWidth onClick={onClose}>Close</Button>
        </div>
      </motion.div>
    </motion.div>
  );
}
