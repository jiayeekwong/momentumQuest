'use client';

import { useState, useEffect, useMemo } from 'react';
import { CheckCircle2, AlertCircle, GraduationCap, ExternalLink, Info } from 'lucide-react';
import { motion } from 'motion/react';
import { DashboardLayout } from '@/src/components/Layout';
import { Card, Badge, Button } from '@/src/components/ui';
import { cn } from '@/src/lib/utils';
import { apiFetch } from '@/src/lib/apiFetch';

interface DemandSkill {
  skill_id: number;
  skill: string;
  category: string;
  demand_count: number;
  demand_percentage: number;
  skill_level?: string;
  priority_level?: 'HIGH' | 'MEDIUM' | 'LOW';
}

interface OwnedSkill {
  skill_id: number;
  skill: string;
  skill_level: string;
}

interface SoftSkill {
  skill_id: number;
  skill: string;
  demand_count: number;
  demand_percentage: number;
  held: boolean;
  skill_level?: string;
}

interface Resource {
  id: number;
  title: string;
  platform: string;
  url: string;
  type: string;
  skill: string;
  skill_priority: 'HIGH' | 'MEDIUM' | 'LOW' | null;
  skill_demand_percentage: number | null;
}

interface ICTRoleOption {
  role_name: string;
  subtracks: string[];
  career_levels: string[];
  listing_count: number;
  // False when the market cannot yet support analysing this role on its own.
  // The role stays selectable regardless; the analysis falls back to its track.
  analysable: boolean;
}

interface ICTRolesResponse {
  evidence_floor: number;
  total_roles: number;
  analysable_roles: number;
  results: { id: number; name: string; slug: string; roles: ICTRoleOption[] }[];
}

interface SkillGap {
  mode: 'TARGET' | 'OVERVIEW';
  scope: 'ROLE' | 'TRACK' | 'OCCUPATION' | 'MARKET';
  target_role: string | null;
  target_occupation: { id: number; code: string; preferred_label: string } | null;
  target_track: { id: number; name: string; slug: string } | null;
  total_listings: number;
  critical_skill_count: number;
  match_percentage: number;
  matched_skills: DemandSkill[];
  missing_skills: DemandSkill[];
  soft_skills: SoftSkill[];
  other_skills: OwnedSkill[];
  recommended_resources: Resource[];
  data_quality: {
    scope_level: 'ROLE' | 'TRACK' | 'OCCUPATION' | 'MARKET';
    target_listing_count: number;
    role_listing_count: number | null;
    market_listing_count: number;
    fell_back_to_track: boolean;
    fell_back_to_market: boolean;
    has_target: boolean;
    evidence_floor: number;
    student_skill_count: number;
  };
}

const PRIORITY_VARIANT: Record<string, 'danger' | 'warning' | 'success'> = {
  HIGH: 'danger', MEDIUM: 'warning', LOW: 'success',
};

const PLATFORM_COLORS: Record<string, string> = {
  'freeCodeCamp':    'bg-green-700',
  'Microsoft Learn': 'bg-sky-700',
  'Cisco NetAcad':   'bg-blue-800',
  'Codecademy':      'bg-teal-700',
  'Coursera':        'bg-violet-700',
};

interface Track {
  id: number;
  name: string;
  slug: string;
  listing_count: number;
  subtrack_count: number;
}

interface TracksResponse {
  min_listings: number;
  results: Track[];
  coverage: {
    classified_listings: number;
    market_listings: number;
    coverage_percentage: number;
  };
}

interface RoadmapRole {
  id: number;
  role_name: string;
  career_level: string;
  progression_order: number;
  is_cross_subtrack: boolean;
}

interface Roadmap {
  track: { id: number; name: string; slug: string };
  source: { publisher: string; framework: string; page: number | null };
  subtracks: { name: string; roles: RoadmapRole[] }[];
}

const LEVEL_COLORS: Record<string, string> = {
  ASSOCIATE: 'bg-sky-100 text-sky-800',
  PROFESSIONAL: 'bg-indigo-100 text-indigo-800',
  SENIOR: 'bg-violet-100 text-violet-800',
  LEAD: 'bg-purple-100 text-purple-800',
  ARCHITECT: 'bg-purple-100 text-purple-800',
  MANAGER: 'bg-amber-100 text-amber-800',
  DIRECTOR: 'bg-orange-100 text-orange-800',
  HEAD: 'bg-orange-100 text-orange-800',
  EXECUTIVE: 'bg-rose-100 text-rose-800',
};

export default function SkillGapPage() {
  const [gap, setGap] = useState<SkillGap | null>(null);
  const [tracks, setTracks] = useState<Track[]>([]);
  const [coverage, setCoverage] = useState<TracksResponse['coverage'] | null>(null);
  const [selectedTrack, setSelectedTrack] = useState<number | ''>('');
  const [roadmap, setRoadmap] = useState<Roadmap | null>(null);
  const [showRoadmap, setShowRoadmap] = useState(false);

  // Role browsing is separate from the saved target, exactly as the track
  // selector already works: choosing a role previews it, "Set as my target"
  // is what persists it.
  const [roleData, setRoleData] = useState<ICTRolesResponse | null>(null);
  const [selectedRole, setSelectedRole] = useState<string>('');
  const [savedRole, setSavedRole] = useState<string | null>(null);
  const [savingTarget, setSavingTarget] = useState(false);
  const [targetMessage, setTargetMessage] = useState<string | null>(null);

  // Rule 5: records the wording only. Never creates a role or a target.
  const [missingOpen, setMissingOpen] = useState(false);
  const [missingText, setMissingText] = useState('');
  const [missingSent, setMissingSent] = useState(false);

  // Loading is derived from whether the data on hand matches the current
  // selection, rather than set synchronously inside the effect (which causes
  // a cascading render).
  const [loadedScope, setLoadedScope] = useState<string | null>(null);
  const scopeKey = selectedRole ? `role:${selectedRole}` : `track:${selectedTrack}`;
  const isLoading = loadedScope !== scopeKey;

  // IMDA career tracks with enough scraped listings to analyse. Tracks rather
  // than MASCO occupations: ~88% of listings carry a track, ~26% an occupation.
  useEffect(() => {
    apiFetch('/api/dashboard/skill-gap/tracks/')
      .then(r => (r.ok ? r.json() : null))
      .then((data: TracksResponse | null) => {
        setTracks(data?.results ?? []);
        setCoverage(data?.coverage ?? null);
        if (data?.results?.length && !selectedTrack) {
          setSelectedTrack(data.results[0].id);
        }
      })
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Every IMDA role, grouped by track. All roles are returned whether or not
  // the market can analyse them -- listing_count and analysable let the page
  // set expectations without removing the option.
  useEffect(() => {
    apiFetch('/api/scrape-jobs/ict-roles/')
      .then(r => (r.ok ? r.json() : null))
      .then((data: ICTRolesResponse | null) => setRoleData(data))
      .catch(() => {});
    apiFetch('/api/auth/profile/')
      .then(r => (r.ok ? r.json() : null))
      .then(data => {
        const saved = data?.target_roles?.[0]?.role_name ?? null;
        setSavedRole(saved);
        if (saved) setSelectedRole(saved);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    // Guards against a slow earlier request overwriting a newer selection.
    let cancelled = false;
    const query = selectedRole
      ? `?role=${encodeURIComponent(selectedRole)}`
      : (selectedTrack ? `?track=${selectedTrack}` : '');
    apiFetch(`/api/dashboard/skill-gap/${query}`)
      .then(r => (r.ok ? r.json() : null))
      .then((data: SkillGap | null) => { if (!cancelled) setGap(data); })
      .catch(() => {})
      .finally(() => { if (!cancelled) setLoadedScope(scopeKey); });
    return () => { cancelled = true; };
  }, [selectedRole, selectedTrack, scopeKey]);

  // The ladder comes from the IMDA hierarchy itself, so it is complete for
  // every track no matter how few job adverts matched an individual role.
  // Stale roadmaps are filtered at render time rather than cleared here.
  useEffect(() => {
    if (!selectedTrack) return;
    let cancelled = false;
    apiFetch(`/api/dashboard/career-roadmap/?track=${selectedTrack}`)
      .then(r => (r.ok ? r.json() : null))
      .then((data: Roadmap | null) => { if (!cancelled) setRoadmap(data); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [selectedTrack]);

  const matchLabel = (value: number) =>
    value >= 70 ? 'STRONG MATCH' : value >= 40 ? 'DEVELOPING' : 'EARLY STAGE';

  const allRoles = useMemo(
    () => (roleData?.results ?? []).flatMap(t => t.roles),
    [roleData]
  );
  const currentRole = allRoles.find(r => r.role_name === selectedRole) ?? null;

  // Rule 9: the heading names the scope that actually answered, never the
  // role the student asked for when the analysis fell back to its track.
  const scopeLabel =
    gap?.scope === 'ROLE' ? gap.target_role
    : gap?.scope === 'TRACK' ? `${gap.target_track?.name ?? 'career track'} track`
    : gap?.scope === 'OCCUPATION' ? gap.target_occupation?.preferred_label
    : 'the whole ICT market';

  const roleLabel = gap?.target_role ?? gap?.target_track?.name ?? 'your target';

  const saveTarget = async () => {
    if (!selectedRole) return;
    setSavingTarget(true);
    setTargetMessage(null);
    try {
      const res = await apiFetch('/api/auth/profile/', {
        method: 'PATCH',
        body: JSON.stringify({ target_roles: [selectedRole] }),
      });
      if (res.ok) {
        setSavedRole(selectedRole);
        setTargetMessage(`${selectedRole} is now your career target.`);
      } else {
        setTargetMessage('Could not save your target. Please try again.');
      }
    } catch {
      setTargetMessage('Could not save your target. Please try again.');
    } finally {
      setSavingTarget(false);
    }
  };

  // Rule 4: saves no role. It only clears the role selection so the student
  // can browse by track instead.
  const exploreByTrack = () => {
    setSelectedRole('');
    setTargetMessage(null);
  };

  const sendMissingTerminology = async () => {
    const text = missingText.trim();
    if (!text) return;
    try {
      await apiFetch('/api/auth/student/role-feedback/', {
        method: 'POST',
        body: JSON.stringify({
          searched_text: text,
          context_track: selectedTrack || null,
        }),
      });
    } catch {
      // Feedback is best-effort; never block the student on it.
    }
    setMissingSent(true);
    setMissingText('');
  };

  return (
    <DashboardLayout title="Skill Gap Analysis">
      <div className="max-w-6xl mx-auto space-y-8">
        <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-6">
          <div>
            <h2 className="text-2xl font-bold text-neutral-900 mb-1">Career Transformation Roadmap</h2>
            <p className="text-neutral-600">
              Identify and bridge the gap between your skills and industry requirements.
            </p>
          </div>

          <div className="w-full lg:w-[26rem] space-y-3">
            <div className="space-y-2">
              <label className="text-xs font-bold text-neutral-400 uppercase tracking-wider block">
                Career Role — IMDA Skills Framework for ICT
              </label>
              {/* Every role is listed, analysable or not. A role the market
                  cannot evidence yet is still a valid thing to aim at; the
                  option carries its job count so the expectation is set here
                  rather than discovered after choosing. */}
              <select
                value={selectedRole}
                onChange={e => { setSelectedRole(e.target.value); setTargetMessage(null); }}
                className="w-full h-11 px-4 bg-white border border-neutral-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
              >
                <option value="">Not sure — explore by track</option>
                {(roleData?.results ?? []).map(track => (
                  <optgroup key={track.id} label={track.name}>
                    {track.roles.map(role => (
                      <option key={`${track.id}-${role.role_name}`} value={role.role_name}>
                        {role.role_name}
                        {role.listing_count > 0 ? ` (${role.listing_count} jobs)` : ' (no jobs yet)'}
                      </option>
                    ))}
                  </optgroup>
                ))}
              </select>

              {selectedRole ? (
                <div className="flex items-center gap-2">
                  <Button
                    size="sm"
                    onClick={saveTarget}
                    disabled={savingTarget || savedRole === selectedRole}
                  >
                    {savedRole === selectedRole
                      ? 'Your career target'
                      : savingTarget ? 'Saving…' : 'Set as my target'}
                  </Button>
                  <Button variant="outline" size="sm" onClick={exploreByTrack}>
                    Explore by track
                  </Button>
                </div>
              ) : (
                <p className="text-xs text-neutral-400">
                  Browsing by track. Pick a role above to see the gap for that career,
                  and to set it as your target.
                </p>
              )}
              {targetMessage && (
                <p className="text-xs font-semibold text-primary">{targetMessage}</p>
              )}
              {currentRole && !currentRole.analysable && (
                <p className="text-xs text-amber-700">
                  {currentRole.listing_count === 0
                    ? 'No scraped listings mention this role yet'
                    : `Only ${currentRole.listing_count} listing(s) mention this role`}
                  {` — fewer than the ${roleData?.evidence_floor ?? 5} needed to analyse it on its own.`}
                  {' You can still target it; the analysis below uses its track.'}
                </p>
              )}
            </div>

            {/* Track selector stays as the browse-by-area path (rule 4). It is
                hidden while a role is chosen, because two competing scopes on
                screen at once is exactly the confusion rule 9 guards against. */}
            {!selectedRole && (
              <div className="space-y-2">
                <label className="text-xs font-bold text-neutral-400 uppercase tracking-wider block">
                  Career Track
                </label>
                <select
                  value={selectedTrack}
                  onChange={e => setSelectedTrack(e.target.value ? Number(e.target.value) : '')}
                  className="w-full h-11 px-4 bg-white border border-neutral-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
                >
                  <option value="">Whole ICT market</option>
                  {tracks.map(track => (
                    <option key={track.id} value={track.id}>
                      {track.name} ({track.listing_count} jobs)
                    </option>
                  ))}
                </select>
                <p className="text-xs text-neutral-400">
                  {tracks.length === 0
                    ? 'No career tracks have enough job data yet.'
                    : `${tracks.length} tracks have enough JobStreet data to analyse.`}
                  {coverage && ` ${coverage.classified_listings} of ${coverage.market_listings} listings classified (${coverage.coverage_percentage}%).`}
                </p>
              </div>
            )}

            {/* Rule 5: records wording only. No role is created, nothing is
                targeted, and no suggestion is returned. */}
            {!missingOpen ? (
              <button
                type="button"
                onClick={() => setMissingOpen(true)}
                className="text-xs font-semibold text-neutral-500 hover:text-primary underline"
              >
                I cannot find my target
              </button>
            ) : missingSent ? (
              <p className="text-xs text-success font-semibold">
                Thank you — we have recorded that wording. It helps us decide which
                careers to cover next.
              </p>
            ) : (
              <div className="space-y-2">
                <input
                  value={missingText}
                  onChange={e => setMissingText(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && (e.preventDefault(), sendMissingTerminology())}
                  placeholder="What role were you looking for?"
                  className="w-full h-10 px-3 bg-white border border-neutral-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
                />
                <div className="flex items-center gap-2">
                  <Button size="sm" onClick={sendMissingTerminology} disabled={!missingText.trim()}>
                    Send
                  </Button>
                  <button
                    type="button"
                    onClick={() => setMissingOpen(false)}
                    className="text-xs text-neutral-400 hover:text-neutral-700"
                  >
                    Cancel
                  </button>
                </div>
                <p className="text-[11px] text-neutral-400">
                  This records the wording only. It does not change your target.
                </p>
              </div>
            )}
          </div>
        </div>

        {isLoading ? (
          <Card className="py-16 text-center text-neutral-500">Analysing your skills…</Card>
        ) : !gap ? (
          <Card className="py-16 text-center text-neutral-500">
            Could not load your skill gap analysis. Please try again.
          </Card>
        ) : (
          <>
            {/* Rule 9: role-level and track-level results are never presented
                as equivalent. This banner is persistent, not dismissible, and
                always names the scope that actually answered rather than the
                role the student asked for. With most roles below the evidence
                floor, the fallback is the common case and has to read as a
                deliberate answer, not a degraded one. */}
            <div className={cn(
              'flex gap-2 text-sm rounded-lg p-4 border',
              gap.scope === 'ROLE'
                ? 'text-emerald-800 bg-emerald-50 border-emerald-100'
                : 'text-amber-800 bg-amber-50 border-amber-100'
            )}>
              <Info size={16} className="shrink-0 mt-0.5" />
              <span>
                {gap.scope === 'ROLE' ? (
                  <>Analysed against <strong>{gap.target_role}</strong> specifically —{' '}
                  {gap.data_quality.role_listing_count} scraped listing(s) for that role.</>
                ) : gap.data_quality.fell_back_to_track ? (
                  <>Only {gap.data_quality.role_listing_count} scraped listing(s) mention{' '}
                  <strong>{gap.target_role}</strong> so far — fewer than the{' '}
                  {gap.data_quality.evidence_floor} needed to analyse a role on its own.
                  These figures cover the <strong>{gap.target_track?.name}</strong> track
                  ({gap.total_listings} listings) instead, which is the closest honest
                  answer for that career.</>
                ) : gap.scope === 'TRACK' ? (
                  <>Analysed against the <strong>{gap.target_track?.name}</strong> track
                  ({gap.total_listings} listings). Pick a role above to narrow this further.</>
                ) : gap.scope === 'OCCUPATION' ? (
                  <>Analysed against <strong>{gap.target_occupation?.preferred_label}</strong>{' '}
                  ({gap.total_listings} listings).</>
                ) : gap.data_quality.has_target ? (
                  <>Neither <strong>{roleLabel}</strong> nor its career track has enough
                  scraped listings to analyse yet, so these figures cover the whole ICT
                  market ({gap.total_listings} listings).</>
                ) : (
                  <>No career role selected, so this compares your skills against the whole
                  scraped ICT market ({gap.total_listings} listings). Pick a role above for
                  a sharper analysis.</>
                )}
              </span>
            </div>

            {/* Heading names the scope that actually answered (rule 9). */}
            <p className="text-xs font-black text-neutral-400 uppercase tracking-widest">
              Showing: {scopeLabel}
            </p>

            {/* Match summary */}
            <Card className="bg-indigo-600 border-none p-8 text-white relative overflow-hidden">
              <div className="relative z-10 flex flex-col md:flex-row items-center gap-10">
                <div className="w-48 h-48 relative flex items-center justify-center shrink-0">
                  <svg className="w-full h-full transform -rotate-90">
                    <circle cx="96" cy="96" r="80" stroke="currentColor" strokeWidth="12" fill="transparent" className="text-white/20" />
                    <circle
                      cx="96" cy="96" r="80" stroke="currentColor" strokeWidth="12" fill="transparent"
                      strokeDasharray="502.4"
                      strokeDashoffset={502.4 * (1 - gap.match_percentage / 100)}
                      strokeLinecap="round" className="text-white"
                    />
                  </svg>
                  <div className="absolute text-center">
                    <span className="text-4xl font-black block">{gap.match_percentage}%</span>
                    <span className="text-xs font-medium uppercase tracking-widest text-indigo-100">Match</span>
                  </div>
                </div>
                <div className="flex-1 space-y-4">
                  <Badge variant="secondary" className="bg-white/20 text-white border-none">
                    {matchLabel(gap.match_percentage)}
                  </Badge>
                  <h3 className="text-3xl font-bold">
                    {gap.mode === 'TARGET'
                      ? `Progress towards ${roleLabel}`
                      : 'Your standing in the current job market'}
                  </h3>
                  <p className="text-indigo-50 text-lg">
                    You have {gap.matched_skills.length} of {gap.critical_skill_count} most-demanded
                    skills, measured across {gap.total_listings} job listings.
                  </p>
                  <div className="flex flex-wrap gap-4 pt-2">
                    <div className="flex items-center gap-2 px-4 py-2 bg-white/10 rounded-lg">
                      <CheckCircle2 size={20} className="text-emerald-300" />
                      <span className="text-sm font-semibold">{gap.matched_skills.length} Skills Matched</span>
                    </div>
                    <div className="flex items-center gap-2 px-4 py-2 bg-white/10 rounded-lg">
                      <AlertCircle size={20} className="text-amber-300" />
                      <span className="text-sm font-semibold">{gap.missing_skills.length} Skills Missing</span>
                    </div>
                  </div>
                </div>
              </div>
              <div className="absolute top-0 right-0 w-96 h-96 bg-white/5 rounded-full -mr-32 -mt-32 blur-3xl" />
            </Card>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
              {/* Skills the student has */}
              <section>
                <div className="flex items-center gap-2 mb-4">
                  <CheckCircle2 className="text-success" size={20} />
                  <h4 className="text-lg font-bold text-neutral-900">Your Skills</h4>
                </div>
                <Card className="p-4 bg-neutral-50/50">
                  {gap.matched_skills.length === 0 && gap.other_skills.length === 0 ? (
                    <p className="text-sm text-neutral-500 py-4 text-center">
                      No skills recorded yet. Upload your exam results under Skill Validation
                      to build your profile automatically.
                    </p>
                  ) : (
                    <div className="space-y-4">
                      {gap.matched_skills.length > 0 && (
                        <div>
                          <p className="text-[10px] font-black text-neutral-400 uppercase tracking-widest mb-2">
                            In demand for this role
                          </p>
                          <div className="flex flex-wrap gap-2">
                            {gap.matched_skills.map(skill => (
                              <Badge key={skill.skill_id} variant="success" className="bg-white px-3 py-1.5 flex items-center gap-1.5">
                                <CheckCircle2 size={14} /> {skill.skill} · {skill.skill_level}
                              </Badge>
                            ))}
                          </div>
                        </div>
                      )}
                      {gap.other_skills.length > 0 && (
                        <div>
                          <p className="text-[10px] font-black text-neutral-400 uppercase tracking-widest mb-2">
                            Your other skills
                          </p>
                          <div className="flex flex-wrap gap-2">
                            {gap.other_skills.map(skill => (
                              <Badge key={skill.skill_id} variant="neutral" className="bg-white px-3 py-1.5">
                                {skill.skill} · {skill.skill_level}
                              </Badge>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </Card>
              </section>

              {/* Missing skills */}
              <section>
                <div className="flex items-center gap-2 mb-4">
                  <AlertCircle className="text-danger" size={20} />
                  <h4 className="text-lg font-bold text-neutral-900">Missing Core Skills</h4>
                </div>
                <div className="space-y-4">
                  {gap.missing_skills.length === 0 ? (
                    <Card className="p-6 text-center text-sm text-neutral-500">
                      You already hold every top-demanded skill in this scope.
                    </Card>
                  ) : (
                    gap.missing_skills.map((gapSkill, i) => (
                      <Card key={gapSkill.skill_id} className="p-4 group hover:border-primary/50 transition-colors">
                        <div className="flex items-start justify-between mb-3">
                          <div>
                            <h5 className="font-bold text-neutral-900">{gapSkill.skill}</h5>
                            <span className="text-[10px] font-bold text-neutral-400 uppercase tracking-widest">
                              Industry Demand
                            </span>
                          </div>
                          <Badge variant={PRIORITY_VARIANT[gapSkill.priority_level ?? 'LOW']}>
                            {gapSkill.priority_level}
                          </Badge>
                        </div>
                        <div className="relative w-full h-1.5 bg-neutral-100 rounded-full overflow-hidden">
                          <motion.div
                            initial={{ width: 0 }}
                            animate={{ width: `${gapSkill.demand_percentage}%` }}
                            transition={{ delay: 0.2 + i * 0.05, duration: 0.8 }}
                            className={cn('absolute top-0 left-0 h-full rounded-full',
                              gapSkill.priority_level === 'HIGH' ? 'bg-danger'
                                : gapSkill.priority_level === 'MEDIUM' ? 'bg-warning' : 'bg-success'
                            )}
                          />
                        </div>
                        <div className="mt-4 flex items-center justify-between">
                          <span className="text-xs font-semibold text-neutral-600">
                            {gapSkill.demand_percentage}% of listings ({gapSkill.demand_count} jobs)
                          </span>
                        </div>
                      </Card>
                    ))
                  )}
                </div>
              </section>
            </div>

            {/* Soft skills — ranked separately so they cannot drown the technical gap */}
            {gap.soft_skills.length > 0 && (
              <section>
                <div className="flex items-center gap-2 mb-3">
                  <h4 className="text-lg font-bold text-neutral-900">
                    Soft Skills Employers Ask For
                  </h4>
                </div>
                <Card className="p-5">
                  <p className="text-xs text-neutral-500 mb-4">
                    Listed separately from technical gaps — these appear across
                    almost every advert, so they rank on their own rather than
                    crowding out the skills you can study for.
                  </p>
                  <div className="space-y-2">
                    {gap.soft_skills.map(skill => (
                      <div key={skill.skill_id} className="flex items-center gap-3">
                        {skill.held
                          ? <CheckCircle2 size={15} className="text-success shrink-0" />
                          : <AlertCircle size={15} className="text-neutral-300 shrink-0" />}
                        <span className={cn(
                          'text-sm w-44 shrink-0',
                          skill.held ? 'font-semibold text-neutral-900' : 'text-neutral-600'
                        )}>
                          {skill.skill}
                        </span>
                        <div className="flex-1 h-1.5 bg-neutral-100 rounded-full overflow-hidden">
                          <div
                            className={cn('h-full rounded-full',
                              skill.held ? 'bg-success' : 'bg-neutral-300')}
                            style={{ width: `${skill.demand_percentage}%` }}
                          />
                        </div>
                        <span className="text-xs text-neutral-500 w-28 text-right shrink-0">
                          {skill.demand_percentage}% of adverts
                        </span>
                      </div>
                    ))}
                  </div>
                </Card>
              </section>
            )}

            {/* Career ladder — read straight from the IMDA hierarchy */}
            {roadmap && roadmap.track.id === selectedTrack && (
              <section>
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
                  <div>
                    <h4 className="text-xl font-bold text-neutral-900">
                      Career Roadmap — {roadmap.track.name}
                    </h4>
                    <p className="text-xs text-neutral-400 font-medium mt-0.5">
                      {roadmap.source.framework}, {roadmap.source.publisher}
                      {roadmap.source.page ? ` (p.${roadmap.source.page})` : ''}
                    </p>
                  </div>
                  <Button variant="outline" size="sm" onClick={() => setShowRoadmap(v => !v)}>
                    {showRoadmap ? 'Hide' : 'Show'} {roadmap.subtracks.length} sub-tracks
                  </Button>
                </div>

                {showRoadmap && (
                  <div className="space-y-4">
                    {roadmap.subtracks.map(subtrack => (
                      <Card key={subtrack.name} className="p-5">
                        <h5 className="font-bold text-neutral-900 mb-3">{subtrack.name}</h5>
                        <div className="flex flex-wrap items-center gap-2">
                          {subtrack.roles.map((role, index) => (
                            <div key={role.id} className="flex items-center gap-2">
                              {index > 0 && <span className="text-neutral-300">→</span>}
                              <div className={cn(
                                'px-3 py-2 rounded-lg border border-neutral-100',
                                role.is_cross_subtrack ? 'bg-neutral-50' : 'bg-white'
                              )}>
                                <p className="text-sm font-semibold text-neutral-900">
                                  {role.role_name}
                                </p>
                                <span className={cn(
                                  'inline-block mt-1 px-2 py-0.5 rounded text-[10px] font-bold tracking-wide',
                                  LEVEL_COLORS[role.career_level] ?? 'bg-neutral-100 text-neutral-600'
                                )}>
                                  {role.career_level}
                                </span>
                              </div>
                            </div>
                          ))}
                        </div>
                      </Card>
                    ))}
                  </div>
                )}
              </section>
            )}

            {/* Recommended learning */}
            <section>
              <div className="flex items-center gap-2 mb-6">
                <GraduationCap className="text-primary" size={24} />
                <div>
                  <h4 className="text-xl font-bold text-neutral-900">Recommended Learning Paths</h4>
                  <p className="text-xs text-neutral-500">
                    Ordered by how much the market is asking for each missing skill.
                  </p>
                </div>
              </div>
              {gap.recommended_resources.length === 0 ? (
                <Card className="p-6 text-center text-sm text-neutral-500">
                  No learning resources are available for your missing skills yet.
                </Card>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                  {gap.recommended_resources.map(resource => (
                    <Card key={resource.id} className="p-0 overflow-hidden flex flex-col group hover:shadow-lg transition-all duration-300">
                      <div className={cn(
                        'h-32 flex items-center justify-center p-6 text-white relative',
                        PLATFORM_COLORS[resource.platform] ?? 'bg-neutral-700'
                      )}>
                        <h5 className="text-base font-black text-center">{resource.title}</h5>
                      </div>
                      <div className="p-5 flex-1 flex flex-col">
                        <div className="flex items-center justify-between mb-2">
                          <span className="text-[10px] font-black text-neutral-400 uppercase tracking-widest">
                            {resource.platform}
                          </span>
                          <Badge variant="primary">{resource.type}</Badge>
                        </div>
                        <p className="text-xs text-neutral-500 mb-1">Builds: {resource.skill}</p>
                        {resource.skill_priority && (
                          <p className="text-[11px] text-neutral-400 mb-4">
                            <span className={cn(
                              'font-black uppercase tracking-wider',
                              resource.skill_priority === 'HIGH' ? 'text-danger'
                                : resource.skill_priority === 'MEDIUM' ? 'text-warning'
                                : 'text-neutral-400'
                            )}>
                              {resource.skill_priority} priority
                            </span>
                            {resource.skill_demand_percentage !== null &&
                              ` · asked for in ${resource.skill_demand_percentage}% of listings`}
                          </p>
                        )}
                        <a href={resource.url} target="_blank" rel="noopener noreferrer" className="mt-auto">
                          <Button fullWidth>
                            <ExternalLink size={14} /> Open Resource
                          </Button>
                        </a>
                      </div>
                    </Card>
                  ))}
                </div>
              )}
            </section>
          </>
        )}
      </div>
    </DashboardLayout>
  );
}
