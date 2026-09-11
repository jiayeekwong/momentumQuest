'use client';

import { useState, useEffect } from 'react';
import { Search, BookOpen, ExternalLink, GraduationCap, Clock, X, FileText } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { DashboardLayout } from '@/src/components/Layout';
import { Card, Badge, Button } from '@/src/components/ui';
import { cn } from '@/src/lib/utils';
import { apiFetch } from '@/src/lib/apiFetch';
import { RichText } from '@/src/lib/richText';

const TRAINING_PLATFORM = 'Training Programme';

interface LearningResource {
  id: number;
  skill: string;
  title: string;
  platform: string;
  url: string;
  type: string;
  scraped_at: string;
}

interface TrainingProgramme {
  id: number;
  title: string;
  skill: string | null;
  company_name: string | null;
  description: string;
  programme_duration: string;
  supporting_doc: string | null;
}

const PLATFORM_COLORS: Record<string, string> = {
  'freeCodeCamp':       'bg-green-700',
  'Microsoft Learn':    'bg-sky-700',
  'Cisco NetAcad':      'bg-blue-800',
  'Codecademy':         'bg-teal-700',
  'Coursera':           'bg-violet-700',
  [TRAINING_PLATFORM]:  'bg-amber-600',
};

function isImageUrl(url: string): boolean {
  return /\.(jpg|jpeg|png|gif|webp|svg)(\?|$)/i.test(url);
}

// ─── Training detail modal ──────────────────────────────────────────────────

function TrainingModal({ programme: p, onClose }: { programme: TrainingProgramme; onClose: () => void }) {
  return (
    <motion.div key="training-backdrop"
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm px-4 py-8 overflow-y-auto"
      onClick={onClose}>
      <motion.div
        initial={{ scale: 0.96, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.96, opacity: 0 }}
        transition={{ type: 'spring', stiffness: 300, damping: 30 }}
        className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl my-auto"
        onClick={e => e.stopPropagation()}>

        <div className="flex items-start justify-between gap-4 p-7 border-b border-neutral-100">
          <div className="flex-1 min-w-0">
            <div className="flex flex-wrap items-center gap-2 mb-3">
              <Badge variant="warning" className="text-[9px] font-black tracking-widest">Training Programme</Badge>
              {p.skill && <Badge variant="primary" className="text-[9px] font-black tracking-widest">{p.skill}</Badge>}
            </div>
            <h2 className="text-xl font-black text-neutral-900 leading-tight">{p.title}</h2>
            <div className="flex flex-wrap items-center gap-4 mt-2 text-[11px] text-neutral-400 font-medium">
              {p.company_name && <span>by {p.company_name}</span>}
              {p.programme_duration && <span className="flex items-center gap-1"><Clock size={11} /> {p.programme_duration}</span>}
            </div>
          </div>
          <button onClick={onClose} className="w-8 h-8 shrink-0 flex items-center justify-center rounded-lg hover:bg-neutral-100 text-neutral-400">
            <X size={18} />
          </button>
        </div>

        <div className="p-7 space-y-5">
          {p.description ? (
            <RichText
              className="text-sm text-neutral-700 leading-relaxed rich-text"
              html={p.description}
            />
          ) : (
            <p className="text-sm text-neutral-400 italic">No description provided.</p>
          )}

          {p.supporting_doc && (
            <div className="border border-neutral-200 rounded-xl overflow-hidden">
              {isImageUrl(p.supporting_doc) ? (
                <img src={p.supporting_doc} alt="Attachment" className="w-full max-h-80 object-contain bg-neutral-50" />
              ) : (
                <a href={p.supporting_doc} target="_blank" rel="noopener noreferrer"
                  className="flex items-center gap-3 p-4 hover:bg-neutral-50 transition-colors">
                  <div className="w-10 h-10 bg-indigo-50 rounded-lg flex items-center justify-center text-primary shrink-0">
                    <FileText size={20} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-bold text-neutral-900">Programme Material</p>
                    <p className="text-xs text-neutral-400 truncate">{p.supporting_doc}</p>
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

// ─── Page ────────────────────────────────────────────────────────────────────

const PAGE_SIZE = 24;
const SEARCH_DEBOUNCE_MS = 350;

/** One page of /api/resources/, plus the platform names for the filter tabs. */
interface ResourcePage {
  count: number;
  next: string | null;
  previous: string | null;
  results: LearningResource[];
  platforms: string[];
}

export default function ResourcesPage() {
  const [resources, setResources] = useState<LearningResource[]>([]);
  const [count, setCount] = useState(0);
  const [apiPlatforms, setApiPlatforms] = useState<string[]>([]);
  const [training, setTraining] = useState<TrainingProgramme[]>([]);
  // Loading is derived, not stored: it is true exactly while the page on
  // screen is not the page the current filters ask for. Storing it meant
  // setting state synchronously in the fetch effect, which cascades a render.
  const [loadedKey, setLoadedKey] = useState<string | null>(null);
  const [platform, setPlatform] = useState('All');
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [page, setPage] = useState(1);
  const [detailItem, setDetailItem] = useState<TrainingProgramme | null>(null);

  // Training programmes are company submissions and there are few of them, so
  // one small unpaginated request is fine here. The scraped catalogue is not.
  useEffect(() => {
    apiFetch('/api/resources/training/approved/')
      .then(r => r.json())
      .then((data: TrainingProgramme[]) => setTraining(Array.isArray(data) ? data : []))
      .catch(() => {});
  }, []);

  // Typing must not put a request on the wire per keystroke.
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search), SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [search]);

  // A changed filter invalidates the page number -- page 7 of Coursera is not
  // page 7 of edX, and a page past the end is a 404 -- so both setters reset
  // it. Done here rather than in an effect watching the filters, which would
  // render once with the stale page before correcting itself.
  const choosePlatform = (next: string) => { setPlatform(next); setPage(1); };
  const changeSearch = (next: string) => { setSearch(next); setPage(1); };

  const showingTraining = platform === TRAINING_PLATFORM;
  const requestKey = `${platform}|${debouncedSearch}|${page}`;
  const isLoading = !showingTraining && loadedKey !== requestKey;

  // The catalogue is filtered and paged by the server. It holds 20,430 rows;
  // fetching all of them to filter in the browser cost 5.4MB and rendered
  // every row into the DOM.
  useEffect(() => {
    if (showingTraining) return;   // nothing to fetch; training is already in memory

    const params = new URLSearchParams({ page: String(page) });
    if (platform !== 'All') params.set('platform', platform);
    if (debouncedSearch) params.set('search', debouncedSearch);

    // Aborted rather than merely ignored: a slow earlier response must not
    // overwrite a newer one, and the work is wasted once superseded.
    const controller = new AbortController();
    fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/resources/?${params.toString()}`,
          { signal: controller.signal })
      .then(r => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((data: ResourcePage) => {
        setResources(Array.isArray(data.results) ? data.results : []);
        setCount(typeof data.count === 'number' ? data.count : 0);
        // Kept once received: a filtered page reports the same full list, but
        // an error response reports none, and the tabs should not vanish.
        if (data.platforms?.length) setApiPlatforms(data.platforms);
      })
      .catch((err: unknown) => {
        if (err instanceof Error && err.name === 'AbortError') return;
        setResources([]);
        setCount(0);
      })
      .finally(() => {
        // Marks this key served, which is what clears the skeleton. Skipped on
        // abort so a superseded request cannot present itself as the answer.
        if (!controller.signal.aborted) setLoadedKey(requestKey);
      });

    return () => controller.abort();
  }, [platform, debouncedSearch, page, showingTraining, requestKey]);

  // The endpoint reports every platform in the catalogue. Deriving the tabs
  // from the rows on screen would list only the ones this page happens to show.
  const platforms = ['All', ...apiPlatforms,
                     ...(training.length > 0 ? [TRAINING_PLATFORM] : [])];

  const totalPages = Math.max(1, Math.ceil(count / PAGE_SIZE));

  // Training is a short list already in memory, so filtering it here needs no
  // request -- presentation state, not a query against the catalogue.
  const q = debouncedSearch.toLowerCase();
  const visibleTraining = (platform === 'All' || showingTraining)
    ? training.filter(t => !q || t.title.toLowerCase().includes(q)
                                || (t.skill ?? '').toLowerCase().includes(q))
    : [];

  const totalShown = resources.length + visibleTraining.length;

  return (
    <DashboardLayout title="Learning Resources">
      <div className="max-w-6xl mx-auto space-y-8">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h2 className="text-2xl font-bold text-neutral-900">Curated Learning Paths</h2>
            <p className="text-neutral-500 mt-1">
              Upskill with the best courses handpicked for your career goals.
            </p>
          </div>
          <div className="relative w-full md:w-64">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400" size={16} />
            <input
              type="text"
              placeholder="Search by title or skill..."
              value={search}
              onChange={(e) => changeSearch(e.target.value)}
              className="w-full h-10 pl-10 pr-4 bg-white border border-neutral-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
            />
          </div>
        </div>

        {/* Platform filter tabs — built from live data */}
        <div className="flex flex-wrap gap-2">
          {platforms.map((p) => (
            <button
              key={p}
              onClick={() => choosePlatform(p)}
              className={cn(
                'px-4 py-2 rounded-full text-xs font-bold transition-all border',
                platform === p
                  ? 'bg-primary text-white border-primary'
                  : 'bg-white text-neutral-600 border-neutral-200 hover:border-primary/40'
              )}
            >
              {p}
            </button>
          ))}
        </div>

        {/* Loading skeleton */}
        {isLoading && !showingTraining && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {Array.from({ length: 6 }).map((_, i) => (
              <Card key={i} className="p-0 overflow-hidden">
                <div className="h-32 bg-neutral-100 animate-pulse" />
                <div className="p-5 space-y-3">
                  <div className="h-3 bg-neutral-100 rounded animate-pulse w-1/3" />
                  <div className="h-4 bg-neutral-100 rounded animate-pulse w-3/4" />
                  <div className="h-3 bg-neutral-100 rounded animate-pulse w-1/2" />
                </div>
              </Card>
            ))}
          </div>
        )}

        {/* Grid */}
        {(!isLoading || showingTraining) && totalShown > 0 && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">

            {/* Training programme cards */}
            {visibleTraining.map((t) => (
              <Card key={`t-${t.id}`} className="p-0 overflow-hidden flex flex-col group hover:shadow-lg transition-all duration-300">
                <div className={cn('h-32 flex items-center justify-center p-6 text-white', PLATFORM_COLORS[TRAINING_PLATFORM])}>
                  <div className="text-center">
                    <GraduationCap size={28} className="mx-auto mb-2 opacity-60" />
                    <h5 className="text-base font-black leading-tight line-clamp-2">{t.title}</h5>
                  </div>
                </div>
                <div className="p-5 flex-1 flex flex-col gap-3">
                  <div>
                    <p className="text-[10px] font-black text-neutral-400 uppercase tracking-widest">
                      {t.company_name ?? 'Company'}
                    </p>
                    <h4 className="font-bold text-neutral-900 mt-0.5 line-clamp-2">{t.title}</h4>
                  </div>

                  <div className="flex flex-wrap gap-2">
                    {t.skill && <Badge variant="neutral" className="text-[9px] px-2 py-0.5">{t.skill}</Badge>}
                    {t.programme_duration && (
                      <span className="flex items-center gap-1 text-[10px] font-bold text-neutral-400">
                        <Clock size={10} /> {t.programme_duration}
                      </span>
                    )}
                  </div>

                  <div className="flex gap-2 mt-auto items-center">
                    <Badge variant="warning" className="text-[9px] shrink-0">Training Programme</Badge>
                    <Button fullWidth size="sm" className="h-8 text-xs" onClick={() => setDetailItem(t)}>
                      View Details
                    </Button>
                  </div>
                </div>
              </Card>
            ))}

            {/* Scraped learning resource cards */}
            {resources.map((res) => {
              const color = PLATFORM_COLORS[res.platform] ?? 'bg-neutral-700';
              return (
                <Card key={`r-${res.id}`} className="p-0 overflow-hidden flex flex-col group hover:shadow-lg transition-all duration-300">
                  <div className={cn('h-32 flex items-center justify-center p-6 text-white', color)}>
                    <div className="text-center">
                      <BookOpen size={28} className="mx-auto mb-2 opacity-60" />
                      <h5 className="text-base font-black leading-tight line-clamp-2">{res.title}</h5>
                    </div>
                  </div>
                  <div className="p-5 flex-1 flex flex-col gap-3">
                    <div>
                      <p className="text-[10px] font-black text-neutral-400 uppercase tracking-widest">
                        {res.platform}
                      </p>
                      <h4 className="font-bold text-neutral-900 mt-0.5 line-clamp-2">{res.title}</h4>
                    </div>

                    <Badge variant="neutral" className="text-[9px] px-2 py-0.5 self-start">
                      {res.skill}
                    </Badge>

                    <div className="flex gap-2 mt-auto items-center">
                      <Badge variant="primary" className="text-[9px] shrink-0">{res.type}</Badge>
                      <a href={res.url} target="_blank" rel="noopener noreferrer" className="flex-1">
                        <Button fullWidth size="sm" className="h-8 text-xs">
                          Enrol Now <ExternalLink size={12} className="ml-1" />
                        </Button>
                      </a>
                    </div>
                  </div>
                </Card>
              );
            })}
          </div>
        )}

        {/* Pagination — server-side; the grid above holds one page, never the
            whole catalogue. Deliberately plain: no infinite scroll, no
            virtualisation, so the page count is verifiable by looking at it. */}
        {!isLoading && !showingTraining && totalPages > 1 && (
          <div className="flex items-center justify-center gap-4 pt-2">
            <Button
              variant="outline"
              size="sm"
              className="h-9 px-4 text-xs"
              disabled={page <= 1}
              onClick={() => setPage(p => Math.max(1, p - 1))}
            >
              Previous
            </Button>
            <p className="text-xs font-bold text-neutral-500 tabular-nums">
              Page {page} of {totalPages}
              <span className="text-neutral-400 font-medium">
                {' '}· {count.toLocaleString()} resources
              </span>
            </p>
            <Button
              variant="outline"
              size="sm"
              className="h-9 px-4 text-xs"
              disabled={page >= totalPages}
              onClick={() => setPage(p => Math.min(totalPages, p + 1))}
            >
              Next
            </Button>
          </div>
        )}

        {/* Empty state */}
        {(!isLoading || showingTraining) && totalShown === 0 && (
          <div className="py-20 text-center">
            <BookOpen size={48} className="mx-auto text-neutral-200 mb-4" />
            <h3 className="text-lg font-bold text-neutral-900">No resources found</h3>
            <p className="text-neutral-500 mt-1 text-sm">
              {count === 0 && training.length === 0 && !debouncedSearch && platform === 'All'
                ? 'No resources have been scraped yet. Run the scraper first.'
                : 'Try adjusting your search or platform filter.'}
            </p>
          </div>
        )}
      </div>

      {/* Training detail modal */}
      <AnimatePresence>
        {detailItem && <TrainingModal programme={detailItem} onClose={() => setDetailItem(null)} />}
      </AnimatePresence>
    </DashboardLayout>
  );
}
