'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { GraduationCap, Clock, CheckCircle2, XCircle, AlertCircle, BookOpen, Link2, Upload, X, FileText, ExternalLink, ArrowLeft } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { DashboardLayout } from '@/src/components/Layout';
import { Card, Badge, Button, Input } from '@/src/components/ui';
import { RichTextEditor } from '@/src/components/RichTextEditor';
import { apiFetch } from '@/src/lib/apiFetch';
import { cn } from '@/src/lib/utils';

interface TrainingProgramme {
  id: number;
  title: string;
  skill: string | null;
  programme_duration: string;
  description: string;
  supporting_doc: string | null;
  approval_status: 'PENDING' | 'APPROVED' | 'REJECTED';
  submission_time: string;
}

const statusConfig = {
  PENDING:  { variant: 'warning'  as const, icon: AlertCircle,   label: 'Pending Review' },
  APPROVED: { variant: 'success'  as const, icon: CheckCircle2,  label: 'Approved' },
  REJECTED: { variant: 'danger'   as const, icon: XCircle,       label: 'Rejected' },
};

function isImageUrl(url: string): boolean {
  return /\.(jpg|jpeg|png|gif|webp|svg)(\?|$)/i.test(url);
}

function formatDate(d: string) {
  return new Date(d).toLocaleDateString('en-MY', { day: 'numeric', month: 'short', year: 'numeric' });
}

// ─── Detail Modal ──────────────────────────────────────────────────────────────

function DetailModal({ programme: p, onClose }: { programme: TrainingProgramme; onClose: () => void }) {
  const config = statusConfig[p.approval_status];
  const Icon = config.icon;
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

        <div className="flex items-start justify-between gap-4 p-7 border-b border-neutral-100">
          <div className="flex-1 min-w-0">
            <div className="flex flex-wrap items-center gap-2 mb-3">
              {p.skill && <Badge variant="primary" className="text-[9px] font-black tracking-widest">{p.skill}</Badge>}
              <Badge variant={config.variant} className="flex items-center gap-1.5 text-[9px] font-black tracking-widest">
                <Icon size={11} /> {config.label}
              </Badge>
            </div>
            <h2 className="text-xl font-black text-neutral-900 leading-tight">{p.title}</h2>
            <div className="flex flex-wrap items-center gap-4 mt-2 text-[11px] text-neutral-400 font-medium">
              {p.programme_duration && <span className="flex items-center gap-1"><Clock size={11} /> {p.programme_duration}</span>}
              <span>Submitted {formatDate(p.submission_time)}</span>
            </div>
          </div>
          <button onClick={onClose} className="w-8 h-8 shrink-0 flex items-center justify-center rounded-lg hover:bg-neutral-100 text-neutral-400">
            <X size={18} />
          </button>
        </div>

        <div className="p-7 space-y-5">
          {p.description ? (
            <div className="text-sm text-neutral-700 leading-relaxed rich-text"
              dangerouslySetInnerHTML={{ __html: p.description }} />
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
                    <p className="text-sm font-bold text-neutral-900">Attached Document</p>
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

export default function PostTrainingPage() {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formOpen, setFormOpen] = useState(false);

  const [title, setTitle] = useState('');
  const [skillName, setSkillName] = useState('');
  const [duration, setDuration] = useState('');
  const [description, setDescription] = useState('');
  const [supportingDoc, setSupportingDoc] = useState('');
  const [uploadedName, setUploadedName] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);

  const [programmes, setProgrammes] = useState<TrainingProgramme[]>([]);
  const [isLoadingList, setIsLoadingList] = useState(true);
  const [detailItem, setDetailItem] = useState<TrainingProgramme | null>(null);

  const fetchProgrammes = useCallback(() => {
    apiFetch('/api/resources/training/')
      .then(r => r.json())
      .then(data => setProgrammes(Array.isArray(data) ? data : []))
      .catch(() => {})
      .finally(() => setIsLoadingList(false));
  }, []);

  useEffect(() => { fetchProgrammes(); }, [fetchProgrammes]);

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setIsUploading(true);
    setError('');
    try {
      const fd = new FormData();
      fd.append('file', file);
      const res = await apiFetch('/api/resources/training/upload/', { method: 'POST', body: fd });
      if (res.ok) {
        const { url } = await res.json();
        setSupportingDoc(url);
        setUploadedName(file.name);
      } else {
        setError('File upload failed. Please try again.');
      }
    } catch {
      setError('Upload error. Please try again.');
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setIsSubmitting(true);

    try {
      const res = await apiFetch('/api/resources/training/', {
        method: 'POST',
        body: JSON.stringify({
          title,
          description,
          skill_name:         skillName.trim() || undefined,
          programme_duration: duration,
          supporting_doc:     supportingDoc.trim() || null,
        }),
      });

      if (res.status === 201) {
        const newProgramme = await res.json();
        setProgrammes(prev => [newProgramme, ...prev]);
        setSubmitted(true);
        setTimeout(() => {
          setSubmitted(false);
          setFormOpen(false);
          setTitle('');
          setSkillName('');
          setDuration('');
          setDescription('');
          setSupportingDoc('');
          setUploadedName(null);
        }, 2500);
      } else {
        const data = await res.json();
        setError(JSON.stringify(data));
      }
    } catch {
      setError('Network error. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <DashboardLayout title="Post Training">
      <div className="max-w-3xl mx-auto space-y-10">

        {/* ── My Submissions ── */}
        <div>
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <BookOpen size={18} className="text-primary" />
              <h3 className="text-lg font-bold text-neutral-900">My Submissions</h3>
              <span className="text-xs font-bold text-neutral-400">{programmes.length} total</span>
            </div>
            <Button
              size="sm"
              onClick={() => setFormOpen(!formOpen)}
              className="h-9 text-xs"
            >
              <GraduationCap size={14} className="mr-1.5" />
              {formOpen ? 'Cancel' : 'Post Training Programme'}
            </Button>
          </div>

          {isLoadingList ? (
            <div className="flex items-center justify-center py-12">
              <div className="w-7 h-7 border-4 border-primary/20 border-t-primary rounded-full animate-spin" />
            </div>
          ) : programmes.length === 0 ? (
            <Card className="p-10 text-center">
              <GraduationCap size={36} className="mx-auto text-neutral-200 mb-3" />
              <p className="text-sm font-bold text-neutral-500">No submissions yet</p>
              <p className="text-xs text-neutral-400 mt-1">Programmes you submit will appear here with their review status.</p>
            </Card>
          ) : (
            <div className="space-y-3">
              {programmes.map(prog => {
                const config = statusConfig[prog.approval_status];
                const Icon = config.icon;
                return (
                  <Card key={prog.id} className="p-5">
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-3 flex-wrap">
                          <button type="button" onClick={() => setDetailItem(prog)}
                            className="text-left font-bold text-neutral-900 truncate hover:text-primary hover:underline underline-offset-2 transition-colors">
                            {prog.title}
                          </button>
                          {prog.skill && (
                            <span className="px-2 py-0.5 bg-indigo-50 text-primary rounded-full text-[10px] font-bold">
                              {prog.skill}
                            </span>
                          )}
                          {prog.supporting_doc && (
                            <span className="flex items-center gap-1 text-[10px] text-primary font-semibold">
                              <FileText size={10} /> Attachment
                            </span>
                          )}
                        </div>
                        <div className="flex flex-wrap items-center gap-4 mt-2 text-xs font-semibold text-neutral-500">
                          {prog.programme_duration && (
                            <span className="flex items-center gap-1">
                              <Clock size={11} /> {prog.programme_duration}
                            </span>
                          )}
                          <span>Submitted {formatDate(prog.submission_time)}</span>
                        </div>
                        {prog.description && (
                          <div className="text-xs text-neutral-400 mt-2 line-clamp-2 rich-text"
                            dangerouslySetInnerHTML={{ __html: prog.description }} />
                        )}
                      </div>
                      <div className="shrink-0">
                        <Badge variant={config.variant} className={cn('flex items-center gap-1.5 px-3 py-1.5 text-[10px] font-black tracking-widest')}>
                          <Icon size={12} /> {config.label}
                        </Badge>
                      </div>
                    </div>
                  </Card>
                );
              })}
            </div>
          )}
        </div>

        {/* ── Form Modal ── */}
        <AnimatePresence>
          {formOpen && (
            <motion.div key="form-backdrop"
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm px-4 py-8 overflow-y-auto"
              onClick={() => setFormOpen(false)}>
              <motion.div
                initial={{ scale: 0.95, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.95, opacity: 0 }}
                transition={{ type: 'spring', stiffness: 300, damping: 30 }}
                className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl my-auto"
                onClick={e => e.stopPropagation()}>

                <div className="flex items-center justify-between gap-4 p-7 border-b border-neutral-100">
                  <h2 className="text-2xl font-bold text-neutral-900">Submit a Training Programme</h2>
                  <button onClick={() => setFormOpen(false)} className="w-8 h-8 shrink-0 flex items-center justify-center rounded-lg hover:bg-neutral-100 text-neutral-400">
                    <X size={20} />
                  </button>
                </div>

                <div className="p-7 overflow-y-auto max-h-[calc(100vh-200px)]">
                  {error && (
                    <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-xl text-sm text-red-700 font-medium">
                      {error}
                    </div>
                  )}
                  <form onSubmit={handleSubmit} className="space-y-6">
                    <Input label="Programme Title" placeholder="e.g. React Web Development Bootcamp" value={title}
                      onChange={e => setTitle(e.target.value)} required />

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                      <Input label="Related Skill" placeholder="e.g. React, Python, SQL" value={skillName}
                        onChange={e => setSkillName(e.target.value)} />
                      <Input label="Duration" placeholder="e.g. 6 weeks / 40 hours" value={duration}
                        onChange={e => setDuration(e.target.value)} icon={<Clock size={16} />} required />
                    </div>

                    <div className="space-y-2">
                      <label className="text-[10px] font-black text-neutral-900 uppercase tracking-widest block">Description</label>
                      <RichTextEditor value={description} onChange={setDescription} />
                    </div>

                    {/* Attachment — URL paste OR upload from computer */}
                    <div className="space-y-2">
                      <label className="text-[10px] font-black text-neutral-900 uppercase tracking-widest block">
                        Attachment <span className="text-neutral-400 normal-case font-normal">(optional)</span>
                      </label>
                      <div className="flex gap-2">
                        <div className="relative flex-1">
                          <Link2 size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400" />
                          <input type="url" value={supportingDoc}
                            onChange={e => { setSupportingDoc(e.target.value); setUploadedName(null); }}
                            placeholder="Paste a URL  or  upload from computer →"
                            className="w-full h-10 pl-9 pr-4 border border-neutral-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20" />
                        </div>
                        <button type="button" onClick={() => fileInputRef.current?.click()} disabled={isUploading}
                          className="h-10 px-4 shrink-0 flex items-center gap-2 rounded-lg border border-neutral-300 bg-neutral-50 text-xs font-bold text-neutral-600 hover:border-primary/40 hover:text-primary hover:bg-indigo-50/50 transition-all disabled:opacity-50">
                          {isUploading
                            ? <div className="w-3.5 h-3.5 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
                            : <Upload size={14} />}
                          {isUploading ? 'Uploading…' : 'Upload'}
                        </button>
                        <input ref={fileInputRef} type="file" className="hidden"
                          accept=".pdf,.doc,.docx,.ppt,.pptx,.jpg,.jpeg,.png,.gif,.webp"
                          onChange={handleFileUpload} />
                      </div>
                      {uploadedName && (
                        <div className="flex items-center gap-2 px-3 py-1.5 bg-emerald-50 border border-emerald-200 rounded-lg w-fit">
                          <CheckCircle2 size={13} className="text-success shrink-0" />
                          <span className="text-xs font-semibold text-success truncate max-w-xs">{uploadedName} uploaded</span>
                          <button type="button" onClick={() => { setSupportingDoc(''); setUploadedName(null); }}
                            className="text-success/60 hover:text-success ml-1"><X size={12} /></button>
                        </div>
                      )}
                      {supportingDoc && isImageUrl(supportingDoc) && (
                        <div className="border border-neutral-200 rounded-xl overflow-hidden">
                          <img src={supportingDoc} alt="Preview" className="w-full max-h-48 object-contain bg-neutral-50"
                            onError={e => (e.currentTarget.style.display = 'none')} />
                        </div>
                      )}
                    </div>

                    <div className="flex gap-4 pt-4">
                      <Button type="button" variant="outline" fullWidth onClick={() => setFormOpen(false)}>Cancel</Button>
                      <Button type="submit" fullWidth disabled={isSubmitting}>
                        <GraduationCap size={16} className="mr-2" /> {isSubmitting ? 'Submitting...' : 'Submit'}
                      </Button>
                    </div>
                  </form>
                </div>
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Success Message */}
        <AnimatePresence>
          {submitted && (
            <motion.div key="success"
              initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.95 }}
              className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
              <motion.div className="bg-white rounded-2xl shadow-2xl p-16 text-center max-w-md w-full mx-4">
                <div className="w-24 h-24 bg-emerald-50 text-success rounded-full flex items-center justify-center mx-auto mb-6">
                  <CheckCircle2 size={48} />
                </div>
                <h3 className="text-2xl font-black text-neutral-900">Training Submitted!</h3>
                <p className="text-neutral-500 mt-2">Your programme is pending admin approval.</p>
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>

      </div>

      {/* Detail modal */}
      <AnimatePresence>
        {detailItem && <DetailModal programme={detailItem} onClose={() => setDetailItem(null)} />}
      </AnimatePresence>
    </DashboardLayout>
  );
}
