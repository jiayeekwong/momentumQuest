'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  CheckCircle2, Clock, Edit3, Megaphone, Paperclip, Plus, Send,
  Trash2, Upload, X, XCircle,
} from 'lucide-react';

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
          <Button onClick={formOpen ? () => { setFormOpen(false); resetForm(); } : openCreate}>
            {formOpen ? <X size={16} className="mr-2" /> : <Plus size={16} className="mr-2" />}
            {formOpen ? 'Cancel' : 'New Announcement'}
          </Button>
        </div>

        {error && !formOpen && (
          <div role="alert" className="p-4 rounded-xl border border-red-200 bg-red-50 text-sm font-medium text-red-700">
            {error}
          </div>
        )}

        {formOpen && (
          <Card className="p-6">
            <form onSubmit={submit} className="space-y-5">
              <div>
                <h3 className="font-bold text-neutral-900">
                  {editId ? 'Revise Announcement' : 'Submit Announcement'}
                </h3>
                <p className="text-xs text-neutral-500 mt-1">
                  The audience is always student accounts. Approval is required before publication.
                </p>
              </div>
              <Input label="Title" value={title} onChange={e => setTitle(e.target.value)}
                maxLength={200} required />

              <div className="space-y-2">
                <label className="text-[10px] font-black text-neutral-900 uppercase tracking-widest block">Category</label>
                <div className="flex flex-wrap gap-2">
                  {CATEGORIES.map(category => (
                    <button key={category} type="button"
                      onClick={() => setCategories(current => current.includes(category)
                        ? current.filter(value => value !== category)
                        : [...current, category])}
                      className={cn(
                        'px-3 py-1.5 rounded-full text-xs font-bold border transition-colors',
                        categories.includes(category)
                          ? 'bg-primary text-white border-primary'
                          : 'bg-white text-neutral-600 border-neutral-200 hover:border-primary/40',
                      )}>
                      {category}
                    </button>
                  ))}
                </div>
              </div>

              <div className="space-y-1.5">
                <label className="text-[10px] font-black text-neutral-900 uppercase tracking-widest block">Announcement body</label>
                <RichTextEditor value={message} onChange={setMessage} minHeight={160} />
              </div>

              <div className="space-y-2">
                <label className="text-[10px] font-black text-neutral-900 uppercase tracking-widest block">Supporting document (optional)</label>
                <div className="flex flex-col sm:flex-row gap-2">
                  <input type="url" value={supportingDoc}
                    onChange={e => {
                      setSupportingDoc(e.target.value);
                      setAttachmentReceipt('');
                      setUploadedName('');
                    }}
                    placeholder="Paste a URL or upload a PDF, PNG or JPG"
                    className="w-full h-10 px-3 bg-white border border-neutral-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20" />
                  <Button type="button" variant="outline" disabled={isUploading}
                    onClick={() => fileInput.current?.click()}>
                    <Upload size={14} className="mr-2" />
                    {isUploading ? 'Uploading...' : 'Upload'}
                  </Button>
                  <input ref={fileInput} type="file" className="hidden"
                    accept=".pdf,.png,.jpg,.jpeg" onChange={uploadAttachment} />
                </div>
                {uploadedName && (
                  <p className="inline-flex items-center gap-1.5 text-xs font-semibold text-success">
                    <Paperclip size={12} /> {uploadedName}
                  </p>
                )}
              </div>

              {error && (
                <p role="alert" className="text-sm text-danger font-semibold bg-danger/5 border border-danger/20 rounded-lg px-3 py-2">
                  {error}
                </p>
              )}

              <div className="flex justify-end">
                <Button type="submit" disabled={isSaving || isUploading}>
                  <Send size={14} className="mr-2" />
                  {isSaving ? 'Submitting...' : 'Submit for Review'}
                </Button>
              </div>
            </form>
          </Card>
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
                        <Badge variant={config.variant} className="text-[9px] font-black tracking-widest">
                          <Icon size={11} className="mr-1" /> {config.label}
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
    </DashboardLayout>
  );
}
