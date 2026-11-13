'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  CheckCircle2, Clock, Edit3, Link2, Megaphone, Plus,
  Send, Trash2, Upload, X, XCircle,
} from 'lucide-react';
import { AnimatePresence, motion } from 'motion/react';

import { isImageUrl } from '@/src/components/AnnouncementDetailModal';
import { DashboardLayout } from '@/src/components/Layout';
import { RichTextEditor } from '@/src/components/RichTextEditor';
import { Badge, Button, Card, Input } from '@/src/components/ui';
import { apiFetch } from '@/src/lib/apiFetch';
import { RichText } from '@/src/lib/richText';
import { cn } from '@/src/lib/utils';

type ApprovalStatus = 'PENDING' | 'APPROVED' | 'REJECTED' | 'WITHDRAWN';

interface CompanyAnnouncement {
  id: number;
  title: string;
  message: string;
  categories: string[];
  audience: 'STUDENTS';
  supporting_doc: string | null;
  approval_status: ApprovalStatus;
  rejection_reason: string;
  submitted_at: string;
  reviewed_at: string | null;
  publish_time: string | null;
}

const CATEGORIES = ['Career Event', 'Job Opportunity', 'Training', 'General'];

const STATUS_STYLE: Record<ApprovalStatus, {
  label: string;
  variant: 'warning' | 'success' | 'danger' | 'neutral';
  icon: typeof Clock;
}> = {
  PENDING: { label: 'Pending review', variant: 'warning', icon: Clock },
  APPROVED: { label: 'Published', variant: 'success', icon: CheckCircle2 },
  REJECTED: { label: 'Changes required', variant: 'danger', icon: XCircle },
  WITHDRAWN: { label: 'Withdrawn', variant: 'neutral', icon: Trash2 },
};

function readableError(data: Record<string, unknown> | null, fallback: string) {
  if (!data) return fallback;
  if (typeof data.detail === 'string') return data.detail;
  for (const value of Object.values(data)) {
    if (Array.isArray(value) && typeof value[0] === 'string') return value[0];
  }
  return fallback;
}

export default function CompanyAnnouncementsPage() {
  const fileInput = useRef<HTMLInputElement>(null);
  const [items, setItems] = useState<CompanyAnnouncement[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [formOpen, setFormOpen] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);
  const [title, setTitle] = useState('');
  const [message, setMessage] = useState('');
  const [categories, setCategories] = useState<string[]>([]);
  const [supportingDoc, setSupportingDoc] = useState('');
  const [attachmentReceipt, setAttachmentReceipt] = useState('');
  const [uploadedName, setUploadedName] = useState('');
  const [error, setError] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const [isUploading, setIsUploading] = useState(false);

  const fetchItems = useCallback(async () => {
    try {
      const res = await apiFetch('/api/dashboard/company/announcements/');
      if (res.ok) {
        const data = await res.json();
        setItems(Array.isArray(data) ? data : data.results ?? []);
      }
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => { void fetchItems(); }, [fetchItems]);

  const resetForm = () => {
    setEditId(null);
    setTitle('');
    setMessage('');
    setCategories([]);
    setSupportingDoc('');
    setAttachmentReceipt('');
    setUploadedName('');
    setError('');
  };

  const openCreate = () => {
    resetForm();
    setFormOpen(true);
  };

  const closeForm = () => {
    setFormOpen(false);
    resetForm();
  };

  const openEdit = (item: CompanyAnnouncement) => {
    setEditId(item.id);
    setTitle(item.title);
    setMessage(item.message);
    setCategories(item.categories ?? []);
    setSupportingDoc(item.supporting_doc ?? '');
    setAttachmentReceipt('');
    setUploadedName(item.supporting_doc ? 'Existing attachment' : '');
    setError('');
    setFormOpen(true);
  };

  const uploadAttachment = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setIsUploading(true);
    setError('');
    try {
      const body = new FormData();
      body.append('file', file);
      const res = await apiFetch('/api/dashboard/announcements/upload/', {
        method: 'POST', body,
      });
      const data = await res.json().catch(() => null);
      if (!res.ok) {
        setError(readableError(data, 'Could not upload the attachment.'));
        return;
      }
      setSupportingDoc(data.url);
      setAttachmentReceipt(data.attachment_receipt);
      setUploadedName(file.name);
    } catch {
      setError('Network error while uploading. Please try again.');
    } finally {
      setIsUploading(false);
      if (fileInput.current) fileInput.current.value = '';
    }
  };

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!message || message === '<p></p>') {
      setError('Announcement body cannot be empty.');
      return;
    }
    setIsSaving(true);
    setError('');
    try {
      const res = await apiFetch(
        editId
          ? `/api/dashboard/company/announcements/${editId}/`
          : '/api/dashboard/company/announcements/',
        {
          method: editId ? 'PATCH' : 'POST',
          body: JSON.stringify({
            title,
            message,
            categories,
            supporting_doc: supportingDoc.trim() || null,
            attachment_receipt: attachmentReceipt || undefined,
          }),
        },
      );
      const data = await res.json().catch(() => null);
      if (!res.ok) {
        setError(readableError(data, 'Could not submit the announcement.'));
        return;
      }
      setItems(current => editId
        ? current.map(item => item.id === editId ? data : item)
        : [data, ...current]);
      setFormOpen(false);
      resetForm();
    } catch {
      setError('Network error. Please try again.');
    } finally {
      setIsSaving(false);
    }
  };

  const withdraw = async (item: CompanyAnnouncement) => {
    if (!window.confirm(`Withdraw "${item.title}"?`)) return;
    const res = await apiFetch(
      `/api/dashboard/company/announcements/${item.id}/`, { method: 'DELETE' });
    if (res.ok) {
      setItems(current => current.map(row => row.id === item.id
        ? { ...row, approval_status: 'WITHDRAWN', supporting_doc: null }
        : row));
    } else {
      const data = await res.json().catch(() => null);
      setError(readableError(data, 'Could not withdraw the announcement.'));
    }
  };

  return (
    <DashboardLayout title="Company Announcements">
      <div className="max-w-4xl mx-auto space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h2 className="text-2xl font-bold text-neutral-900">Announcements for Students</h2>
            <p className="text-sm text-neutral-500 mt-1">
              Submit an announcement for administrator review before students can see it.
            </p>
          </div>
          <Button onClick={openCreate}>
            <Plus size={16} className="mr-2" /> New Announcement
          </Button>
        </div>

        {error && !formOpen && (
          <div role="alert" className="p-4 rounded-xl border border-red-200 bg-red-50 text-sm font-medium text-red-700">
            {error}
          </div>
        )}

        {isLoading ? (
          <div className="flex justify-center py-16">
            <div className="w-8 h-8 border-4 border-primary/20 border-t-primary rounded-full animate-spin" />
          </div>
        ) : items.length === 0 ? (
          <Card className="p-12 text-center">
            <Megaphone size={36} className="mx-auto text-neutral-200 mb-3" />
            <p className="font-bold text-neutral-700">No announcement submissions yet</p>
          </Card>
        ) : (
          <div className="space-y-3">
            {items.map(item => {
              const config = STATUS_STYLE[item.approval_status];
              const Icon = config.icon;
              const editable = item.approval_status === 'PENDING' || item.approval_status === 'REJECTED';
              return (
                <Card key={item.id} className="p-5">
                  <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="font-bold text-neutral-900">{item.title}</h3>
                        <Badge
                          variant={config.variant}
                          className="inline-flex items-center gap-1 whitespace-nowrap text-[9px] font-black tracking-widest"
                        >
                          <Icon size={11} className="shrink-0" />
                          {config.label}
                        </Badge>
                      </div>
                      <p className="text-[11px] text-neutral-400 mt-1">
                        Submitted {new Date(item.submitted_at).toLocaleDateString('en-MY')}
                      </p>
                      <RichText className="text-sm text-neutral-600 mt-3 line-clamp-3" html={item.message} />
                      {item.rejection_reason && (
                        <p className="mt-3 p-3 bg-red-50 border border-red-100 rounded-lg text-xs text-red-700">
                          <strong>Review note:</strong> {item.rejection_reason}
                        </p>
                      )}
                    </div>
                    {editable && (
                      <div className="flex gap-2 shrink-0">
                        <Button size="sm" variant="outline" onClick={() => openEdit(item)}>
                          <Edit3 size={13} className="mr-1.5" /> Edit
                        </Button>
                        <Button size="sm" variant="outline"
                          className="text-danger border-danger/20"
                          onClick={() => withdraw(item)}>
                          <Trash2 size={13} className="mr-1.5" /> Withdraw
                        </Button>
                      </div>
                    )}
                  </div>
                </Card>
              );
            })}
          </div>
        )}
      </div>

      <AnimatePresence>
        {formOpen && (
          <motion.div
            key="company-announcement-form"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-black/40 px-4 py-8 backdrop-blur-sm"
          >
            <motion.div
              role="dialog"
              aria-modal="true"
              aria-labelledby="company-announcement-form-title"
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              transition={{ type: 'spring', stiffness: 300, damping: 30 }}
              className="my-auto w-full max-w-xl rounded-2xl bg-white p-8 shadow-2xl"
            >
              <div className="mb-6 flex items-start justify-between gap-4">
                <div>
                  <h3 id="company-announcement-form-title" className="text-xl font-black text-neutral-900">
                    {editId ? 'Revise Announcement' : 'New Announcement'}
                  </h3>
                  <p className="mt-1 text-xs text-neutral-500">
                    Student accounts only. Administrator approval is required before publication.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={closeForm}
                  aria-label="Close announcement form"
                  className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-neutral-500 hover:bg-neutral-100"
                >
                  <X size={18} />
                </button>
              </div>

              <form onSubmit={submit} className="space-y-5">
                <Input
                  label="Announcement Title"
                  placeholder="e.g. Career Fair 2026 — June Edition"
                  value={title}
                  onChange={event => setTitle(event.target.value)}
                  maxLength={200}
                  required
                />

                <div className="space-y-2">
                  <label className="block text-[10px] font-black uppercase tracking-widest text-neutral-900">
                    Category <span className="font-normal normal-case text-neutral-400">(select all that apply)</span>
                  </label>
                  <div className="flex flex-wrap gap-2">
                    {CATEGORIES.map(category => (
                      <button
                        key={category}
                        type="button"
                        onClick={() => setCategories(current => current.includes(category)
                          ? current.filter(value => value !== category)
                          : [...current, category])}
                        className={cn(
                          'rounded-full border px-3 py-1.5 text-xs font-bold transition-all',
                          categories.includes(category)
                            ? 'border-primary bg-primary text-white'
                            : 'border-neutral-200 bg-white text-neutral-600 hover:border-primary/40',
                        )}
                      >
                        {category}
                        {categories.includes(category) && <X size={10} className="ml-1.5 -mt-0.5 inline" />}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="space-y-1">
                  <label className="block text-[10px] font-black uppercase tracking-widest text-neutral-900">
                    Announcement Body
                  </label>
                  <RichTextEditor value={message} onChange={setMessage} minHeight={140} />
                </div>

                <div className="space-y-2">
                  <label className="block text-[10px] font-black uppercase tracking-widest text-neutral-900">
                    Supporting Document <span className="font-normal normal-case text-neutral-400">(optional)</span>
                  </label>
                  <div className="flex gap-2">
                    <div className="relative flex-1">
                      <Link2
                        size={15}
                        className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400"
                        aria-hidden="true"
                      />
                      <input
                        type="url"
                        value={supportingDoc}
                        onChange={event => {
                          setSupportingDoc(event.target.value);
                          setAttachmentReceipt('');
                          setUploadedName('');
                        }}
                        placeholder="Paste a URL or upload from computer"
                        className="h-10 w-full rounded-lg border border-neutral-300 pl-9 pr-4 text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
                      />
                    </div>
                    <button
                      type="button"
                      onClick={() => fileInput.current?.click()}
                      disabled={isUploading}
                      className="flex h-10 shrink-0 items-center gap-2 rounded-lg border border-neutral-300 bg-neutral-50 px-4 text-xs font-bold text-neutral-600 transition-all hover:border-primary/40 hover:bg-indigo-50/50 hover:text-primary disabled:opacity-50"
                    >
                      {isUploading
                        ? <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-primary/30 border-t-primary" />
                        : <Upload size={14} />}
                      {isUploading ? 'Uploading…' : 'Upload'}
                    </button>
                    <input
                      ref={fileInput}
                      type="file"
                      className="hidden"
                      accept=".pdf,.png,.jpg,.jpeg"
                      onChange={uploadAttachment}
                    />
                  </div>

                  {uploadedName && (
                    <div className="flex w-fit items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-1.5">
                      <CheckCircle2 size={13} className="shrink-0 text-success" />
                      <span className="max-w-xs truncate text-xs font-semibold text-success">
                        {uploadedName}{uploadedName === 'Existing attachment' ? '' : ' uploaded'}
                      </span>
                      <button
                        type="button"
                        aria-label="Remove supporting document"
                        onClick={() => {
                          setSupportingDoc('');
                          setAttachmentReceipt('');
                          setUploadedName('');
                        }}
                        className="ml-1 text-success/60 hover:text-success"
                      >
                        <X size={12} />
                      </button>
                    </div>
                  )}

                  {supportingDoc && isImageUrl(supportingDoc) && (
                    <div className="overflow-hidden rounded-xl border border-neutral-200">
                      <img
                        src={supportingDoc}
                        alt="Supporting document preview"
                        className="max-h-48 w-full bg-neutral-50 object-contain"
                        onError={event => { event.currentTarget.style.display = 'none'; }}
                      />
                    </div>
                  )}
                </div>

                {error && (
                  <p role="alert" className="rounded-lg border border-danger/20 bg-danger/5 px-3 py-2 text-sm font-semibold text-danger">
                    {error}
                  </p>
                )}

                <div className="flex gap-3 pt-1">
                  <Button type="button" variant="outline" fullWidth onClick={closeForm}>
                    Cancel
                  </Button>
                  <Button type="submit" fullWidth disabled={isSaving || isUploading}>
                    <Send size={14} className="mr-2" />
                    {isSaving ? 'Submitting…' : 'Submit for Review'}
                  </Button>
                </div>
              </form>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </DashboardLayout>
  );
}
