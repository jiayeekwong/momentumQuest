'use client';

import { useState, useEffect } from 'react';
import { Search, CheckCircle2, XCircle, Award, ChevronDown, ExternalLink, ShieldCheck, Lock } from 'lucide-react';
import { DashboardLayout } from '@/src/components/Layout';
import { Card, Badge, Button, Checkbox } from '@/src/components/ui';
import { cn } from '@/src/lib/utils';
import { apiFetch } from '@/src/lib/apiFetch';

type EndorseStatus = 'pending' | 'endorsed' | 'rejected';

type ProficiencyLevel = 'BEGINNER' | 'INTERMEDIATE' | 'ADVANCED';

const LEVEL_LABEL: Record<ProficiencyLevel, string> = {
  BEGINNER: 'Beginner',
  INTERMEDIATE: 'Intermediate',
  ADVANCED: 'Advanced',
};

interface SkillEvidence {
  id: number;
  skill: string;
  skill_id: number;
  claimed_level: ProficiencyLevel;
  approved_level: ProficiencyLevel | '';
  granted_level: ProficiencyLevel | null;
  review_status: 'PENDING' | 'APPROVED' | 'REJECTED';
  review_note: string;
}

interface EndorsementRequest {
  id: number;
  student_name: string | null;
  student_email: string;
  matric_number: string;
  department: string;
  // Each claimed skill is decided on its own: a broad programme routinely
  // over-claims, and rejecting the whole document for one bad claim would
  // throw away the ones it genuinely supports.
  skill_evidence: SkillEvidence[];
  cert_url: string;
  source: string;
  certificate_type: string;
  certificate_name: string;
  original_name: string;
  has_file: boolean;
  uploaded_time: string;
  verified_status: 'PENDING' | 'APPROVED' | 'REJECTED';
  verified_at: string | null;
  rejection_reason: string;
  verification_notes: string;
  reviewed_by: string | null;
  consent_recorded_at: string | null;
}

/**
 * What the reviewer confirms before approving.
 *
 * There is deliberately no "IC/passport number matches" item. MomentumQuest
 * stores no identification number, so there is nothing to compare the one on
 * the document against — offering the check would imply a verification the
 * system cannot actually perform. The name on the document against the
 * registered name is the identity check that is genuinely available.
 */
const VERIFICATION_CHECKS = [
  'Name on the document matches the student\'s registered name',
  'Document is readable and legible',
  'Issuing institution or organisation is identifiable',
  'Qualification or skill information matches the submission',
] as const;

const REJECTION_REASONS = [
  ['NAME_MISMATCH', 'Name does not match'],
  ['UNREADABLE_DOCUMENT', 'Document is unreadable'],
  ['INCORRECT_DOCUMENT', 'Incorrect document'],
  ['INSUFFICIENT_INFORMATION', 'Insufficient information'],
  ['SUSPECTED_INVALID_DOCUMENT', 'Suspected invalid document'],
  ['OTHER', 'Other'],
] as const;

const toUiStatus = (vs: string): EndorseStatus => {
  if (vs === 'APPROVED') return 'endorsed';
  if (vs === 'REJECTED') return 'rejected';
  return 'pending';
};

const statusVariants: Record<EndorseStatus, 'neutral' | 'success' | 'danger'> = {
  pending: 'neutral', endorsed: 'success', rejected: 'danger',
};

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-MY', { day: 'numeric', month: 'short', year: 'numeric' });
}

export default function EndorsePage() {
  const [requests, setRequests] = useState<EndorsementRequest[]>([]);
  const [filter, setFilter] = useState<'All' | EndorseStatus>('All');
  const [search, setSearch] = useState('');
  const [expanded, setExpanded] = useState<number | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<number | null>(null);

  // The checklist is a reviewer's working aid, not stored data: it exists to
  // make the approval deliberate, so it gates the Approve button and is
  // cleared whenever a different submission is opened.
  const [checks, setChecks] = useState<boolean[]>(() => VERIFICATION_CHECKS.map(() => false));
  const [decision, setDecision] = useState<'APPROVED' | 'REJECTED' | null>(null);
  const [rejectionReason, setRejectionReason] = useState('');
  const [notes, setNotes] = useState('');
  const [formError, setFormError] = useState('');
  // Per-skill decisions, keyed by skill id. A claim absent from this map is
  // refused: an administrator approving two of three should not have to spell
  // out the refusal, and defaulting the other way would approve claims nobody
  // looked at.
  const [skillDecisions, setSkillDecisions] =
    useState<Record<number, ProficiencyLevel>>({});

  const resetDecisionForm = () => {
    setChecks(VERIFICATION_CHECKS.map(() => false));
    setDecision(null);
    setRejectionReason('');
    setNotes('');
    setFormError('');
    setSkillDecisions({});
  };

  const openPanel = (id: number) => {
    resetDecisionForm();
    // Opening a submission pre-selects every claim at the level the student
    // asked for, so "approve everything as claimed" is one click and any
    // correction is a deliberate edit away from it.
    const request = requests.find(r => r.id === id);
    if (request && expanded !== id) {
      setSkillDecisions(Object.fromEntries(
        request.skill_evidence.map(e => [e.skill_id, e.claimed_level])));
    }
    setExpanded(expanded === id ? null : id);
  };

  const toggleSkill = (skillId: number, claimed: ProficiencyLevel) =>
    setSkillDecisions(prev => {
      const next = { ...prev };
      if (skillId in next) delete next[skillId];
      else next[skillId] = claimed;
      return next;
    });

  const setSkillLevel = (skillId: number, level: ProficiencyLevel) =>
    setSkillDecisions(prev => ({ ...prev, [skillId]: level }));

  const allChecked = checks.every(Boolean);

  useEffect(() => {
    apiFetch('/api/resources/certificates/')
      .then(r => r.json())
      .then(data => setRequests(Array.isArray(data) ? data : (data.results ?? [])))
      .catch(() => {})
      .finally(() => setIsLoading(false));
  }, []);

  const openCertificate = async (id: number) => {
    try {
      const res = await apiFetch(`/api/resources/certificates/${id}/file/`);
      if (!res.ok) return;
      const url = URL.createObjectURL(await res.blob());
      window.open(url, '_blank');
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch {
      /* the button simply does nothing if the file cannot be read */
    }
  };

  const submitDecision = async (id: number) => {
    if (!decision) {
      setFormError('Choose whether to approve or reject this submission.');
      return;
    }
    if (decision === 'APPROVED' && !allChecked) {
      setFormError('Complete every item on the verification checklist before approving.');
      return;
    }
    if (decision === 'REJECTED' && !rejectionReason) {
      setFormError('Select a reason so the student is told why.');
      return;
    }
    if (decision === 'APPROVED' && Object.keys(skillDecisions).length === 0) {
      setFormError(
        'Approve at least one claimed skill, or reject the submission. '
        + 'A verified certificate that grants nothing is a rejection.');
      return;
    }

    setFormError('');
    setActionLoading(id);
    try {
      const res = await apiFetch(`/api/resources/certificates/${id}/endorse/`, {
        method: 'PATCH',
        body: JSON.stringify({
          verified_status: decision,
          rejection_reason: decision === 'REJECTED' ? rejectionReason : '',
          verification_notes: notes.trim(),
          skills: decision === 'APPROVED'
            ? Object.entries(skillDecisions).map(([skillId, level]) => ({
                skill_id: Number(skillId),
                approved_level: level,
              }))
            : [],
        }),
      });
      if (res.ok) {
        const updated = await res.json();
        setRequests(prev => prev.map(r => (r.id === id ? { ...r, ...updated } : r)));
        setExpanded(null);
        resetDecisionForm();
      } else {
        const data = await res.json().catch(() => ({}));
        const first = Object.values(data)[0];
        setFormError(
          Array.isArray(first) ? String(first[0]) : String(first ?? 'The decision could not be saved.')
        );
      }
    } catch {
      setFormError('The decision could not be saved.');
    } finally {
      setActionLoading(null);
    }
  };

  const filtered = requests.filter((r) => {
    const uiStatus = toUiStatus(r.verified_status);
    const matchFilter = filter === 'All' || uiStatus === filter;
    const name  = (r.student_name ?? '').toLowerCase();
    const skill = r.skill_evidence
      .map(e => e.skill).join(' ').toLowerCase();
    const matchSearch = name.includes(search.toLowerCase()) || skill.includes(search.toLowerCase());
    return matchFilter && matchSearch;
  });

  const pendingCount = requests.filter(r => r.verified_status === 'PENDING').length;

  return (
    <DashboardLayout title="Endorse Skills">
      <div className="max-w-4xl mx-auto space-y-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h2 className="text-2xl font-bold text-neutral-900 flex items-center gap-3">
              Skill Endorsements
              {pendingCount > 0 && <Badge variant="warning" className="text-xs font-black">{pendingCount} pending</Badge>}
            </h2>
            <p className="text-neutral-500 mt-1 text-sm">Review student certificate submissions and grant or deny endorsements.</p>
          </div>
          <div className="relative w-full md:w-52">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400" size={16} />
            <input type="text" placeholder="Search..." value={search} onChange={(e) => setSearch(e.target.value)}
              className="w-full h-10 pl-10 pr-4 bg-white border border-neutral-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20" />
          </div>
        </div>

        <div className="flex gap-1 p-1 bg-neutral-100 rounded-xl w-fit">
          {(['All', 'pending', 'endorsed', 'rejected'] as const).map((f) => (
            <button key={f} onClick={() => setFilter(f)}
              className={cn('px-4 py-2 text-xs font-bold rounded-lg transition-all capitalize', filter === f ? 'bg-white shadow-sm text-primary' : 'text-neutral-500 hover:text-neutral-900')}>
              {f}
            </button>
          ))}
        </div>

        {isLoading ? (
          <div className="space-y-3">
            {[1, 2, 3].map(i => <div key={i} className="h-20 bg-neutral-100 animate-pulse rounded-2xl" />)}
          </div>
        ) : (
          <div className="space-y-3">
            {filtered.map((req) => {
              const uiStatus = toUiStatus(req.verified_status);
              return (
                <Card key={req.id} className="p-0 overflow-hidden hover:border-primary/20 transition-all">
                  <div className="p-5 flex items-start gap-4">
                    <div className="w-11 h-11 rounded-xl bg-indigo-50 flex items-center justify-center text-primary shrink-0">
                      <Award size={20} />
                    </div>
                    <div className="flex-1">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <h3 className="font-bold text-neutral-900">{req.student_name ?? 'Unknown Student'}</h3>
                          <p className="text-sm font-semibold text-primary mt-0.5">
                            {req.skill_evidence.length
                              ? req.skill_evidence.map(e => e.skill).join(', ')
                              : 'No skill claimed'}
                          </p>
                          <p className="text-[10px] font-medium text-neutral-400 mt-0.5">Submitted {formatDate(req.uploaded_time)}</p>
                        </div>
                        <div className="flex items-center gap-2 shrink-0">
                          <Badge variant={statusVariants[uiStatus]} className="capitalize text-[10px] font-black tracking-widest">{uiStatus}</Badge>
                          <Button variant="outline" size="sm" className="h-8 w-8 p-0"
                            onClick={() => openPanel(req.id)}>
                            <ChevronDown size={15} className={cn('transition-transform', expanded === req.id ? 'rotate-180' : '')} />
                          </Button>
                        </div>
                      </div>
                    </div>
                  </div>

                  {expanded === req.id && (
                    <div className="px-5 pb-5 border-t border-neutral-100">
                      <div className="pt-4 space-y-4">
                        <div>
                          <p className="text-[10px] font-black text-neutral-400 uppercase tracking-widest mb-1.5">Student</p>
                          <dl className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
                            <div className="flex gap-2">
                              <dt className="text-neutral-400">Name</dt>
                              <dd className="font-medium text-neutral-800">{req.student_name ?? '—'}</dd>
                            </div>
                            <div className="flex gap-2">
                              <dt className="text-neutral-400">Matric ID</dt>
                              <dd className="font-medium text-neutral-800">{req.matric_number || '—'}</dd>
                            </div>
                            <div className="flex gap-2">
                              <dt className="text-neutral-400">Email</dt>
                              <dd className="font-medium text-neutral-800 truncate">{req.student_email || '—'}</dd>
                            </div>
                            <div className="flex gap-2">
                              <dt className="text-neutral-400">Department</dt>
                              <dd className="font-medium text-neutral-800">{req.department || '—'}</dd>
                            </div>
                          </dl>
                          {req.consent_recorded_at && (
                            <p className="mt-2 text-[11px] text-neutral-400">
                              Upload consent recorded {formatDate(req.consent_recorded_at)}.
                            </p>
                          )}
                        </div>

                        <div>
                          <p className="text-[10px] font-black text-neutral-400 uppercase tracking-widest mb-1.5">Certificate / Evidence</p>
                          {req.has_file ? (
                            <button type="button" onClick={() => openCertificate(req.id)}
                              className="inline-flex items-center gap-1.5 text-sm text-primary font-semibold hover:underline bg-indigo-50 px-3 py-2 rounded-lg border border-indigo-100">
                              <ExternalLink size={13} />
                              View Certificate
                              <span className="text-neutral-400 font-normal">
                                — {req.original_name || 'uploaded file'}
                                {req.source ? ` · ${req.source}` : ''}
                              </span>
                            </button>
                          ) : req.cert_url ? (
                            <a href={req.cert_url} target="_blank" rel="noopener noreferrer"
                              className="inline-flex items-center gap-1.5 text-sm text-primary font-semibold hover:underline bg-indigo-50 px-3 py-2 rounded-lg border border-indigo-100">
                              <ExternalLink size={13} />
                              View Certificate
                              {req.source && <span className="text-neutral-400 font-normal">— {req.source}</span>}
                            </a>
                          ) : (
                            <p className="text-sm text-neutral-400 italic bg-neutral-50 p-4 rounded-xl border border-neutral-100">No certificate evidence provided.</p>
                          )}
                        </div>
                        {uiStatus === 'pending' ? (
                          <>
                            <div className="rounded-xl border border-neutral-100 bg-neutral-50 p-4 space-y-3">
                              <div className="flex items-center gap-2">
                                <ShieldCheck size={14} className="text-primary" />
                                <p className="text-[10px] font-black text-neutral-900 uppercase tracking-widest">
                                  Verification Checklist
                                </p>
                              </div>
                              {VERIFICATION_CHECKS.map((item, i) => (
                                <Checkbox
                                  key={item}
                                  checked={checks[i]}
                                  onChange={(e) => setChecks(prev => {
                                    const next = [...prev];
                                    next[i] = e.target.checked;
                                    return next;
                                  })}
                                  label={item}
                                />
                              ))}
                              <p className="flex items-start gap-1.5 pt-1 text-[11px] leading-relaxed text-neutral-400">
                                <Lock size={12} className="mt-0.5 shrink-0" />
                                MomentumQuest stores no NRIC/MyKad or passport number, so there is
                                nothing to compare an identification number against. Check the name
                                instead. Any identification number visible on the document stays
                                inside it — do not copy it anywhere.
                              </p>
                            </div>


                            {/* Each claimed skill is decided on its own.
                                A broad programme routinely over-claims, so
                                approving a subset -- or lowering a level the
                                document does not support -- must be possible
                                without rejecting the whole submission. */}
                            <div className="rounded-xl border border-neutral-100 bg-white p-4 space-y-3">
                              <p className="text-[10px] font-black text-neutral-900 uppercase tracking-widest">
                                Claimed Skills
                              </p>
                              {req.skill_evidence.length === 0 ? (
                                <p className="text-sm text-neutral-400 italic">
                                  This submission claims no skills.
                                </p>
                              ) : req.skill_evidence.map(evidence => {
                                const approved = evidence.skill_id in skillDecisions;
                                return (
                                  <div
                                    key={evidence.id}
                                    className={cn(
                                      'flex flex-col gap-2 rounded-lg border p-3 sm:flex-row sm:items-center sm:justify-between',
                                      approved
                                        ? 'border-emerald-200 bg-emerald-50/50'
                                        : 'border-neutral-200 bg-neutral-50'
                                    )}
                                  >
                                    <Checkbox
                                      checked={approved}
                                      onChange={() => toggleSkill(
                                        evidence.skill_id, evidence.claimed_level)}
                                      label={`${evidence.skill} — claimed ${LEVEL_LABEL[evidence.claimed_level]}`}
                                    />
                                    <select
                                      value={skillDecisions[evidence.skill_id] ?? evidence.claimed_level}
                                      disabled={!approved}
                                      onChange={e => setSkillLevel(
                                        evidence.skill_id,
                                        e.target.value as ProficiencyLevel)}
                                      className="rounded-lg border border-neutral-200 px-2 py-1.5 text-xs
                                                 disabled:opacity-40 focus:border-primary focus:outline-none"
                                    >
                                      {(Object.keys(LEVEL_LABEL) as ProficiencyLevel[]).map(level => (
                                        <option key={level} value={level}>
                                          Approve at {LEVEL_LABEL[level]}
                                        </option>
                                      ))}
                                    </select>
                                  </div>
                                );
                              })}
                              <p className="pt-1 text-[11px] leading-relaxed text-neutral-400">
                                Unticked claims are refused. An approved certificate
                                may carry refused claims — that is the normal outcome
                                when a broad programme evidences only some of what was
                                asked for.
                              </p>
                            </div>

                            <div className="space-y-3">
                              <p className="text-[10px] font-black text-neutral-400 uppercase tracking-widest">
                                Verification Decision
                              </p>
                              <div className="flex gap-2">
                                {([
                                  ['APPROVED', 'Approve', CheckCircle2],
                                  ['REJECTED', 'Reject', XCircle],
                                ] as const).map(([value, label, Icon]) => (
                                  <button
                                    key={value}
                                    type="button"
                                    onClick={() => setDecision(value)}
                                    className={cn(
                                      'flex items-center gap-1.5 rounded-lg border-2 px-4 py-2 text-xs font-bold transition-all',
                                      decision === value
                                        ? value === 'APPROVED'
                                          ? 'border-success bg-emerald-50 text-success'
                                          : 'border-danger bg-red-50 text-danger'
                                        : 'border-neutral-200 text-neutral-500 hover:border-neutral-300'
                                    )}
                                  >
                                    <Icon size={14} /> {label}
                                  </button>
                                ))}
                              </div>

                              {decision === 'REJECTED' && (
                                <div className="space-y-1.5">
                                  <label className="block text-[10px] font-black uppercase tracking-widest text-neutral-900">
                                    Reason
                                  </label>
                                  <select
                                    value={rejectionReason}
                                    onChange={(e) => setRejectionReason(e.target.value)}
                                    className="h-10 w-full rounded-lg border border-neutral-300 bg-white px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
                                  >
                                    <option value="">Select a reason…</option>
                                    {REJECTION_REASONS.map(([value, label]) => (
                                      <option key={value} value={value}>{label}</option>
                                    ))}
                                  </select>
                                  <p className="text-[11px] text-neutral-400">
                                    The student is shown a plain-language explanation, not this code.
                                  </p>
                                </div>
                              )}

                              <div className="space-y-1.5">
                                <label className="block text-[10px] font-black uppercase tracking-widest text-neutral-900">
                                  Internal notes <span className="font-medium normal-case tracking-normal text-neutral-400">(optional)</span>
                                </label>
                                <textarea
                                  value={notes}
                                  onChange={(e) => setNotes(e.target.value)}
                                  rows={2}
                                  placeholder="Visible only to administrators."
                                  className="w-full rounded-lg border border-neutral-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
                                />
                                <p className="text-[11px] text-neutral-400">
                                  Never shown to the student. Do not record identification numbers here.
                                </p>
                              </div>

                              {formError && (
                                <div className="rounded-lg border border-red-100 bg-red-50 p-3 text-sm text-danger">
                                  {formError}
                                </div>
                              )}

                              <div className="flex gap-3">
                                <Button size="sm" variant="outline" className="h-9 text-xs"
                                  onClick={() => { setExpanded(null); resetDecisionForm(); }}>
                                  Cancel
                                </Button>
                                <Button size="sm"
                                  className="h-9 text-xs flex items-center gap-1.5"
                                  disabled={actionLoading === req.id}
                                  onClick={() => submitDecision(req.id)}>
                                  {actionLoading === req.id ? 'Saving…' : 'Submit Decision'}
                                </Button>
                              </div>
                            </div>
                          </>
                        ) : (
                          <div className="rounded-xl border border-neutral-100 bg-neutral-50 p-4 space-y-1.5">
                            <p className="text-sm font-semibold text-neutral-800">
                              {uiStatus === 'endorsed' ? 'Endorsed' : 'Rejected'}
                              {req.reviewed_by ? ` by ${req.reviewed_by}` : ''}
                              {req.verified_at ? ` on ${formatDate(req.verified_at)}` : ''}
                            </p>
                            {req.rejection_reason && (
                              <p className="text-xs text-neutral-500">
                                Reason: {REJECTION_REASONS.find(([v]) => v === req.rejection_reason)?.[1]
                                         ?? req.rejection_reason}
                              </p>
                            )}
                            {req.verification_notes && (
                              <p className="text-xs italic text-neutral-500">
                                Internal note: {req.verification_notes}
                              </p>
                            )}
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </Card>
              );
            })}
          </div>
        )}

        {!isLoading && filtered.length === 0 && (
          <div className="py-20 text-center">
            <Award size={48} className="mx-auto text-neutral-200 mb-4" />
            <h3 className="text-xl font-bold text-neutral-900">No requests found</h3>
            <p className="text-neutral-500 mt-1 text-sm">
              {search || filter !== 'All' ? 'Try adjusting your search or filter.' : 'Certificate submissions will appear here.'}
            </p>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
