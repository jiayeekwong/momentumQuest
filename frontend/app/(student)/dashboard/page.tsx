'use client';

import { useAuth } from '@/src/context/AuthContext';
import { DashboardLayout } from '@/src/components/Layout';
import { Card, Badge, Button } from '@/src/components/ui';
import { Briefcase, Target, Star, Bell, ChevronRight, Sparkles, ArrowUpRight, X, FileText, ExternalLink, Paperclip, AlertTriangle, TrendingDown } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';
import { motion, AnimatePresence } from 'motion/react';
import Link from 'next/link';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { apiFetch } from '@/src/lib/apiFetch';

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

interface RankedOccupation {
  id: number;
  code: string;
  preferred_label: string;
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
  target_occupation: {
    id: number;
    code: string;
    preferred_label: string;
    version: string;
  } | null;
  series: DemandPoint[];
  total_postings: number;
  three_month_change_percentage: number | null;
  top_occupations: RankedOccupation[];
  top_categories: RankedCategory[];
  data_quality: {
    first_observed_date: string | null;
    latest_observed_date: string | null;
    freshness_days: number | null;
    is_stale: boolean;
    market_postings_in_period: number;
    standardized_postings_in_period: number;
    standardization_coverage_percentage: number;
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
          <div
            className="text-sm text-neutral-700 leading-relaxed announcement-body"
            dangerouslySetInnerHTML={{ __html: a.message }}
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
  // Browsing an occupation's trend is separate from committing to it as a
  // target — the student can flip between roles as often as they like.
  const [trendOccupationId,    setTrendOccupationId]    = useState<number | ''>('');
  const [ictOccupations,       setIctOccupations]       = useState<{ id: number; code: string; preferred_label: string; listing_count: number }[]>([]);
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

  // Only occupations with standardized listings behind them — anything else
  // renders an empty chart.
  useEffect(() => {
    apiFetch('/api/dashboard/skill-gap/occupations/')
      .then(r => (r.ok ? r.json() : null))
      .then((data) => setIctOccupations(data?.results ?? []))
      .catch(() => {});
  }, []);

  // Re-scope only the chart when the student browses another occupation.
  const loadTrend = useCallback(async (occupationId: number | '') => {
    setTrendLoading(true);
    try {
      const query = occupationId ? `?occupation=${occupationId}` : '';
      const response = await apiFetch(`/api/dashboard/market-demand/${query}`);
      if (response.ok) setMarketDemand(await response.json() as MarketDemand);
    } catch {
      // leave the previous chart in place
    } finally {
      setTrendLoading(false);
    }
  }, []);

  const rankedItems = useMemo(() => {
    if (!marketDemand) return [];
    if (marketDemand.top_occupations.length) {
      return marketDemand.top_occupations.map((occupation) => ({
        id: occupation.id,
        label: occupation.preferred_label,
        code: occupation.code,
        jobCount: occupation.job_count,
        occupationId: occupation.id,
      }));
    }
    return marketDemand.top_categories.map((category) => ({
      id: category.id,
      label: category.category_name,
      code: 'Category',
      jobCount: category.job_count,
      occupationId: null,
    }));
  }, [marketDemand]);

  const maxRankedCount = Math.max(...rankedItems.map((item) => item.jobCount), 1);
  const observedPoints = marketDemand?.series.filter((point) => point.observed) ?? [];

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
            { label: marketDemand?.mode === 'TARGET' ? 'Target Job Postings' : 'Market Job Postings', value: marketDemand ? String(marketDemand.total_postings) : '—', icon: Target, color: 'bg-emerald-50 text-success', trend: `within the ${marketDemand?.period_months ?? 12}-month view` },
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
                {marketDemand?.mode === 'TARGET' ? 'YOUR MASCO TARGET' : 'MARKET OVERVIEW'}
              </Badge>
            </div>

            {/* Browse any ICT occupation's trend — does not change your saved target */}
            <div className="flex flex-col sm:flex-row sm:items-center gap-2 mb-5">
              <select
                value={trendOccupationId}
                onChange={(e) => {
                  const value = e.target.value ? Number(e.target.value) : '';
                  setTrendOccupationId(value);
                  void loadTrend(value);
                }}
                className="h-10 flex-1 rounded-lg border border-neutral-300 bg-white px-3 text-sm text-neutral-800 focus:outline-none focus:ring-2 focus:ring-primary/20"
              >
                <option value="">
                  {user?.targetOccupations?.length ? 'My target role' : 'Whole market'}
                </option>
                {ictOccupations.map((occupation) => (
                  <option key={occupation.id} value={occupation.id}>
                    {occupation.code} — {occupation.preferred_label} ({occupation.listing_count} jobs)
                  </option>
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
            ) : observedPoints.length ? (
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={marketDemand?.series ?? []} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="label" tick={{ fontSize: 10, fontWeight: 600, fill: '#9ca3af' }} axisLine={false} tickLine={false} interval={1} />
                  <YAxis allowDecimals={false} tick={{ fontSize: 11, fontWeight: 600, fill: '#9ca3af' }} axisLine={false} tickLine={false} domain={[0, 'auto']} />
                  <Tooltip contentStyle={{ borderRadius: 12, border: 'none', boxShadow: '0 4px 20px rgba(0,0,0,0.1)', fontSize: 12 }} />
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

            {marketDemand && (
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-5">
                <div className="rounded-xl bg-neutral-50 px-4 py-3">
                  <p className="text-[10px] font-black uppercase tracking-wider text-neutral-400">Postings shown</p>
                  <p className="text-xl font-black text-neutral-900 mt-1">{marketDemand.total_postings}</p>
                </div>
                <div className="rounded-xl bg-neutral-50 px-4 py-3">
                  <p className="text-[10px] font-black uppercase tracking-wider text-neutral-400">3-month change</p>
                  <p className={`text-xl font-black mt-1 flex items-center gap-1 ${
                    marketDemand.three_month_change_percentage === null
                      ? 'text-neutral-500'
                      : marketDemand.three_month_change_percentage >= 0
                        ? 'text-success'
                        : 'text-danger'
                  }`}>
                    {marketDemand.three_month_change_percentage === null ? (
                      'Not enough history'
                    ) : marketDemand.three_month_change_percentage >= 0 ? (
                      <><ArrowUpRight size={17} />{marketDemand.three_month_change_percentage}%</>
                    ) : (
                      <><TrendingDown size={17} />{marketDemand.three_month_change_percentage}%</>
                    )}
                  </p>
                </div>
                <div className="rounded-xl bg-neutral-50 px-4 py-3">
                  <p className="text-[10px] font-black uppercase tracking-wider text-neutral-400">Latest observed</p>
                  <p className="text-sm font-black text-neutral-900 mt-2">
                    {marketDemand.data_quality.latest_observed_date ?? 'No data'}
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
                {/* A link, not a form. This block used to PATCH
                    target_occupation_ids, which the profile endpoint no longer
                    accepts -- it returned 200 and changed nothing. Targets are
                    now set in one place only, so the dashboard points there
                    instead of being a second writer. */}
                <p className="text-xs text-neutral-600 mt-1">
                  Choose your IMDA career role on the Skill Gap page and this trend
                  will follow it.
                </p>
                <Link href="/skill-gap">
                  <Button className="h-10 mt-3">Choose your career role</Button>
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

        {/* Market ranking */}
        <Card className="p-6">
          <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3 mb-5">
            <div>
              <h3 className="text-lg font-bold text-neutral-900">
                {marketDemand?.top_occupations.length ? 'Top MASCO Occupations in Demand' : 'Top Job Categories in Demand'}
              </h3>
              <p className="text-xs text-neutral-400 font-medium mt-0.5">
                {marketDemand?.top_occupations.length
                  ? 'Standardized occupations ranked by postings in the current chart period'
                  : 'Category overview shown until MASCO standardization data is available'}
              </p>
            </div>
            {marketDemand && (
              <span className="text-[10px] font-bold text-neutral-400 uppercase tracking-wider">
                MASCO coverage {marketDemand.data_quality.standardization_coverage_percentage}%
              </span>
            )}
          </div>

          {rankedItems.length ? (
            <div className="space-y-4">
              {rankedItems.map((item) => (
                <div key={`${item.code}-${item.id}`} className="flex items-center gap-4">
                  <div className="w-36 sm:w-64 min-w-0">
                    <p className="text-sm font-bold text-neutral-900 truncate">{item.label}</p>
                    <p className="text-[10px] font-semibold text-neutral-400 truncate">{item.code}</p>
                  </div>
                  <div className="flex-1 h-2.5 rounded-full bg-neutral-100 overflow-hidden">
                    <div
                      className="h-full rounded-full bg-primary"
                      style={{ width: `${Math.max(item.jobCount / maxRankedCount * 100, 3)}%` }}
                    />
                  </div>
                  <span className="w-12 text-right text-sm font-black text-neutral-800">{item.jobCount}</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="rounded-xl bg-neutral-50 py-8 text-center">
              <p className="text-sm font-bold text-neutral-500">No market ranking data available</p>
            </div>
          )}
        </Card>

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
