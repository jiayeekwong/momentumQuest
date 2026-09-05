'use client';

import { useAuth } from '@/src/context/AuthContext';
import { DashboardLayout } from '@/src/components/Layout';
import { Card, Badge, Button } from '@/src/components/ui';
import { Briefcase, Target, Star, Bell, ChevronRight, Sparkles, ArrowUpRight, X, FileText, ExternalLink, Paperclip, AlertTriangle, TrendingDown } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';
import { motion, AnimatePresence } from 'motion/react';
import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { apiFetch } from '@/src/lib/apiFetch';
import { RichText } from '@/src/lib/richText';

const statusVariants: Record<string, 'neutral' | 'primary' | 'warning' | 'danger' | 'success'> = {
  pending: 'neutral', shortlisted: 'primary', interview: 'warning', rejected: 'danger', accepted: 'success',
};

interface Announcement {
  id: number;
  title: string;
  message: string;
  categories: string[];
  supporting_doc: string | null;
  publish_time: string;
}

interface DemandPoint {
  month: string;
  label: string;
  job_count: number | null;
  observed: boolean;
}

interface RankedArea {
  name: string;
  job_count: number;
}

interface AreaOption {
  name: string;
  listing_count: number;
  // The Market Roles inside this area with enough adverts to chart.
  roles: { id: number; name: string; listing_count: number }[];
}

interface RankedMarketRole {
  name: string;
  broad_area: string;
  job_count: number;
}

interface RankedCategory {
  id: number;
  category_name: string;
  job_count: number;
}

interface MarketDemand {
  mode: 'OVERVIEW' | 'TARGET';
  period_months: number;
  title: string;
  // Set when the chart is scoped to one Market Role rather than a whole area.
  target_market_role: string | null;
  target_broad_area: string | null;
  series: DemandPoint[];
  // Still open on JobStreet, and the only ones the skill gap measures
  // against. Distinct from the 12-month figure the trend line is drawn from.
  total_postings: number;
  total_postings_in_period: number;
  // The month still running. Reported beside the chart, never plotted in it:
  // one day of September is not a fall from August, but drawn as a point it
  // is indistinguishable from one.
  month_in_progress: { label: string; job_count: number } | null;
  // Null whenever the two months cannot be honestly compared. `change_basis`
  // says which case it is, so the tile can explain rather than show a dash.
  demand_change_percentage: number | null;
  change_basis: 'MONTH_ON_MONTH' | 'UNEVEN_COLLECTION' | 'SINGLE_MONTH'
              | 'CURRENT_MONTH_ONLY' | 'NOT_ENOUGH_COLLECTED';
  collected_months: number;
  top_broad_areas: RankedArea[];
  top_market_roles: RankedMarketRole[];
  // How many adverts the role ranking rests on, so the UI can say so rather
  // than presenting a handful of adverts as the whole market.
  market_role_postings: number;
  top_categories: RankedCategory[];
  data_quality: {
    first_observed_date: string | null;
    latest_observed_date: string | null;
    freshness_days: number | null;
    is_stale: boolean;
    market_postings_in_period: number;
    live_market_postings: number;
    // How many adverts were placed on a Market Role at all. "Classified",
    // not "verified": nothing here is human-checked, and the label must not
    // imply otherwise.
    matched_postings_in_period: number;
    matched_coverage_percentage: number;
  };
}

interface RecentApplication {
  id: number;
  job_id: number;
  job_title: string;
  company_name: string;
  status: string;
  applied_time: string;
}

interface StudentDashboardResponse {
  skills_count: number;
  applications_count: number;
  recent_applications: RecentApplication[];
  announcements: Announcement[];
  market_demand: MarketDemand;
}

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function AnnouncementDetailModal({ a, onClose }: { a: Announcement; onClose: () => void }) {
  const isImage = (url: string) => /\.(jpg|jpeg|png|gif|webp)(\?|$)/i.test(url);

  return (
    <motion.div
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm px-4 py-8 overflow-y-auto"
      onClick={onClose}>
      <motion.div
        initial={{ scale: 0.96, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.96, opacity: 0 }}
        transition={{ type: 'spring', stiffness: 300, damping: 30 }}
        className="bg-white rounded-2xl shadow-2xl w-full max-w-xl my-auto"
        onClick={e => e.stopPropagation()}>

        {/* Header */}
        <div className="flex items-start justify-between gap-4 p-6 border-b border-neutral-100">
          <div className="flex-1 min-w-0">
            {a.categories?.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mb-2">
                {a.categories.map(cat => (
                  <Badge key={cat} variant="primary" className="text-[9px] font-black tracking-widest">{cat}</Badge>
                ))}
              </div>
            )}
            <h2 className="text-lg font-black text-neutral-900 leading-tight">{a.title}</h2>
            <p className="text-[10px] text-neutral-400 font-medium mt-1">{timeAgo(a.publish_time)}</p>
          </div>
          <button onClick={onClose}
            className="w-8 h-8 shrink-0 flex items-center justify-center rounded-lg hover:bg-neutral-100 text-neutral-400">
            <X size={17} />
          </button>
        </div>

        {/* Body */}
        <div className="p-6 space-y-4">
          <RichText
            className="text-sm text-neutral-700 leading-relaxed announcement-body"
            html={a.message}
          />

          {/* Attachment */}
          {a.supporting_doc && (
            <div className="border border-neutral-200 rounded-xl overflow-hidden mt-2">
              {isImage(a.supporting_doc) ? (
                <img src={a.supporting_doc} alt="Attachment" className="w-full max-h-72 object-contain bg-neutral-50" />
              ) : (
                <a href={a.supporting_doc} target="_blank" rel="noopener noreferrer"
                  className="flex items-center gap-3 p-4 hover:bg-neutral-50 transition-colors">
                  <div className="w-10 h-10 bg-indigo-50 rounded-lg flex items-center justify-center text-primary shrink-0">
                    <FileText size={20} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-bold text-neutral-900">Attached Document</p>
                    <p className="text-xs text-neutral-400">Click to open</p>
                  </div>
                  <ExternalLink size={14} className="text-neutral-400 shrink-0" />
                </a>
              )}
            </div>
          )}
        </div>

        <div className="px-6 pb-6">
          <Button variant="outline" fullWidth onClick={onClose}>Close</Button>
        </div>
      </motion.div>
    </motion.div>
  );
}

/**
 * Why a month-on-month figure is missing. Shown in place of the number, so
 * the tile says what is wrong instead of leaving the reader to guess.
 */
const CHANGE_LABEL: Record<string, string> = {
  UNEVEN_COLLECTION: 'Collection uneven',
  SINGLE_MONTH: 'One month so far',
  CURRENT_MONTH_ONLY: 'This month only',
  NOT_ENOUGH_COLLECTED: 'Not enough history',
};

const CHANGE_EXPLAINER: Record<string, string> = {
  UNEVEN_COLLECTION:
    'The scraper ran a different number of times in the two most recent months, '
    + 'so the difference between them reflects the collection schedule rather than '
    + 'employer demand. Run it on a regular schedule and this becomes comparable.',
  SINGLE_MONTH: 'Only one completed month has been collected, so there is nothing to compare it with.',
  CURRENT_MONTH_ONLY: 'Only the month in progress has been collected. A part-month cannot be compared with a full one.',
  NOT_ENOUGH_COLLECTED: 'No completed month has been collected yet.',
};

export default function DashboardPage() {
  const { user, updateUser } = useAuth();
  const firstName = user?.name?.split(' ')[0] ?? 'there';
  const [skillsCount,          setSkillsCount]          = useState<number | null>(null);
  const [applicationsCount,    setApplicationsCount]    = useState<number | null>(null);
  const [announcements,        setAnnouncements]        = useState<Announcement[]>([]);
  const [recentApplications,   setRecentApplications]   = useState<RecentApplication[]>([]);
  const [marketDemand,         setMarketDemand]         = useState<MarketDemand | null>(null);
  const [dashboardLoading,     setDashboardLoading]     = useState(true);
  const [dashboardError,       setDashboardError]       = useState('');
  const [selectedAnnouncement, setSelectedAnnouncement] = useState<Announcement | null>(null);
  // Browsing a career's trend is separate from committing to it as a
  // target — the student can flip between roles as often as they like.
  // One string covers both levels: "area:Data & AI" or "role:Data Analyst".
  // A bare name could not say which of the two it meant.
  const [trendScope,           setTrendScope]           = useState<string>('');
  const [areas,                setAreas]                = useState<AreaOption[]>([]);
  const [trendLoading,         setTrendLoading]         = useState(false);

  const loadDashboard = useCallback(async () => {
    try {
      const response = await apiFetch('/api/dashboard/student/');
      if (!response.ok) throw new Error('Unable to load dashboard analytics.');
      const data = await response.json() as StudentDashboardResponse;
      setDashboardError('');
      setSkillsCount(data.skills_count ?? 0);
      setApplicationsCount(data.applications_count ?? 0);
      setAnnouncements(data.announcements ?? []);
      setRecentApplications(data.recent_applications ?? []);
      setMarketDemand(data.market_demand ?? null);
    } catch (error) {
      setDashboardError(error instanceof Error ? error.message : 'Unable to load dashboard analytics.');
    } finally {
      setDashboardLoading(false);
    }
  }, []);

  useEffect(() => {
    queueMicrotask(() => void loadDashboard());
  }, [loadDashboard]);

  // Only Market Roles with classified adverts behind them — anything else
  // renders an empty chart.
  useEffect(() => {
    apiFetch('/api/dashboard/skill-gap/market-roles/')
      .then(r => (r.ok ? r.json() : null))
      .then((data) => setAreas(data?.results ?? []))
      .catch(() => {});
  }, []);

  // Re-scope only the chart when the student browses another area or role.
  const loadTrend = useCallback(async (scope: string) => {
    setTrendLoading(true);
    try {
      const [kind, ...rest] = scope.split(':');
      const value = rest.join(':');
      const query =
        kind === 'area' ? `?broad_area=${encodeURIComponent(value)}`
        : kind === 'role' ? `?role=${encodeURIComponent(value)}`
        : '';
      const response = await apiFetch(`/api/dashboard/market-demand/${query}`);
      if (response.ok) setMarketDemand(await response.json() as MarketDemand);
    } catch {
      // leave the previous chart in place
    } finally {
      setTrendLoading(false);
    }
  }, []);

  const plottedPoints = marketDemand?.series.filter(
    (point) => point.job_count !== null) ?? [];
  const collectedGaps = (marketDemand?.series ?? []).filter(
    (point) => !point.observed).length;

  return (
    <DashboardLayout title="Dashboard">
      <div className="max-w-6xl mx-auto space-y-8">
        {/* Hero greeting */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h2 className="text-2xl font-bold text-neutral-900">Good morning, {firstName} 👋</h2>
            <p className="text-neutral-500 mt-1">Here&apos;s what&apos;s happening with your career today.</p>
          </div>
          <Link href="/jobs">
            <Button className="h-11 px-6">
              <Sparkles size={16} className="mr-2" /> Browse Jobs
            </Button>
          </Link>
        </div>

        {/* Stat cards */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-5">
          {[
            { label: 'Applications Sent', value: applicationsCount !== null ? String(applicationsCount) : '—', icon: Briefcase, color: 'bg-indigo-50 text-primary', trend: 'from your applications' },
            // Open postings, not everything ever scraped: this number sat
            // beside a jobs page listing far fewer, because it counted the
            // closed months the trend line needs.
            { label: marketDemand?.mode === 'TARGET' ? 'Open Target Postings' : 'Open Job Postings', value: marketDemand ? String(marketDemand.total_postings) : '—', icon: Target, color: 'bg-emerald-50 text-success', trend: marketDemand ? `of ${marketDemand.total_postings_in_period} seen in ${marketDemand.period_months} months` : 'still open on JobStreet' },
            { label: 'Skills in Profile', value: skillsCount !== null ? String(skillsCount) : '—', icon: Star, color: 'bg-amber-50 text-warning', trend: 'from your profile' },
          ].map((stat) => (
            <Card key={stat.label} className="p-6 flex items-start gap-5">
              <div className={`w-12 h-12 rounded-xl flex items-center justify-center shrink-0 ${stat.color}`}>
                <stat.icon size={22} />
              </div>
              <div>
                <p className="text-[10px] font-black text-neutral-400 uppercase tracking-widest">{stat.label}</p>
                <p className="text-3xl font-black text-neutral-900 mt-1">{stat.value}</p>
                <p className="text-xs font-medium text-success mt-1 flex items-center gap-1">
                  <ArrowUpRight size={12} />{stat.trend}
                </p>
              </div>
            </Card>
          ))}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
          {/* Job demand trend */}
          <Card className="lg:col-span-3 p-6">
            <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3 mb-5">
              <div>
                <h3 className="text-lg font-bold text-neutral-900">
                  {marketDemand?.title ?? 'Job Demand Trend'}
                </h3>
                <p className="text-xs text-neutral-400 font-medium mt-0.5">
                  Unique scraped job postings by month — missing collection periods are left blank
                </p>
              </div>
              <Badge
                variant={marketDemand?.mode === 'TARGET' ? 'primary' : 'neutral'}
                className="text-[10px] font-black tracking-widest shrink-0"
              >
                {marketDemand?.mode !== 'TARGET' ? 'MARKET OVERVIEW'
                  : marketDemand.target_market_role ? 'MARKET ROLE' : 'CAREER AREA'}
              </Badge>
            </div>

            {/* Browse any career's trend — does not change your saved target */}
            <div className="flex flex-col sm:flex-row sm:items-center gap-2 mb-5">
              <select
                value={trendScope}
                onChange={(e) => {
                  setTrendScope(e.target.value);
                  void loadTrend(e.target.value);
                }}
                className="h-10 flex-1 rounded-lg border border-neutral-300 bg-white px-3 text-sm text-neutral-800 focus:outline-none focus:ring-2 focus:ring-primary/20"
              >
                <option value="">
                  {user?.targetRoles?.length ? 'My career' : 'Whole market'}
                </option>
                {/* Grouped by Broad Area, with the area itself selectable
                    above its Market Roles. Both levels are offered because
                    they answer different questions and rest on different
                    amounts of evidence. Nothing without adverts behind it is
                    listed, so every option charts something. */}
                {areas.map((area) => (
                  <optgroup key={area.name} label={area.name}>
                    <option value={`area:${area.name}`}>
                      All {area.name} ({area.listing_count} jobs)
                    </option>
                    {area.roles.map((role) => (
                      <option key={role.id} value={`role:${role.name}`}>
                        {role.name} ({role.listing_count} jobs)
                      </option>
                    ))}
                  </optgroup>
                ))}
              </select>
              {trendLoading && (
                <span className="text-xs text-neutral-400 font-medium shrink-0">Updating…</span>
              )}
            </div>

            {dashboardError ? (
              <div className="h-52 rounded-xl bg-red-50 text-danger flex items-center justify-center text-sm font-semibold px-6 text-center">
                {dashboardError}
              </div>
            ) : dashboardLoading ? (
              <div className="h-52 rounded-xl bg-neutral-50 animate-pulse" />
            ) : plottedPoints.length ? (
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={marketDemand?.series ?? []} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="label" tick={{ fontSize: 10, fontWeight: 600, fill: '#9ca3af' }} axisLine={false} tickLine={false} interval={1} />
                  <YAxis allowDecimals={false} tick={{ fontSize: 11, fontWeight: 600, fill: '#9ca3af' }} axisLine={false} tickLine={false} domain={[0, 'auto']} />
                  <Tooltip contentStyle={{ borderRadius: 12, border: 'none', boxShadow: '0 4px 20px rgba(0,0,0,0.1)', fontSize: 12 }} />
                  {/* connectNulls={false} is what makes an uncollected month
                      a break in the line rather than a straight edge drawn
                      through demand nobody measured. */}
                  <Line name="Job postings" type="monotone" dataKey="job_count" connectNulls={false} stroke="#4f46e5" strokeWidth={3} dot={{ fill: '#4f46e5', strokeWidth: 0, r: 4 }} activeDot={{ r: 6 }} />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-52 rounded-xl bg-neutral-50 flex flex-col items-center justify-center text-center px-6">
                <Target size={28} className="text-neutral-300 mb-2" />
                <p className="text-sm font-bold text-neutral-600">No observed demand data yet</p>
                <p className="text-xs text-neutral-400 mt-1">The chart will appear after job listings are collected.</p>
              </div>
            )}

            {marketDemand && (collectedGaps > 0 || marketDemand.month_in_progress) && (
              <p className="text-xs text-neutral-400 mt-3">
                {collectedGaps > 0 && (
                  <>Gaps are months the scraper did not run — not months without demand. </>
                )}
                {marketDemand.month_in_progress && (
                  <>{marketDemand.month_in_progress.label} is still in progress
                    ({marketDemand.month_in_progress.job_count} so far) and is left
                    off the line until it ends.</>
                )}
              </p>
            )}

            {marketDemand && (
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-5">
                <div className="rounded-xl bg-neutral-50 px-4 py-3">
                  <p className="text-[10px] font-black uppercase tracking-wider text-neutral-400">Open postings</p>
                  <p className="text-xl font-black text-neutral-900 mt-1">{marketDemand.total_postings}</p>
                </div>
                {/* Month-on-month, and only when the scraper ran equally
                    often in both months. A figure computed across an uneven
                    collection schedule measures how hard we looked, not what
                    employers advertised -- that is where "+880.9%" came from,
                    and a number nobody can trust is worse than no number. */}
                <div className="rounded-xl bg-neutral-50 px-4 py-3">
                  <p className="text-[10px] font-black uppercase tracking-wider text-neutral-400">
                    Month-on-month
                  </p>
                  {marketDemand.demand_change_percentage === null ? (
                    <p className="text-sm font-bold text-neutral-500 mt-2"
                       title={CHANGE_EXPLAINER[marketDemand.change_basis]}>
                      {CHANGE_LABEL[marketDemand.change_basis]}
                    </p>
                  ) : (
                    <p className={`text-xl font-black mt-1 flex items-center gap-1 ${
                      marketDemand.demand_change_percentage >= 0 ? 'text-success' : 'text-danger'
                    }`}>
                      {marketDemand.demand_change_percentage >= 0 ? (
                        <><ArrowUpRight size={17} />+{marketDemand.demand_change_percentage}%</>
                      ) : (
                        <><TrendingDown size={17} />{marketDemand.demand_change_percentage}%</>
                      )}
                    </p>
                  )}
                </div>
                <div className="rounded-xl bg-neutral-50 px-4 py-3">
                  <p className="text-[10px] font-black uppercase tracking-wider text-neutral-400">Months collected</p>
                  <p className="text-sm font-black text-neutral-900 mt-2">
                    {marketDemand.collected_months} of {marketDemand.period_months}
                  </p>
                </div>
              </div>
            )}

            {marketDemand?.data_quality.is_stale && (
              <div className="mt-4 flex items-start gap-2 rounded-xl bg-amber-50 px-4 py-3 text-amber-800">
                <AlertTriangle size={16} className="shrink-0 mt-0.5" />
                <p className="text-xs font-semibold">
                  {marketDemand.data_quality.freshness_days === null
                    ? 'Market data has not been collected yet.'
                    : `Market data is ${marketDemand.data_quality.freshness_days} days old. Blank recent months mean no recent collection, not zero employer demand.`}
                </p>
              </div>
            )}

            {marketDemand?.mode === 'OVERVIEW' && (
              <div className="mt-5 rounded-xl border border-indigo-100 bg-indigo-50/60 p-4">
                <p className="text-sm font-bold text-neutral-900">Personalize this trend</p>
                {/* A link, not a form. Targets are set in one place only,
                    so the dashboard points there instead of being a second
                    writer. */}
                <p className="text-xs text-neutral-600 mt-1">
                  Choose your Market Role on the Skill Gap page and this trend
                  will follow it.
                </p>
                <Link href="/skill-gap">
                  <Button className="h-10 mt-3">Choose your Market Role</Button>
                </Link>
              </div>
            )}
          </Card>

          {/* Announcements */}
          <Card className="lg:col-span-2 p-6 flex flex-col">
            <div className="flex items-center justify-between mb-5">
              <h3 className="text-lg font-bold text-neutral-900 flex items-center gap-2">
                <Bell size={18} className="text-primary" /> Announcements
              </h3>
            </div>
            <div className="space-y-1 flex-1 overflow-y-auto">
              {announcements.length > 0 ? announcements.map((a) => (
                <button key={a.id} type="button" onClick={() => setSelectedAnnouncement(a)}
                  className="w-full flex items-center justify-between gap-3 px-3 py-3 rounded-xl hover:bg-neutral-50 transition-colors text-left group">
                  <div className="flex items-center gap-2.5 min-w-0">
                    <div className="w-2 h-2 rounded-full bg-primary shrink-0" />
                    <p className="text-sm font-semibold text-neutral-900 truncate group-hover:text-primary transition-colors">
                      {a.title}
                    </p>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    {a.categories?.length > 0 && (
                      <Badge variant="primary" className="text-[9px] hidden sm:inline-flex">{a.categories[0]}</Badge>
                    )}
                    {a.supporting_doc && <Paperclip size={11} className="text-neutral-400" />}
                    <span className="text-[10px] text-neutral-400 font-medium whitespace-nowrap">{timeAgo(a.publish_time)}</span>
                  </div>
                </button>
              )) : (
                <div className="flex flex-col items-center justify-center py-8 text-neutral-300">
                  <Bell size={28} className="mb-2" />
                  <p className="text-xs font-bold text-neutral-400">No announcements</p>
                </div>
              )}
            </div>
          </Card>
        </div>

        {/* Recent applications */}
        <Card className="p-6">
          <div className="flex items-center justify-between mb-5">
            <h3 className="text-lg font-bold text-neutral-900">Recent Applications</h3>
            <Link href="/applications">
              <Button variant="ghost" size="sm" className="text-primary text-xs font-bold">
                View All <ChevronRight size={14} className="ml-1" />
              </Button>
            </Link>
          </div>
          <div className="divide-y divide-neutral-100">
            {recentApplications.length ? recentApplications.map((app) => {
              const normalizedStatus = app.status.toLowerCase();
              return (
                <div key={app.id} className="py-4 flex items-center justify-between">
                  <div>
                    <p className="text-sm font-bold text-neutral-900">{app.job_title}</p>
                    <p className="text-xs font-medium text-neutral-500">{app.company_name}</p>
                  </div>
                  <Badge variant={statusVariants[normalizedStatus] ?? 'neutral'} className="capitalize px-3 py-1 text-[10px] tracking-widest font-black">
                    {normalizedStatus}
                  </Badge>
                </div>
              );
            }) : (
              <div className="py-8 text-center">
                <p className="text-sm font-bold text-neutral-500">No applications yet</p>
                <Link href="/jobs" className="text-xs font-semibold text-primary mt-1 inline-block">Browse available jobs</Link>
              </div>
            )}
          </div>
        </Card>
      </div>

      {/* Announcement detail modal */}
      <AnimatePresence>
        {selectedAnnouncement && (
          <AnnouncementDetailModal
            a={selectedAnnouncement}
            onClose={() => setSelectedAnnouncement(null)}
          />
        )}
      </AnimatePresence>
    </DashboardLayout>
  );
}
