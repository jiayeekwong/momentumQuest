'use client';

import { useState, useEffect, useRef } from 'react';
import {
  Award, FileText, Upload, CheckCircle2, XCircle, Clock,
  ChevronDown, ChevronRight, ExternalLink, AlertTriangle, ShieldCheck, Trash2,
} from 'lucide-react';
import { Card, Badge, Button, Checkbox } from '@/src/components/ui';
import { cn } from '@/src/lib/utils';
import { apiFetch } from '@/src/lib/apiFetch';
import { usePrivacyNotice, toParagraphs, DocumentNotice } from '@/src/lib/privacyNotice';

interface ParsedSubject {
  code: string;
  name: string;
  credit: number;
  grade: string;
  semester: string;
  session: string;
  checksum_ok: boolean;
  skills: string[];
}

interface Transcript {
  id: number;
  original_name: string;
  uploaded_time: string;
  status: 'PARSED' | 'FAILED';
  parsed_subjects: ParsedSubject[];
  skills_added: number;
  error_message: string;
  // Parsing and verification are separate states. "Parsed" means the file was
  // readable; only verification_status says whether it changed any skills.
  document_type_status: 'LIKELY_TRANSCRIPT' | 'UNCERTAIN' | 'NOT_TRANSCRIPT' | 'LEGACY_UNVERIFIED';
  verification_status: 'PENDING' | 'AUTO_VERIFIED' | 'MANUALLY_VERIFIED' | 'REJECTED';
  detected_institution: string;
  rejection_reason: string;
  skills_applied_at: string | null;
}

interface Certificate {
  id: number;
  skill: string | null;
  cert_url: string;
  source: string;
  original_name: string;
  has_file: boolean;
  uploaded_time: string;
  verified_status: 'PENDING' | 'APPROVED' | 'REJECTED';
  // Plain-language explanation of a rejection. The admin's internal notes are
  // never sent to the student, only this.
  rejection_message: string;
}

interface SkillOption {
  id: number;
  skill_name: string;
  skill_category: string;
}

type Tab = 'transcripts' | 'certificates';

const STATUS_BADGE: Record<string, { variant: 'success' | 'warning' | 'danger'; icon: typeof Clock }> = {
  APPROVED: { variant: 'success', icon: CheckCircle2 },
  PENDING:  { variant: 'warning', icon: Clock },
  REJECTED: { variant: 'danger',  icon: XCircle },
};

function formatDate(value: string) {
  return new Date(value).toLocaleDateString('en-MY', {
    day: 'numeric', month: 'short', year: 'numeric',
  });
}

// ─── Transcript row ──────────────────────────────────────────────────────────

function TranscriptCard({ transcript }: { transcript: Transcript }) {
  const [expanded, setExpanded] = useState(false);
  const [opening, setOpening] = useState(false);

  const recognised = transcript.parsed_subjects.filter(s => s.skills.length > 0);

  // Verification, not parsing, decides what the student is told. A document
  // can parse perfectly and still have granted nothing.
  const isVerified =
    transcript.verification_status === 'MANUALLY_VERIFIED' ||
    transcript.verification_status === 'AUTO_VERIFIED';

  const statusBadge: { label: string; variant: 'success' | 'warning' | 'danger' | 'neutral' } =
    isVerified
      ? { label: 'Verified', variant: 'success' }
      : transcript.verification_status === 'REJECTED'
        ? {
            label: transcript.document_type_status === 'NOT_TRANSCRIPT'
              ? 'Could not recognise transcript'
              : 'Rejected',
            variant: 'danger',
          }
        : { label: 'Awaiting verification', variant: 'warning' };

  // The file endpoint needs the Bearer token, so a plain link would 401 —
  // fetch it through apiFetch and open the resulting blob instead.
  const openPdf = async () => {
    setOpening(true);
    try {
      const res = await apiFetch(`/api/resources/skill-validation/transcripts/${transcript.id}/file/`);
      if (!res.ok) {
        alert('Could not open this transcript.');
        return;
      }
      const url = URL.createObjectURL(await res.blob());
      window.open(url, '_blank');
      // Give the new tab time to load before releasing the object URL.
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch {
      alert('Could not open this transcript.');
    } finally {
      setOpening(false);
    }
  };

  return (
    <Card className="p-0 overflow-hidden">
      <div className="flex flex-col sm:flex-row sm:items-center gap-4 p-5">
        <div className="h-10 w-10 rounded-lg bg-indigo-50 flex items-center justify-center shrink-0">
          <FileText size={18} className="text-primary" />
        </div>

        <div className="flex-1 min-w-0">
          <p className="font-medium text-neutral-900 truncate">
            {transcript.original_name || 'Transcript'}
          </p>
          <p className="text-sm text-neutral-500 mt-0.5">
            Uploaded {formatDate(transcript.uploaded_time)}
            {transcript.parsed_subjects.length > 0 && (
              <> · {transcript.parsed_subjects.length} subjects</>
            )}
            {/* Skill counts appear only once skills were actually applied.
                Showing them while pending would tell the student their
                profile had changed when nothing had. */}
            {isVerified && (
              <> · {transcript.skills_added} skills added</>
            )}
            {transcript.detected_institution && (
              <> · {transcript.detected_institution}</>
            )}
          </p>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <Badge variant={statusBadge.variant}>{statusBadge.label}</Badge>
          <Button size="sm" variant="outline" onClick={openPdf} isLoading={opening}>
            <ExternalLink size={14} /> View PDF
          </Button>
        </div>
      </div>

      {/* PENDING is now the exception, not the normal path: a transcript that
          clears every check is verified on upload. Anything still pending is
          an older upload waiting on an administrator. */}
      {transcript.verification_status === 'PENDING' && (
        <div className="px-5 pb-4 -mt-1">
          <div className="flex gap-2 text-sm text-blue-800 bg-blue-50 border border-blue-100 rounded-lg p-3">
            <AlertTriangle size={16} className="shrink-0 mt-0.5" />
            <span>
              Awaiting review. Your skills will be updated once this document
              has been checked.
            </span>
          </div>
        </div>
      )}

      {/* The safe reason only. Classification detail stays on the admin side
          so it cannot be read as a checklist for producing a passing forgery. */}
      {transcript.verification_status === 'REJECTED' && transcript.rejection_reason && (
        <div className="px-5 pb-4 -mt-1">
          <div className="flex gap-2 text-sm text-red-800 bg-red-50 border border-red-100 rounded-lg p-3">
            <AlertTriangle size={16} className="shrink-0 mt-0.5" />
            <span className="whitespace-pre-line">{transcript.rejection_reason}</span>
          </div>
        </div>
      )}

      {transcript.error_message && transcript.verification_status !== 'REJECTED' && (
        <div className="px-5 pb-4 -mt-1">
          <div className="flex gap-2 text-sm text-amber-700 bg-amber-50 border border-amber-100 rounded-lg p-3">
            <AlertTriangle size={16} className="shrink-0 mt-0.5" />
            <span className="whitespace-pre-line">{transcript.error_message}</span>
          </div>
        </div>
      )}

      {transcript.parsed_subjects.length > 0 && (
        <>
          <button
            onClick={() => setExpanded(v => !v)}
            className="w-full flex items-center gap-2 px-5 py-3 border-t border-neutral-100 text-sm font-medium text-neutral-600 hover:bg-neutral-50 transition-colors"
          >
            {expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
            {expanded ? 'Hide' : 'Show'} subjects ({recognised.length} of {transcript.parsed_subjects.length} mapped to skills)
          </button>

          {expanded && (
            <div className="border-t border-neutral-100 overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-neutral-50 text-neutral-500">
                  <tr>
                    <th className="text-left font-medium px-5 py-2">Module</th>
                    <th className="text-left font-medium px-3 py-2">Subject</th>
                    <th className="text-left font-medium px-3 py-2">Grade</th>
                    <th className="text-left font-medium px-5 py-2">Skills recognised</th>
                  </tr>
                </thead>
                <tbody>
                  {transcript.parsed_subjects.map((subject, i) => (
                    <tr key={`${subject.code}-${i}`} className="border-t border-neutral-100">
                      <td className="px-5 py-2 font-mono text-xs text-neutral-600">{subject.code}</td>
                      <td className="px-3 py-2 text-neutral-800">{subject.name}</td>
                      <td className="px-3 py-2">
                        <span className="font-medium text-neutral-700">{subject.grade}</span>
                      </td>
                      <td className="px-5 py-2">
                        {subject.skills.length > 0 ? (
                          <div className="flex flex-wrap gap-1">
                            {subject.skills.map(skill => (
                              <Badge key={skill} variant="primary">{skill}</Badge>
                            ))}
                          </div>
                        ) : (
                          <span className="text-neutral-400 text-xs">
                            {subject.checksum_ok ? 'No matching skill' : 'Could not read this row'}
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </Card>
  );
}

/**
 * The acknowledgement a student gives before handing over a document.
 *
 * The wording comes from the server rather than from this file: it is the
 * text they are agreeing to, and a stale local copy would mean recording
 * consent to something they never read.
 */
function DocumentConsentPanel({
  notice,
  checked,
  onChange,
}: {
  notice: DocumentNotice | null;
  checked: boolean;
  onChange: (value: boolean) => void;
}) {
  if (!notice) {
    return (
      <div className="space-y-2 rounded-lg border border-neutral-200 bg-neutral-50 p-4">
        <div className="h-3 w-1/3 animate-pulse rounded bg-neutral-200" />
        <div className="h-3 w-full animate-pulse rounded bg-neutral-200" />
      </div>
    );
  }

  return (
    <div className="space-y-3 rounded-lg border border-amber-200 bg-amber-50/60 p-4 text-left">
      <div className="flex items-center gap-2">
        <ShieldCheck size={15} className="text-amber-600" />
        <p className="text-sm font-semibold text-neutral-800">{notice.heading}</p>
      </div>
      {toParagraphs(notice.body).map(paragraph => (
        <p key={paragraph} className="text-xs leading-relaxed text-neutral-600">
          {paragraph}
        </p>
      ))}
      <a
        href="/privacy-notice"
        target="_blank"
        rel="noopener noreferrer"
        className="inline-block text-xs font-semibold text-primary hover:underline"
      >
        Read the full Privacy Notice
      </a>
      <Checkbox
        checked={checked}
        onChange={e => onChange(e.target.checked)}
        label={notice.acknowledgement}
      />
    </div>
  );
}


// ─── Certificate upload ───────────────────────────────────────

/**
 * Submits one certificate as proof of a skill.
 *
 * Two kinds of proof are accepted because students hold them in two forms: a
 * downloaded PDF/image, or a credential URL from the issuing platform. The
 * backend requires exactly one of them, so the button stays disabled until a
 * skill and at least one proof are present.
 */
function CertificateUploadForm({
  skillOptions,
  uploadNotice,
  onUploaded,
}: {
  skillOptions: SkillOption[];
  uploadNotice: DocumentNotice | null;
  onUploaded: (message: { kind: 'ok' | 'err'; text: string }) => void;
}) {
  const [skillId, setSkillId] = useState('');
  const [source, setSource] = useState('');
  const [certUrl, setCertUrl] = useState('');
  const [file, setFile] = useState<File | null>(null);
  // Acknowledged per submission, not once per account: the student is
  // consenting to *this* document being read, so it resets with the form.
  const [consentAck, setConsentAck] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const certInput = useRef<HTMLInputElement>(null);

  const canSubmit =
    Boolean(skillId) && Boolean(file || certUrl.trim()) && consentAck
    && Boolean(uploadNotice) && !submitting;

  const reset = () => {
    setSkillId('');
    setSource('');
    setCertUrl('');
    setFile(null);
    setConsentAck(false);
    if (certInput.current) certInput.current.value = '';
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);

    const body = new FormData();
    body.append('skill', skillId);
    if (source.trim()) body.append('source', source.trim());
    if (certUrl.trim()) body.append('cert_url', certUrl.trim());
    if (file) body.append('file', file);
    body.append('document_consent_ack', 'true');

    try {
      const res = await apiFetch('/api/resources/certificates/', { method: 'POST', body });
      const data = await res.json();
      if (res.ok) {
        reset();
        onUploaded({
          kind: 'ok',
          text: 'Certificate submitted. An admin will endorse it before the skill '
              + 'is added to your profile.',
        });
      } else {
        // DRF returns {field: [message]}; surface the first one rather than [object Object].
        const first = Object.values(data ?? {})[0];
        onUploaded({
          kind: 'err',
          text: Array.isArray(first) ? String(first[0]) : String(first ?? 'Upload failed.'),
        });
      }
    } catch {
      onUploaded({ kind: 'err', text: 'Upload failed. Please try again.' });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Card className="p-5">
      <form onSubmit={submit} className="space-y-4">
        <div>
          <p className="font-medium text-neutral-800">Upload a certificate</p>
          <p className="text-sm text-neutral-500 mt-0.5">
            Attach the certificate file, or paste the credential URL your course
            platform issued.
          </p>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <label className="block">
            <span className="text-sm font-medium text-neutral-700">
              Skill proven <span className="text-red-500">*</span>
            </span>
            <select
              value={skillId}
              onChange={e => setSkillId(e.target.value)}
              required
              className="mt-1 w-full rounded-lg border border-neutral-200 px-3 py-2 text-sm
                         focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
            >
              <option value="">Select a skill…</option>
              {skillOptions.map(skill => (
                <option key={skill.id} value={skill.id}>
                  {skill.skill_name}
                  {skill.skill_category ? ` — ${skill.skill_category}` : ''}
                </option>
              ))}
            </select>
          </label>

          <label className="block">
            <span className="text-sm font-medium text-neutral-700">Issuer</span>
            <input
              type="text"
              value={source}
              onChange={e => setSource(e.target.value)}
              placeholder="Coursera, Microsoft Learn…"
              className="mt-1 w-full rounded-lg border border-neutral-200 px-3 py-2 text-sm
                         focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </label>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <span className="text-sm font-medium text-neutral-700">Certificate file</span>
            <input
              ref={certInput}
              type="file"
              accept=".pdf,.png,.jpg,.jpeg"
              className="hidden"
              onChange={e => setFile(e.target.files?.[0] ?? null)}
            />
            <div className="mt-1 flex items-center gap-2">
              <Button type="button" size="sm" variant="outline"
                      onClick={() => certInput.current?.click()}>
                <Upload size={14} /> Choose file
              </Button>
              <span className="text-sm text-neutral-500 truncate">
                {file ? file.name : 'PDF, PNG or JPG · max 10MB'}
              </span>
            </div>
          </div>

          <label className="block">
            <span className="text-sm font-medium text-neutral-700">or credential URL</span>
            <input
              type="url"
              value={certUrl}
              onChange={e => setCertUrl(e.target.value)}
              placeholder="https://coursera.org/verify/…"
              className="mt-1 w-full rounded-lg border border-neutral-200 px-3 py-2 text-sm
                         focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </label>
        </div>


        {/* Acknowledged separately from the consent given at signup: this one
            is about the specific document being handed over. */}
        <DocumentConsentPanel
          notice={uploadNotice}
          checked={consentAck}
          onChange={setConsentAck}
        />

        <div className="flex items-center gap-3">
          <Button type="submit" disabled={!canSubmit} isLoading={submitting}>
            {submitting ? 'Submitting…' : 'Submit for endorsement'}
          </Button>
          {!skillId && (
            <span className="text-xs text-neutral-400">Choose the skill this certificate proves.</span>
          )}
          {skillId && !consentAck && (
            <span className="text-xs text-neutral-400">
              Acknowledge the verification notice to submit.
            </span>
          )}
        </div>
      </form>
    </Card>
  );
}


// ─── Section ─────────────────────────────────────────────────────────────────

/**
 * Skill Validation, rendered inside the student's profile.
 *
 * `onSkillsChanged` fires after a transcript is accepted so the surrounding
 * Skill Portfolio can refresh — a transcript upload writes StudentSkill rows,
 * and the list above it would otherwise show stale data.
 */
export function SkillValidation({ onSkillsChanged }: { onSkillsChanged?: () => void }) {
  const [tab, setTab] = useState<Tab>('transcripts');
  const [transcripts, setTranscripts] = useState<Transcript[]>([]);
  const [certificates, setCertificates] = useState<Certificate[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null);

  const [skillOptions, setSkillOptions] = useState<SkillOption[]>([]);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  // A transcript is an examination result and is the document most likely to
  // show an NRIC, so it is acknowledged before upload just like a certificate.
  const [transcriptConsent, setTranscriptConsent] = useState(false);
  const { notice } = usePrivacyNotice();

  const fileInput = useRef<HTMLInputElement>(null);

  const loadTranscripts = () =>
    apiFetch('/api/resources/skill-validation/transcripts/')
      .then(r => r.json())
      .then((data: Transcript[]) => setTranscripts(Array.isArray(data) ? data : []))
      .catch(() => {});

  const openCertificate = async (cert: Certificate) => {
    try {
      const res = await apiFetch(`/api/resources/certificates/${cert.id}/file/`);
      if (!res.ok) {
        setMessage({ kind: 'err', text: 'Could not open this certificate.' });
        return;
      }
      const url = URL.createObjectURL(await res.blob());
      window.open(url, '_blank');
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch {
      setMessage({ kind: 'err', text: 'Could not open this certificate.' });
    }
  };

  const loadCertificates = () =>
    apiFetch('/api/resources/certificates/')
      .then(r => r.json())
      .then((data: Certificate[]) => setCertificates(Array.isArray(data) ? data : []))
      .catch(() => {});

  /**
   * Withdraw a submission that has not been decided yet.
   *
   * The button only appears on PENDING rows, but the server enforces the same
   * rule -- an approved certificate is the evidence behind a skill the student
   * already holds, so it cannot be pulled out from under it.
   */
  const deleteCertificate = async (id: number) => {
    setDeletingId(id);
    try {
      const res = await apiFetch(`/api/resources/certificates/${id}/`, { method: 'DELETE' });
      if (res.ok) {
        setCertificates(prev => prev.filter(c => c.id !== id));
        setMessage({ kind: 'ok', text: 'Submission withdrawn and the document deleted.' });
      } else {
        setMessage({ kind: 'err', text: 'This submission could not be withdrawn.' });
      }
    } catch {
      setMessage({ kind: 'err', text: 'This submission could not be withdrawn.' });
    } finally {
      setDeletingId(null);
    }
  };

  useEffect(() => {
    Promise.all([loadTranscripts(), loadCertificates()]).finally(() => setIsLoading(false));
    // The skill must be a real Skill row, not free text, or the certificate
    // could never be matched to a gap the student is trying to close.
    apiFetch('/api/scrape-jobs/skills/')
      .then(r => r.json())
      .then((data: SkillOption[]) => setSkillOptions(Array.isArray(data) ? data : []))
      .catch(() => {});
  }, []);

  const handleTranscriptUpload = async (file: File) => {
    setUploading(true);
    setMessage(null);

    const body = new FormData();
    body.append('file', file);
    body.append('document_consent_ack', 'true');

    try {
      const res = await apiFetch('/api/resources/skill-validation/transcripts/', {
        method: 'POST',
        body,
      });
      const data = await res.json();

      if (res.ok) {
        setMessage({ kind: 'ok', text: data.detail ?? 'Transcript verified.' });
        // Only when skills were actually applied. A transcript left pending
        // changes nothing, and refreshing then would imply otherwise.
        if (data.verification_status === 'AUTO_VERIFIED'
            || data.verification_status === 'MANUALLY_VERIFIED') {
          onSkillsChanged?.();
        }
      } else {
        setMessage({
          kind: 'err',
          text: data.rejection_reason || data.error_message || data.detail || 'Upload failed.',
        });
      }
      await loadTranscripts();
    } catch {
      setMessage({ kind: 'err', text: 'Upload failed. Please try again.' });
    } finally {
      setUploading(false);
      if (fileInput.current) fileInput.current.value = '';
    }
  };

  return (
    <Card className="p-6">
      <div className="space-y-6">
        <div>
          <h3 className="text-lg font-bold text-neutral-900 flex items-center gap-2">
            <ShieldCheck size={20} className="text-primary" /> Skill Validation
          </h3>
          <p className="text-sm text-neutral-500 mt-1">
            Prove your skills with your examination results or a course certificate.
          </p>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 border-b border-neutral-200">
          {([
            { key: 'transcripts',  label: 'Exam Results', icon: FileText, count: transcripts.length },
            { key: 'certificates', label: 'Certificates', icon: Award,    count: certificates.length },
          ] as const).map(({ key, label, icon: Icon, count }) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={cn(
                'flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors',
                tab === key
                  ? 'border-primary text-primary'
                  : 'border-transparent text-neutral-500 hover:text-neutral-800'
              )}
            >
              <Icon size={16} /> {label}
              {count > 0 && <span className="text-xs text-neutral-400">({count})</span>}
            </button>
          ))}
        </div>

        {message && (
          <div className={cn(
            'rounded-lg p-4 text-sm border',
            message.kind === 'ok'
              ? 'bg-emerald-50 border-emerald-100 text-emerald-800'
              : 'bg-red-50 border-red-100 text-red-700'
          )}>
            {message.text}
          </div>
        )}

        {/* ─── Exam results ─────────────────────────────────────────────── */}
        {tab === 'transcripts' && (
          <div className="space-y-4">
            <Card className="border-dashed border-2 border-neutral-200 bg-neutral-50/50 text-center py-8">
              <Upload size={22} className="mx-auto text-neutral-400" />
              <p className="mt-3 font-medium text-neutral-800">Upload your academic transcript</p>
              <p className="text-sm text-neutral-500 mt-1 max-w-md mx-auto">
                Your subjects and grades are read automatically and matched to skills.
                No admin approval needed — the examination result is the proof.
              </p>
              <input
                ref={fileInput}
                type="file"
                accept="application/pdf"
                className="hidden"
                onChange={e => {
                  const file = e.target.files?.[0];
                  if (file) handleTranscriptUpload(file);
                }}
              />
              <div className="mx-auto mt-5 max-w-md">
                <DocumentConsentPanel
                  notice={notice?.transcript_notice ?? null}
                  checked={transcriptConsent}
                  onChange={setTranscriptConsent}
                />
              </div>

              <Button
                className="mt-4 mx-auto"
                onClick={() => fileInput.current?.click()}
                isLoading={uploading}
                disabled={!transcriptConsent || !notice || uploading}
              >
                {uploading ? 'Reading transcript…' : 'Choose PDF'}
              </Button>
              {!transcriptConsent && (
                <p className="mt-2 text-xs text-neutral-400">
                  Acknowledge the notice above to upload.
                </p>
              )}
            </Card>

            {isLoading ? (
              <p className="text-sm text-neutral-500 py-4">Loading…</p>
            ) : transcripts.length === 0 ? (
              <p className="text-sm text-neutral-500 py-4 text-center">
                You have not uploaded any examination results yet.
              </p>
            ) : (
              transcripts.map(t => <TranscriptCard key={t.id} transcript={t} />)
            )}
          </div>
        )}

        {/* ─── Certificates ─────────────────────────────────────────────── */}
        {tab === 'certificates' && (
          <div className="space-y-3">
            <div className="text-sm text-neutral-500 bg-neutral-50 border border-neutral-100 rounded-lg p-4">
              Certificates from external courses need an admin to endorse them before
              the skill is added to your profile.
            </div>

            <CertificateUploadForm
              skillOptions={skillOptions}
              uploadNotice={notice?.upload_notice ?? null}
              onUploaded={result => {
                setMessage(result);
                if (result.kind === 'ok') loadCertificates();
              }}
            />

            {isLoading ? (
              <p className="text-sm text-neutral-500 py-4">Loading…</p>
            ) : certificates.length === 0 ? (
              <p className="text-sm text-neutral-500 py-4 text-center">
                You have not uploaded any certificates yet.
              </p>
            ) : (
              certificates.map(cert => {
                const badge = STATUS_BADGE[cert.verified_status] ?? STATUS_BADGE.PENDING;
                const Icon = badge.icon;
                return (
                  <Card key={cert.id} className="flex flex-col sm:flex-row sm:items-center gap-4 p-5">
                    <div className="h-10 w-10 rounded-lg bg-amber-50 flex items-center justify-center shrink-0">
                      <Award size={18} className="text-amber-600" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-neutral-900 truncate">
                        {cert.skill ?? 'Certificate'}
                      </p>
                      <p className="text-sm text-neutral-500 mt-0.5">
                        {cert.source || cert.original_name || 'External course'}
                        {' · '}{formatDate(cert.uploaded_time)}
                      </p>
                      {cert.rejection_message && (
                        <p className="mt-1.5 text-xs leading-relaxed text-danger">
                          {cert.rejection_message}
                        </p>
                      )}
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <Badge variant={badge.variant} className="inline-flex items-center gap-1">
                        <Icon size={12} /> {cert.verified_status}
                      </Badge>
                      {cert.has_file ? (
                        <Button size="sm" variant="outline" onClick={() => openCertificate(cert)}>
                          <ExternalLink size={14} /> View
                        </Button>
                      ) : cert.cert_url ? (
                        <a href={cert.cert_url} target="_blank" rel="noopener noreferrer">
                          <Button size="sm" variant="outline">
                            <ExternalLink size={14} /> View
                          </Button>
                        </a>
                      ) : null}
                      {cert.verified_status === 'PENDING' && (
                        <Button
                          size="sm"
                          variant="outline"
                          className="text-danger border-danger/30 hover:bg-danger/5"
                          disabled={deletingId === cert.id}
                          onClick={() => deleteCertificate(cert.id)}
                        >
                          <Trash2 size={14} />
                          {deletingId === cert.id ? 'Removing…' : 'Withdraw'}
                        </Button>
                      )}
                    </div>
                  </Card>
                );
              })
            )}
          </div>
        )}
      </div>
    </Card>
  );
}
