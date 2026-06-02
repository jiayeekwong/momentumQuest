'use client';

import { useState, useCallback, useEffect, useRef } from 'react';
import { Plus, Bell, Users, Briefcase, GraduationCap, CheckCircle2, Bold, Italic, Underline, List, Link2, X, Trash2, Clock, FileText, ExternalLink, Paperclip, AlertTriangle, Upload } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { useEditor, EditorContent } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import UnderlineExt from '@tiptap/extension-underline';
import { DashboardLayout } from '@/src/components/Layout';
import { Card, Badge, Button, Input } from '@/src/components/ui';
import { cn } from '@/src/lib/utils';
import { apiFetch } from '@/src/lib/apiFetch';

// ─── Constants ────

const AUDIENCES = [
  { id: 'EVERYONE',  label: 'Everyone',       icon: Users,         desc: 'All students and companies' },
  { id: 'STUDENTS',  label: 'Students Only',  icon: GraduationCap, desc: 'Only student accounts' },
  { id: 'COMPANIES', label: 'Companies Only', icon: Briefcase,     desc: 'Only company accounts' },
];

const ALL_CATEGORIES = ['Career Event', 'Job Opportunity', 'Training', 'Platform Update', 'General'];

const AUDIENCE_LABELS: Record<string, string> = {
  EVERYONE: 'Everyone', STUDENTS: 'Students Only', COMPANIES: 'Companies Only',
};

// ─── Types ──────────

interface Announcement {
  id: number;
  title: string;
  message: string;
  categories: string[];
  audience: string;
  admin_name: string | null;
  supporting_doc: string | null;
  publish_time: string;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function isImageUrl(url: string): boolean {
  return /\.(jpg|jpeg|png|gif|webp|svg)(\?|$)/i.test(url);
}

// ─── Detail Modal ─────────────────────────────────────────────────────────────

function DetailModal({ announcement: a, onClose }: { announcement: Announcement; onClose: () => void }) {
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
          <div
            className="text-sm text-neutral-700 leading-relaxed announcement-body"
            dangerouslySetInnerHTML={{ __html: a.message }}
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

// ─── Create Form ─────────

function CreateForm({ onSuccess, onClose }: { onSuccess: (a: Announcement) => void; onClose: () => void }) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [, forceUpdate]  = useState(0);
  const [isPosting,    setIsPosting]    = useState(false);
  const [isUploading,  setIsUploading]  = useState(false);
  const [error,        setError]        = useState('');
  const [title,        setTitle]        = useState('');
  const [categories,   setCategories]   = useState<string[]>([]);
  const [audience,     setAudience]     = useState('EVERYONE');
  const [supportingDoc, setSupportingDoc] = useState('');
  const [uploadedName, setUploadedName] = useState<string | null>(null);

  const editor = useEditor({
    immediatelyRender: true,
    extensions: [StarterKit, UnderlineExt],
    content: '',
    editorProps: {
      attributes: {
        class: 'tiptap-editor focus:outline-none min-h-[140px] px-4 py-3 text-sm text-neutral-700 leading-relaxed',
      },
    },
    onUpdate:          () => forceUpdate(n => n + 1),
    onSelectionUpdate: () => forceUpdate(n => n + 1),
  });

  const toggleCategory = useCallback((cat: string) => {
    setCategories(prev => prev.includes(cat) ? prev.filter(c => c !== cat) : [...prev, cat]);
  }, []);

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setIsUploading(true);
    setError('');
    try {
      const fd = new FormData();
      fd.append('file', file);
      const res = await apiFetch('/api/dashboard/announcements/upload/', { method: 'POST', body: fd });
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
    const message = editor?.getHTML() ?? '';
    if (!message || message === '<p></p>') { setError('Announcement body cannot be empty.'); return; }

    setIsPosting(true);
    try {
      const res = await apiFetch('/api/dashboard/announcements/create/', {
        method: 'POST',
        body: JSON.stringify({
          title,
          message,
          audience,
          categories,
          supporting_doc: supportingDoc.trim() || null,
        }),
      });
      if (res.ok) {
        onSuccess(await res.json());
      } else {
        const data = await res.json().catch(() => ({}));
        setError(data.detail ?? JSON.stringify(data) ?? 'Failed to publish.');
      }
    } catch { setError('Network error. Please try again.'); }
    finally  { setIsPosting(false); }
  };

  const toolbarItems = [
    { icon: Bold,      label: 'Bold',      action: () => editor?.chain().focus().toggleBold().run(),       isActive: () => editor?.isActive('bold')       ?? false },
    { icon: Italic,    label: 'Italic',    action: () => editor?.chain().focus().toggleItalic().run(),     isActive: () => editor?.isActive('italic')     ?? false },
    { icon: Underline, label: 'Underline', action: () => editor?.chain().focus().toggleUnderline().run(),  isActive: () => editor?.isActive('underline')  ?? false },
    { icon: List,      label: 'Bullets',   action: () => editor?.chain().focus().toggleBulletList().run(), isActive: () => editor?.isActive('bulletList') ?? false },
  ];

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      <Input label="Announcement Title" placeholder="e.g. Career Fair 2026 — June Edition"
        value={title} onChange={e => setTitle(e.target.value)} required />

      {/* Category pills */}
      <div className="space-y-2">
        <label className="text-[10px] font-black text-neutral-900 uppercase tracking-widest block">
          Category <span className="text-neutral-400 normal-case font-normal">(select all that apply)</span>
        </label>
        <div className="flex flex-wrap gap-2">
          {ALL_CATEGORIES.map(cat => (
            <button key={cat} type="button" onClick={() => toggleCategory(cat)}
              className={cn('px-3 py-1.5 rounded-full text-xs font-bold border transition-all',
                categories.includes(cat) ? 'bg-primary text-white border-primary' : 'bg-white text-neutral-600 border-neutral-200 hover:border-primary/40')}>
              {cat}{categories.includes(cat) && <X size={10} className="inline ml-1.5 -mt-0.5" />}
            </button>
          ))}
        </div>
      </div>

      {/* Audience */}
      <div className="space-y-2">
        <label className="text-[10px] font-black text-neutral-900 uppercase tracking-widest block">Target Audience</label>
        <div className="grid grid-cols-3 gap-2">
          {AUDIENCES.map(a => (
            <div key={a.id} onClick={() => setAudience(a.id)}
              className={cn('p-3 border-2 rounded-xl cursor-pointer transition-all flex flex-col gap-1',
                audience === a.id ? 'border-primary bg-indigo-50/50' : 'border-neutral-100 hover:border-neutral-200')}>
              <a.icon className={audience === a.id ? 'text-primary' : 'text-neutral-400'} size={16} />
              <span className={cn('text-xs font-bold', audience === a.id ? 'text-primary' : 'text-neutral-900')}>{a.label}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Rich-text body */}
      <div className="space-y-1">
        <label className="text-[10px] font-black text-neutral-900 uppercase tracking-widest block">Announcement Body</label>
        <div className="flex items-center gap-1 p-1.5 bg-neutral-50 border border-neutral-200 rounded-t-xl border-b-0">
          {toolbarItems.map(({ icon: Icon, label, action, isActive }) => (
            <button key={label} type="button" onClick={action} title={label}
              className={cn('w-7 h-7 flex items-center justify-center rounded-lg transition-colors',
                isActive() ? 'bg-primary text-white' : 'text-neutral-500 hover:bg-neutral-200')}>
              <Icon size={14} />
            </button>
          ))}
        </div>
        <div className="border border-neutral-300 rounded-b-xl bg-white focus-within:ring-2 focus-within:ring-primary/20">
          <EditorContent editor={editor} />
        </div>
      </div>

      {/* Supporting document — URL paste OR upload from computer */}
      <div className="space-y-2">
        <label className="text-[10px] font-black text-neutral-900 uppercase tracking-widest block">
          Supporting Document <span className="text-neutral-400 normal-case font-normal">(optional)</span>
        </label>

        {/* URL input row with Upload button */}
        <div className="flex gap-2">
          <div className="relative flex-1">
            <Link2 size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400" />
            <input
              type="url"
              value={supportingDoc}
              onChange={e => { setSupportingDoc(e.target.value); setUploadedName(null); }}
              placeholder="Paste a URL  or  upload from computer"
              className="w-full h-10 pl-9 pr-4 border border-neutral-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
            />
          </div>
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={isUploading}
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

        {/* Uploaded file chip */}
        {uploadedName && (
          <div className="flex items-center gap-2 px-3 py-1.5 bg-emerald-50 border border-emerald-200 rounded-lg w-fit">
            <CheckCircle2 size={13} className="text-success shrink-0" />
            <span className="text-xs font-semibold text-success truncate max-w-xs">{uploadedName} uploaded</span>
            <button type="button" onClick={() => { setSupportingDoc(''); setUploadedName(null); }}
              className="text-success/60 hover:text-success ml-1"><X size={12} /></button>
          </div>
        )}

        {/* Live image preview for URL or uploaded image */}
        {supportingDoc && isImageUrl(supportingDoc) && (
          <div className="border border-neutral-200 rounded-xl overflow-hidden">
            <img src={supportingDoc} alt="Preview" className="w-full max-h-48 object-contain bg-neutral-50"
              onError={e => (e.currentTarget.style.display = 'none')} />
          </div>
        )}
      </div>

      {error && <p className="text-sm text-danger font-semibold bg-danger/5 border border-danger/20 rounded-lg px-3 py-2">{error}</p>}

      <div className="flex gap-3 pt-1">
        <Button type="button" variant="outline" fullWidth onClick={onClose}>Cancel</Button>
        <Button type="submit" fullWidth disabled={isPosting}>
          <Bell size={15} className="mr-2" />{isPosting ? 'Publishing…' : 'Publish'}
        </Button>
      </div>
    </form>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function AnnouncementsPage() {
  const [announcements,   setAnnouncements]   = useState<Announcement[]>([]);
  const [isLoading,       setIsLoading]       = useState(true);
  const [createOpen,      setCreateOpen]      = useState(false);
  const [detailItem,      setDetailItem]      = useState<Announcement | null>(null);
  const [deletingId,      setDeletingId]      = useState<number | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null);
  const [justCreated,     setJustCreated]     = useState<number | null>(null);

  useEffect(() => {
    apiFetch('/api/dashboard/announcements/')
      .then(r => r.json())
      .then(data => setAnnouncements(Array.isArray(data) ? data : []))
      .catch(() => {})
      .finally(() => setIsLoading(false));
  }, []);

  const handleCreated = (a: Announcement) => {
    setAnnouncements(prev => [a, ...prev]);
    setCreateOpen(false);
    setJustCreated(a.id);
    setTimeout(() => setJustCreated(null), 3000);
  };

  const handleDelete = async (id: number) => {
    setConfirmDeleteId(null);
    setDeletingId(id);
    try {
      const res = await apiFetch(`/api/dashboard/announcements/${id}/`, { method: 'DELETE' });
      if (res.status === 204 || res.ok) {
        setAnnouncements(prev => prev.filter(a => a.id !== id));
        if (detailItem?.id === id) setDetailItem(null);
      }
    } catch { /* silent */ }
    finally { setDeletingId(null); }
  };

  return (
    <DashboardLayout title="Announcements">
      <div className="max-w-4xl mx-auto space-y-6">

        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-bold text-neutral-900">Announcements</h2>
            <p className="text-neutral-500 mt-1 text-sm">Broadcast important updates to platform users.</p>
          </div>
          <Button className="h-11 px-5 flex items-center gap-2" onClick={() => setCreateOpen(true)}>
            <Plus size={18} /> New Announcement
          </Button>
        </div>

        {/* Success flash */}
        <AnimatePresence>
          {justCreated !== null && (
            <motion.div key="flash" initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
              className="flex items-center gap-3 px-4 py-3 bg-emerald-50 border border-emerald-200 rounded-xl">
              <CheckCircle2 size={18} className="text-success shrink-0" />
              <p className="text-sm font-bold text-success">Announcement published successfully!</p>
            </motion.div>
          )}
        </AnimatePresence>

        {/* List */}
        {isLoading ? (
          <div className="space-y-4">
            {[1, 2, 3].map(i => <div key={i} className="h-32 bg-neutral-100 animate-pulse rounded-2xl" />)}
          </div>
        ) : announcements.length > 0 ? (
          <div className="space-y-4">
            {announcements.map(a => (
              <Card key={a.id} className={cn('p-6 transition-all', justCreated === a.id && 'border-emerald-300 bg-emerald-50/20')}>
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex flex-wrap items-center gap-2 mb-2">
                      {a.categories?.map(cat => (
                        <Badge key={cat} variant="primary" className="text-[9px] font-black tracking-widest">{cat}</Badge>
                      ))}
                      <Badge variant="neutral" className="text-[9px] font-black tracking-widest">
                        {AUDIENCE_LABELS[a.audience] ?? a.audience}
                      </Badge>
                    </div>

                    <button type="button" onClick={() => setDetailItem(a)}
                      className="text-left font-bold text-neutral-900 text-base leading-tight hover:text-primary transition-colors hover:underline underline-offset-2">
                      {a.title}
                    </button>

                    <div
                      className="text-sm text-neutral-500 mt-2 leading-relaxed announcement-body line-clamp-2"
                      dangerouslySetInnerHTML={{ __html: a.message }}
                    />

                    <div className="flex items-center gap-3 mt-2">
                      {a.supporting_doc && (
                        <span className="flex items-center gap-1 text-[10px] text-primary font-semibold">
                          <Paperclip size={10} /> Attachment
                        </span>
                      )}
                      <p className="text-[10px] text-neutral-400 font-medium flex items-center gap-1">
                        <Clock size={10} /> {timeAgo(a.publish_time)} · by {a.admin_name ?? 'Admin'}
                      </p>
                    </div>
                  </div>

                  <button
                    disabled={deletingId === a.id}
                    onClick={() => setConfirmDeleteId(a.id)}
                    className="w-9 h-9 shrink-0 flex items-center justify-center rounded-xl border border-neutral-200 text-neutral-400 hover:border-danger/40 hover:text-danger hover:bg-danger/5 transition-all disabled:opacity-40">
                    {deletingId === a.id
                      ? <div className="w-4 h-4 border-2 border-danger/30 border-t-danger rounded-full animate-spin" />
                      : <Trash2 size={15} />}
                  </button>
                </div>
              </Card>
            ))}
          </div>
        ) : (
          <div className="py-24 text-center">
            <Bell size={48} className="mx-auto text-neutral-200 mb-4" />
            <h3 className="text-lg font-bold text-neutral-900">No announcements yet</h3>
            <p className="text-neutral-400 text-sm mt-1">Click <strong>New Announcement</strong> to post one.</p>
          </div>
        )}
      </div>

      {/* Detail modal */}
      <AnimatePresence>
        {detailItem && <DetailModal announcement={detailItem} onClose={() => setDetailItem(null)} />}
      </AnimatePresence>

      {/* Custom delete confirmation modal */}
      <AnimatePresence>
        {confirmDeleteId !== null && (
          <motion.div key="confirm-delete"
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm px-4">
            <motion.div
              initial={{ scale: 0.92, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.92, opacity: 0 }}
              transition={{ type: 'spring', stiffness: 320, damping: 28 }}
              className="bg-white rounded-2xl shadow-2xl w-full max-w-sm p-7">
              <div className="flex flex-col items-center text-center gap-4">
                <div className="w-14 h-14 rounded-full bg-danger/10 flex items-center justify-center text-danger">
                  <AlertTriangle size={28} />
                </div>
                <div>
                  <h3 className="text-lg font-black text-neutral-900">Delete Announcement?</h3>
                  <p className="text-sm text-neutral-500 mt-1 leading-relaxed">
                    This action cannot be undone. The announcement will be permanently removed for all users.
                  </p>
                </div>
                <div className="flex gap-3 w-full pt-1">
                  <Button variant="outline" fullWidth onClick={() => setConfirmDeleteId(null)}>
                    Cancel
                  </Button>
                  <Button
                    fullWidth
                    className="bg-danger hover:bg-danger/90 text-white"
                    onClick={() => handleDelete(confirmDeleteId)}>
                    <Trash2 size={15} className="mr-2" /> Delete
                  </Button>
                </div>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Create modal */}
      <AnimatePresence>
        {createOpen && (
          <motion.div key="create-modal"
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm px-4 py-8 overflow-y-auto">
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.95, opacity: 0 }}
              transition={{ type: 'spring', stiffness: 300, damping: 30 }}
              className="bg-white rounded-2xl shadow-2xl w-full max-w-xl p-8 my-auto">
              <div className="flex items-center justify-between mb-6">
                <h3 className="text-xl font-black text-neutral-900">New Announcement</h3>
                <button onClick={() => setCreateOpen(false)}
                  className="w-8 h-8 flex items-center justify-center rounded-lg hover:bg-neutral-100">
                  <X size={18} />
                </button>
              </div>
              <CreateForm onSuccess={handleCreated} onClose={() => setCreateOpen(false)} />
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </DashboardLayout>
  );
}
