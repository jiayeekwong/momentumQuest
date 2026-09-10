'use client';

import { useState, useEffect, useMemo } from 'react';
import { CheckCircle2, AlertCircle, GraduationCap, ExternalLink, Info } from 'lucide-react';
import { motion } from 'motion/react';
import { DashboardLayout } from '@/src/components/Layout';
import { Card, Badge, Button } from '@/src/components/ui';
import { cn } from '@/src/lib/utils';
import { apiFetch } from '@/src/lib/apiFetch';

type ProficiencyLevel = 'BEGINNER' | 'INTERMEDIATE' | 'ADVANCED';

const LEVEL_LABEL: Record<ProficiencyLevel, string> = {
  BEGINNER: 'Beginner',
  INTERMEDIATE: 'Intermediate',
  ADVANCED: 'Advanced',
};

interface DemandSkill {
  skill_id: number;
  skill: string;
  category: string;
  demand_count: number;
  demand_percentage: number;
  skill_level?: string;
  priority_level?: 'HIGH' | 'MEDIUM' | 'LOW';
  // Holding a skill is not the same as being ready for it. The level the
  // market asks for, the level the student holds, and the verdict comparing
  // them -- reporting only "you have it" hid every partial gap.
  required_level: ProficiencyLevel;
  student_level: ProficiencyLevel | null;
  readiness_status: 'MATCHED' | 'DEVELOPING' | 'MISSING';
  // How the adverts in scope actually split, so the required level can be
  // checked rather than taken on trust.
  level_distribution: Partial<Record<ProficiencyLevel, number>>;
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
  // Absent when the provider never stated a price. Absent is not "paid": the
  // field is left out of the card entirely rather than guessed at.
  is_free?: boolean;
}

interface SkillResourceGroup {
  skill_id: number;
  skill: string;
  skill_priority: 'HIGH' | 'MEDIUM' | 'LOW' | null;
  skill_demand_percentage: number | null;
  // How many exist for this skill in total; the page shows a handful and
  // offers the rest behind "View more".
  total: number;
  resources: Resource[];
}

interface MarketRoleOption {
  id: number;
  name: string;
  broad_area: string;
  description: string;
  advert_count: number;
  // False when the market cannot yet support analysing this role on its own.
  // The role stays selectable regardless; the analysis widens to its area.
  analysable: boolean;
}

interface MarketRolesResponse {
  evidence_floor: number;
  total_roles: number;
  analysable_roles: number;
  results: { name: string; roles: MarketRoleOption[] }[];
}

interface SkillGap {
  mode: 'TARGET' | 'OVERVIEW';
  scope: 'ROLE' | 'BROAD_AREA' | 'MARKET';
  target_role: string | null;
  target_broad_area: string | null;
  total_listings: number;
  critical_skill_count: number;
  match_percentage: number;
  matched_skills: DemandSkill[];
  missing_skills: DemandSkill[];
  soft_skills: SoftSkill[];
  other_skills: OwnedSkill[];
  resources_by_skill: SkillResourceGroup[];
  data_quality: {
    scope_level: 'ROLE' | 'BROAD_AREA' | 'MARKET';
    target_listing_count: number;
    role_listing_count: number | null;
    market_listing_count: number;
    fell_back_to_broad_area: boolean;
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
  'edX':             'bg-red-800',
};

interface ScopeArea {
  name: string;
  listing_count: number;
  roles: { id: number; name: string; listing_count: number }[];
}

interface ScopeResponse {
  evidence_floor: number;
  results: ScopeArea[];
  coverage: {
    scraped_total: number;
    classified_total: number;
    classified_percentage: number;
  };
}

interface RoleProfile {
  role: { id: number; name: string; broad_area: string; description: string };
  listing_count: number;
  analysable: boolean;
  evidence_floor: number;
  career_levels: { career_level: string; listing_count: number }[];
  // How this role's adverts were classified, so the evidence behind the
  // numbers can be judged rather than assumed.
  classification_methods: { classification_method: string; listing_count: number }[];
  reviewed_titles: string[];
}

const LEVEL_COLORS: Record<string, string> = {
  INTERN: 'bg-sky-100 text-sky-800',
  GRADUATE: 'bg-teal-100 text-teal-800',
  JUNIOR: 'bg-emerald-100 text-emerald-800',
  ASSOCIATE: 'bg-indigo-100 text-indigo-800',
  MID: 'bg-violet-100 text-violet-800',
  SENIOR: 'bg-amber-100 text-amber-800',
};

const METHOD_LABELS: Record<string, string> = {
  EXACT_MARKET_ROLE: 'Title is the Market Role',
  REVIEWED_TITLE_ALIAS: 'Reviewed title alias',
  CAREER_LEVEL_NORMALIZED_ROLE: 'Market Role after career level removed',
  CAREER_LEVEL_NORMALIZED_ALIAS: 'Reviewed alias after career level removed',
  REVIEWED_SEGMENT_MATCH: 'Reviewed segment of a compound title',
  JD_RESOLVED: 'Resolved from advert responsibilities',
  HUMAN_REVIEW: 'Set by a reviewer',
};

export default function SkillGapPage() {
  const [gap, setGap] = useState<SkillGap | null>(null);
  const [areas, setAreas] = useState<ScopeArea[]>([]);
  const [coverage, setCoverage] = useState<ScopeResponse['coverage'] | null>(null);
  const [selectedArea, setSelectedArea] = useState<string>('');
  const [profile, setProfile] = useState<RoleProfile | null>(null);
  const [showEvidence, setShowEvidence] = useState(false);

  // Role browsing is separate from the saved target: choosing a Market Role
  // previews it, "Set as my target" is what persists it.
  const [roleData, setRoleData] = useState<MarketRolesResponse | null>(null);
  const [selectedRole, setSelectedRole] = useState<string>('');
  const [savedRole, setSavedRole] = useState<string | null>(null);
  const [savingTarget, setSavingTarget] = useState(false);
  const [targetMessage, setTargetMessage] = useState<string | null>(null);

  // Records the wording only. Never creates a role or a target.
  const [missingOpen, setMissingOpen] = useState(false);
  const [missingText, setMissingText] = useState('');
  const [missingSent, setMissingSent] = useState(false);
  // Skills whose full resource list has been fetched, keyed by skill id. The
  // page ships a handful per skill so it stays readable; the rest arrive only
  // if a student asks, rather than sending 371 Python courses to everyone.
  const [expandedSkills, setExpandedSkills] =
    useState<Record<number, Resource[]>>({});
  const [loadingSkillId, setLoadingSkillId] = useState<number | null>(null);

  const loadAllResources = async (skillId: number) => {
    setLoadingSkillId(skillId);
    try {
      const res = await apiFetch(
        `/api/dashboard/skill-resources/?skill=${skillId}`);
      if (res.ok) {
        const data = await res.json();
        setExpandedSkills(prev => ({ ...prev, [skillId]: data.resources }));
      }
    } catch {
      // Leaving the short list in place is the honest failure: the student
      // still has the resources the page already showed them.
    } finally {
      setLoadingSkillId(null);
    }
  };

  // Loading is derived from whether the data on hand matches the current
  // selection, rather than set synchronously inside the effect (which causes
  // a cascading render).
  const [loadedScope, setLoadedScope] = useState<string | null>(null);
  const scopeKey = selectedRole ? `role:${selectedRole}` : `area:${selectedArea}`;
  const isLoading = loadedScope !== scopeKey;

  // The Market Roles the analysis can actually answer for, grouped by Broad
  // Area. Broad Area is presentation only -- it groups the list and widens a
  // thin measurement; it never decides which role an advert belongs to.
  useEffect(() => {
    apiFetch('/api/dashboard/skill-gap/market-roles/')
      .then(r => (r.ok ? r.json() : null))
      .then((data: ScopeResponse | null) => {
        setAreas(data?.results ?? []);
        setCoverage(data?.coverage ?? null);
      })
      .catch(() => {});
  }, []);

  // Every Market Role, grouped by Broad Area. All roles are returned whether
  // or not the market can analyse them -- advert_count and analysable let the
  // page set expectations without removing the option.
  useEffect(() => {
    apiFetch('/api/scrape-jobs/market-roles/')
      .then(r => (r.ok ? r.json() : null))
      .then((data: MarketRolesResponse | null) => setRoleData(data))
      .catch(() => {});
    apiFetch('/api/auth/profile/')
      .then(r => (r.ok ? r.json() : null))
      .then(data => {
        const saved = data?.target_roles?.[0]?.market_role ?? null;
        setSavedRole(saved);
        if (saved) setSelectedRole(saved);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    // Guards against a slow earlier request overwriting a newer selection.
    let cancelled = false;
    // An empty query used to mean "no role and no area", which the server
    // read as "use my saved target" -- so choosing "Not sure" answered with
    // the role the student had just stepped away from. scope=market says the
    // whole market is the actual request.
    const query = selectedRole
      ? `?role=${encodeURIComponent(selectedRole)}`
      : (selectedArea
        ? `?broad_area=${encodeURIComponent(selectedArea)}`
        : '?scope=market');
    apiFetch(`/api/dashboard/skill-gap/${query}`)
      .then(r => (r.ok ? r.json() : null))
      .then((data: SkillGap | null) => { if (!cancelled) setGap(data); })
      // A thrown request used to be swallowed while the scope was still
      // marked loaded, which left the previous role's analysis on screen
      // under the newly chosen one. Clearing it shows the error card instead
      // of attributing one career's skills to another.
      .catch(() => { if (!cancelled) setGap(null); })
      .finally(() => { if (!cancelled) setLoadedScope(scopeKey); });
    return () => { cancelled = true; };
  }, [selectedRole, selectedArea, scopeKey]);

  // What the market says about the selected role: how many adverts it rests
  // on, at which career levels, and how each was classified. There is no
  // progression ladder, deliberately -- the scraped adverts make no claim
  // about career structure, only about what is currently advertised.
  useEffect(() => {
    // No clearing here. The panel below already renders only when the loaded
    // profile belongs to the current selection, so a stale one is invisible
    // rather than wrong -- and clearing it synchronously inside the effect was
    // a cascading render for no visible gain.
    if (!selectedRole) return;
    let cancelled = false;
    apiFetch(`/api/dashboard/market-role/?role=${encodeURIComponent(selectedRole)}`)
      .then(r => (r.ok ? r.json() : null))
      .then((data: RoleProfile | null) => { if (!cancelled) setProfile(data); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [selectedRole]);

  const matchLabel = (value: number) =>
    value >= 70 ? 'STRONG MATCH' : value >= 40 ? 'DEVELOPING' : 'EARLY STAGE';

  const allRoles = useMemo(
    () => (roleData?.results ?? []).flatMap(area => area.roles),
    [roleData]
  );
  const currentRole = allRoles.find(r => r.name === selectedRole) ?? null;

  // The heading names the scope that actually answered, never the role the
  // student asked for when the analysis had to widen.
  const scopeLabel =
    gap?.scope === 'ROLE' ? gap.target_role
    : gap?.scope === 'BROAD_AREA' ? gap.target_broad_area
    : 'the whole ICT market';

  const roleLabel = gap?.target_role ?? gap?.target_broad_area ?? 'your target';

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
        // The server's own reason where it gave one. A rejected Market Role
        // name and an expired session both used to print the same sentence,
        // which said only that something went wrong and never what.
        const detail = await res.json().catch(() => null);
        const reason =
          detail?.target_roles?.[0] ?? detail?.detail ?? `the server answered ${res.status}`;
        setTargetMessage(`Could not save your target — ${reason}`);
      }
    } catch {
      // Thrown rather than refused: the request never reached the server.
      setTargetMessage('Could not save your target — the server could not be reached.');
    } finally {
      setSavingTarget(false);
    }
  };

  // Saves no role. It only clears the role selection so the student can
  // browse by career area instead.
  const exploreByArea = () => {
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
          context_broad_area: selectedArea || null,
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
            <h2 className="text-2xl font-bold text-neutral-900 mb-1">Career Transformation Plan</h2>
            <p className="text-neutral-600">
              Identify and bridge the gap between your skills and industry requirements.
            </p>
          </div>

          <div className="w-full lg:w-[26rem] space-y-3">
            <div className="space-y-2">
              <label className="text-xs font-bold text-neutral-400 uppercase tracking-wider block">
                Market Role — grouped from Malaysian ICT job adverts
              </label>
              {/* Market Roles only. A raw advert title ("Senior Front-End
                  Engineer (Remote)") and its normalized form ("frontend
                  engineer") are matching evidence, never career options.

                  Every role is listed, analysable or not: one the market
                  cannot evidence yet is still a valid thing to aim at, and
                  the option carries its advert count so the expectation is
                  set here rather than discovered after choosing. */}
              <select
                value={selectedRole}
                onChange={e => { setSelectedRole(e.target.value); setTargetMessage(null); }}
                className="w-full h-11 px-4 bg-white border border-neutral-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
              >
                <option value="">Not sure — explore by career area</option>
                {(roleData?.results ?? []).map(area => (
                  <optgroup key={area.name} label={area.name}>
                    {area.roles.map(role => (
                      <option key={role.id} value={role.name}>
                        {role.name}
                        {role.advert_count > 0 ? ` (${role.advert_count} jobs)` : ' (no jobs yet)'}
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
                  <Button variant="outline" size="sm" onClick={exploreByArea}>
                    Explore by career area
                  </Button>
                </div>
              ) : (
                <p className="text-xs text-neutral-400">
                  Browsing by career area. Pick a Market Role above to see the gap for
                  that career, and to set it as your target.
                </p>
              )}
              {targetMessage && (
                <p className="text-xs font-semibold text-primary">{targetMessage}</p>
              )}
              {currentRole && !currentRole.analysable && (
                <p className="text-xs text-amber-700">
                  {currentRole.advert_count === 0
                    ? 'No scraped adverts have been classified into this role yet'
                    : `Only ${currentRole.advert_count} advert(s) classified into this role`}
                  {` — fewer than the ${roleData?.evidence_floor ?? 5} needed to analyse it on its own.`}
                  {' You can still target it; the analysis below uses its career area.'}
                </p>
              )}
            </div>

            {/* The career-area selector is the browse path. It is hidden while
                a role is chosen, because two competing scopes on screen at
                once is exactly the confusion the scope label guards against.

                Broad Area groups and widens; it never classifies. */}
            {!selectedRole && (
              <div className="space-y-2">
                <label className="text-xs font-bold text-neutral-400 uppercase tracking-wider block">
                  Career Area
                </label>
                <select
                  value={selectedArea}
                  onChange={e => setSelectedArea(e.target.value)}
                  className="w-full h-11 px-4 bg-white border border-neutral-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
                >
                  <option value="">Whole ICT market</option>
                  {areas.map(area => (
                    <option key={area.name} value={area.name}>
                      {area.name} ({area.listing_count} jobs)
                    </option>
                  ))}
                </select>
                <p className="text-xs text-neutral-400">
                  {areas.length === 0
                    ? 'No career area has enough job data yet.'
                    : `${areas.reduce((n, a) => n + a.roles.length, 0)} Market Roles have enough JobStreet data to analyse.`}
                  {coverage && ` ${coverage.classified_total} of ${coverage.scraped_total} adverts classified (${coverage.classified_percentage}%).`}
                </p>
              </div>
            )}

            {/* Records wording only. No role is created, nothing is targeted,
                and no suggestion is returned. */}
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
            {/* Role-level and area-level results are never presented as
                equivalent. This banner is persistent, not dismissible, and
                always names the scope that actually answered rather than the
                role the student asked for. */}
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
                  {gap.data_quality.role_listing_count} scraped advert(s) classified into
                  that Market Role.</>
                ) : gap.data_quality.fell_back_to_broad_area ? (
                  <>Only {gap.data_quality.role_listing_count} scraped advert(s) have been
                  classified into <strong>{gap.target_role}</strong> so far — fewer than the{' '}
                  {gap.data_quality.evidence_floor} needed to analyse a Market Role on its
                  own. These figures cover the whole{' '}
                  <strong>{gap.target_broad_area}</strong> area ({gap.total_listings}{' '}
                  adverts) instead, which is the closest honest answer for that career.</>
                ) : gap.scope === 'BROAD_AREA' ? (
                  <>Analysed against the <strong>{gap.target_broad_area}</strong> area
                  ({gap.total_listings} adverts). Pick a Market Role above to narrow this
                  further.</>
                ) : gap.data_quality.has_target ? (
                  <>Neither <strong>{roleLabel}</strong> nor its career area has enough
                  classified adverts to analyse yet, so these figures cover the whole ICT
                  market ({gap.total_listings} adverts).</>
                ) : (
                  <>No Market Role selected, so this compares your skills against the whole
                  scraped ICT market ({gap.total_listings} adverts). Pick a Market Role
                  above for a sharper analysis.</>
                )}
              </span>
            </div>

            {/* Heading names the scope that actually answered. */}
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
                              <Badge
                                key={skill.skill_id}
                                variant={skill.readiness_status === 'MATCHED' ? 'success' : 'warning'}
                                className="bg-white px-3 py-1.5 flex items-center gap-1.5"
                                title={`Market asks ${LEVEL_LABEL[skill.required_level]}`}
                              >
                                <CheckCircle2 size={14} /> {skill.skill}
                                {' · '}
                                {skill.student_level ? LEVEL_LABEL[skill.student_level] : '—'}
                                {skill.readiness_status === 'DEVELOPING' && (
                                  <span className="font-normal opacity-70">
                                    {` of ${LEVEL_LABEL[skill.required_level]}`}
                                  </span>
                                )}
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
                              {gapSkill.readiness_status === 'DEVELOPING'
                                ? `${LEVEL_LABEL[gapSkill.student_level!]} → ${LEVEL_LABEL[gapSkill.required_level]}`
                                : `Needs ${LEVEL_LABEL[gapSkill.required_level]}`}
                            </span>
                          </div>
                          <div className="flex items-center gap-1.5 shrink-0">
                            <Badge
                              variant={gapSkill.readiness_status === 'DEVELOPING' ? 'warning' : 'neutral'}
                              className="text-[9px]"
                            >
                              {gapSkill.readiness_status}
                            </Badge>
                            <Badge variant={PRIORITY_VARIANT[gapSkill.priority_level ?? 'LOW']}>
                              {gapSkill.priority_level}
                            </Badge>
                          </div>
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
                          {/* The spread behind the required level, so the
                              student can see the evidence rather than trust a
                              single word. */}
                          <span className="text-[10px] text-neutral-400">
                            {(Object.entries(gapSkill.level_distribution) as
                              [ProficiencyLevel, number][])
                              .map(([level, n]) => `${LEVEL_LABEL[level]} ${n}`)
                              .join(' · ')}
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

            {/* What the market actually says about this Market Role.

                There is no progression ladder here, deliberately. A ladder
                would be a claim about career structure that scraped adverts
                do not make; what they do support is how many adverts back
                this role, at which levels employers advertise it, and how
                each advert came to be filed here. */}
            {profile && profile.role.name === selectedRole && (
              <section>
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
                  <div>
                    <h4 className="text-xl font-bold text-neutral-900">
                      Market evidence — {profile.role.name}
                    </h4>
                    <p className="text-xs text-neutral-400 font-medium mt-0.5">
                      {profile.listing_count} classified advert(s) in {profile.role.broad_area}
                      {profile.analysable
                        ? ''
                        : ` — below the ${profile.evidence_floor} needed to analyse this role alone`}
                    </p>
                  </div>
                  <Button variant="outline" size="sm" onClick={() => setShowEvidence(v => !v)}>
                    {showEvidence ? 'Hide' : 'Show'} evidence
                  </Button>
                </div>

                {showEvidence && (
                  <div className="space-y-4">
                    {profile.career_levels.length > 0 && (
                      <Card className="p-5">
                        <h5 className="font-bold text-neutral-900 mb-3">
                          Career levels employers advertise
                        </h5>
                        <div className="flex flex-wrap items-center gap-2">
                          {profile.career_levels.map(level => (
                            <div
                              key={level.career_level}
                              className="px-3 py-2 rounded-lg border border-neutral-100 bg-white"
                            >
                              <span className={cn(
                                'inline-block px-2 py-0.5 rounded text-[10px] font-bold tracking-wide',
                                LEVEL_COLORS[level.career_level] ?? 'bg-neutral-100 text-neutral-600'
                              )}>
                                {level.career_level}
                              </span>
                              <p className="text-sm font-semibold text-neutral-900 mt-1">
                                {level.listing_count} advert(s)
                              </p>
                            </div>
                          ))}
                        </div>
                      </Card>
                    )}

                    <Card className="p-5">
                      <h5 className="font-bold text-neutral-900 mb-1">
                        How these adverts were classified
                      </h5>
                      <p className="text-xs text-neutral-500 mb-3">
                        Every advert keeps the evidence that placed it here, so these
                        figures can be checked rather than taken on trust.
                      </p>
                      <div className="space-y-1.5">
                        {profile.classification_methods.map(row => (
                          <div
                            key={row.classification_method}
                            className="flex items-center justify-between text-sm"
                          >
                            <span className="text-neutral-700">
                              {METHOD_LABELS[row.classification_method]
                                ?? row.classification_method}
                            </span>
                            <span className="font-semibold text-neutral-900">
                              {row.listing_count}
                            </span>
                          </div>
                        ))}
                      </div>
                    </Card>

                    {profile.reviewed_titles.length > 0 && (
                      <Card className="p-5">
                        <h5 className="font-bold text-neutral-900 mb-1">
                          Job titles grouped into this role
                        </h5>
                        <p className="text-xs text-neutral-500 mb-3">
                          Reviewed naming variations, not guesses: each was checked as a
                          genuine way employers write this same career.
                        </p>
                        <div className="flex flex-wrap gap-1.5">
                          {profile.reviewed_titles.map(title => (
                            <span
                              key={title}
                              className="px-2.5 py-1 rounded-full bg-neutral-100 text-neutral-700 text-xs font-medium"
                            >
                              {title}
                            </span>
                          ))}
                        </div>
                      </Card>
                    )}
                  </div>
                )}
              </section>
            )}

            {/* Learning resources, grouped by the skill they teach.
                Named for what it is. This was "Recommended Learning Paths"
                over a flat list of six, which made two claims the data cannot
                support: that those six skills mattered most, and that the
                first course was the best one. The catalogue knows what a
                course teaches -- not how long it takes, how well it teaches,
                or whether it suits this student. So the page lists the
                related courses per skill and lets the student choose. */}
            <section>
              <div className="flex items-center gap-2 mb-6">
                <GraduationCap className="text-primary" size={24} />
                <div>
                  <h4 className="text-xl font-bold text-neutral-900">Learning Resources</h4>
                  <p className="text-xs text-neutral-500">
                    Courses related to each missing skill, most in-demand skill first.
                    Pick whichever suits you.
                  </p>
                </div>
              </div>
              {gap.resources_by_skill.length === 0 ? (
                <Card className="p-6 text-center text-sm text-neutral-500">
                  No learning resources are available for your missing skills yet.
                </Card>
              ) : (
                <div className="space-y-8">
                  {gap.resources_by_skill.map(group => {
                    const extra = expandedSkills[group.skill_id];
                    const shown = extra ?? group.resources;
                    const hasMore = group.total > shown.length;
                    return (
                      <div key={group.skill_id}>
                        <div className="flex flex-wrap items-baseline justify-between gap-2 mb-3">
                          <div className="flex items-baseline gap-2">
                            <h5 className="text-base font-bold text-neutral-900">
                              Related courses for {group.skill}
                            </h5>
                            {group.skill_priority && (
                              <span className={cn(
                                'text-[10px] font-black uppercase tracking-wider',
                                group.skill_priority === 'HIGH' ? 'text-danger'
                                  : group.skill_priority === 'MEDIUM' ? 'text-warning'
                                  : 'text-neutral-400'
                              )}>
                                {group.skill_priority} priority
                              </span>
                            )}
                          </div>
                          <span className="text-[11px] text-neutral-400">
                            {group.skill_demand_percentage !== null &&
                              `asked for in ${group.skill_demand_percentage}% of listings · `}
                            showing {shown.length} of {group.total}
                          </span>
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                          {shown.map(resource => (
                            <Card key={resource.id} className="p-4 flex flex-col gap-2">
                              <div className="flex items-start justify-between gap-2">
                                {/* The provider, colour-coded. A student
                                    scanning five platforms in one list needs
                                    to tell them apart at a glance. */}
                                <span className={cn(
                                  'text-[10px] font-black uppercase tracking-widest px-2 py-0.5 rounded text-white',
                                  PLATFORM_COLORS[resource.platform] ?? 'bg-neutral-600'
                                )}>
                                  {resource.platform}
                                </span>
                                <Badge variant="neutral">{resource.type}</Badge>
                              </div>
                              <p className="text-sm font-bold text-neutral-900 leading-snug">
                                {resource.title}
                              </p>
                              {/* Only when the provider actually said so.
                                  Most do not, and an absent price shown as
                                  "Paid" would be an invention. */}
                              {resource.is_free !== undefined && (
                                <span className={cn(
                                  'text-[10px] font-black uppercase tracking-wider w-fit',
                                  resource.is_free ? 'text-emerald-600' : 'text-neutral-500'
                                )}>
                                  {resource.is_free ? 'Free' : 'Paid'}
                                </span>
                              )}
                              <a
                                href={resource.url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="mt-auto pt-2"
                              >
                                <Button fullWidth variant="outline">
                                  <ExternalLink size={14} /> Open
                                </Button>
                              </a>
                            </Card>
                          ))}
                        </div>

                        {hasMore && (
                          <button
                            type="button"
                            onClick={() => loadAllResources(group.skill_id)}
                            disabled={loadingSkillId === group.skill_id}
                            className="mt-3 text-xs font-semibold text-primary hover:underline disabled:text-neutral-400"
                          >
                            {loadingSkillId === group.skill_id
                              ? 'Loading…'
                              : `View more (${group.total - shown.length} more)`}
                          </button>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </section>
          </>
        )}
      </div>
    </DashboardLayout>
  );
}
