'use client';

import { useEffect, useState, useRef } from 'react';
import { Plus, Users, Clock, Trash2, ToggleLeft, ToggleRight, Pencil, X, Calendar, MapPin, Save } from 'lucide-react';
import { DashboardLayout } from '@/src/components/Layout';
import { Card, Badge, Button, Input } from '@/src/components/ui';
import Link from 'next/link';
import { apiFetch } from '@/src/lib/apiFetch';
import { cn } from '@/src/lib/utils';

interface Listing {
  id: number;
  job_title: string;
  applicants_count: number;
  closing_date: string | null;
  status: string;
  work_mode: string;
  experience_level: string;
  posted_time: string;
}

interface ListingDetail {
  id: number;
  job_title: string;
  category: number | null;
  description: string;
  salary_min: string | null;
  salary_max: string | null;
  work_mode: string;
  experience_level: string;
  closing_date: string | null;
  status: string;
  required_skills: string[];
}

interface JobCategory { id: number; category_name: string; }

const statusVariants: Record<string, 'success' | 'neutral' | 'warning'> = {
  ACTIVE: 'success', DRAFT: 'warning', CLOSED: 'neutral',
};

const workModes = ['On-site', 'Hybrid', 'Remote'];
const experienceLevels = ['Entry Level', 'Mid Level', 'Senior Level', 'Internship'];

export default function ManageListingsPage() {
  const [listings, setListings] = useState<Listing[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [categories, setCategories] = useState<JobCategory[]>([]);

  // Edit panel state
  const [editOpen, setEditOpen] = useState(false);
  const [editLoading, setEditLoading] = useState(false);
  const [editSaving, setEditSaving] = useState(false);
  const [editError, setEditError] = useState('');
  const [editId, setEditId] = useState<number | null>(null);

  // Edit form fields
  const [eTitle, setETitle] = useState('');
  const [eCategoryId, setECategoryId] = useState('');
  const [eSalaryMin, setESalaryMin] = useState('');
  const [eSalaryMax, setESalaryMax] = useState('');
  const [eWorkMode, setEWorkMode] = useState('');
  const [eExperience, setEExperience] = useState('');
  const [eClosing, setEClosing] = useState('');
  const [eDescription, setEDescription] = useState('');
  const [eSkills, setESkills] = useState<string[]>([]);
  const [eSkillInput, setESkillInput] = useState('');

  const skillInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    apiFetch('/api/job-listings/jobs/')
      .then(r => r.json())
      .then(data => setListings(Array.isArray(data) ? data : []))
      .catch(() => {})
      .finally(() => setIsLoading(false));

    fetch('http://localhost:8000/api/scrape-jobs/categories/')
      .then(r => r.json())
      .then(data => setCategories(Array.isArray(data) ? data : (data.results ?? [])))
      .catch(() => {});
  }, []);

  const openEdit = async (id: number) => {
    setEditId(id);
    setEditOpen(true);
    setEditError('');
    setEditLoading(true);

    try {
      const res = await apiFetch(`/api/job-listings/jobs/${id}/`);
      const detail: ListingDetail = await res.json();

      setETitle(detail.job_title);
      setECategoryId(detail.category ? String(detail.category) : '');
      setESalaryMin(detail.salary_min ?? '');
      setESalaryMax(detail.salary_max ?? '');
      setEWorkMode(detail.work_mode);
      setEExperience(detail.experience_level);
      setEClosing(detail.closing_date ?? '');
      setEDescription(detail.description);
      setESkills(detail.required_skills);
    } catch {
      setEditError('Failed to load listing details.');
    } finally {
      setEditLoading(false);
    }
  };

  const closeEdit = () => {
    setEditOpen(false);
    setEditId(null);
    setESkillInput('');
    setEditError('');
  };

  const addSkill = () => {
    const trimmed = eSkillInput.trim();
    if (trimmed && !eSkills.includes(trimmed)) {
      setESkills(prev => [...prev, trimmed]);
      setESkillInput('');
      skillInputRef.current?.focus();
    }
  };

  const saveEdit = async () => {
    if (!editId) return;
    setEditSaving(true);
    setEditError('');

    const payload: Record<string, unknown> = {
      job_title:        eTitle,
      description:      eDescription,
      work_mode:        eWorkMode,
      experience_level: eExperience,
      closing_date:     eClosing || null,
      required_skills:  eSkills,
    };
    if (eCategoryId) payload.category = Number(eCategoryId);
    if (eSalaryMin)  payload.salary_min = Number(eSalaryMin);
    if (eSalaryMax)  payload.salary_max = Number(eSalaryMax);

    try {
      const res = await apiFetch(`/api/job-listings/jobs/${editId}/`, {
        method: 'PATCH',
        body: JSON.stringify(payload),
      });

      if (res.ok) {
        setListings(prev => prev.map(l =>
          l.id === editId
            ? { ...l, job_title: eTitle, work_mode: eWorkMode, experience_level: eExperience, closing_date: eClosing || null }
            : l
        ));
        closeEdit();
      } else {
        const data = await res.json();
        setEditError(JSON.stringify(data));
      }
    } catch {
      setEditError('Network error. Please try again.');
    } finally {
      setEditSaving(false);
    }
  };

  const toggleStatus = async (listing: Listing) => {
    const newStatus = listing.status === 'ACTIVE' ? 'CLOSED' : 'ACTIVE';
    const res = await apiFetch(`/api/job-listings/jobs/${listing.id}/`, {
      method: 'PATCH',
      body: JSON.stringify({ status: newStatus }),
    });
    if (res.ok) {
      setListings(prev => prev.map(l => l.id === listing.id ? { ...l, status: newStatus } : l));
    }
  };

  const deleteListing = async (id: number) => {
    const res = await apiFetch(`/api/job-listings/jobs/${id}/`, { method: 'DELETE' });
    if (res.status === 204) {
      setListings(prev => prev.filter(l => l.id !== id));
    }
  };

  const formatDate = (d: string | null) =>
    d ? new Date(d).toLocaleDateString('en-MY', { day: 'numeric', month: 'short', year: 'numeric' }) : 'No deadline';

  const activeCount = listings.filter(l => l.status === 'ACTIVE').length;

  return (
    <DashboardLayout title="Manage Listings">
      <div className="max-w-5xl mx-auto space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-bold text-neutral-900">Job Listings</h2>
            <p className="text-neutral-500 mt-1 text-sm">{activeCount} active listing{activeCount !== 1 ? 's' : ''}</p>
          </div>
          <Link href="/post-job">
            <Button className="h-11 px-6"><Plus size={16} className="mr-2" /> Post New Job</Button>
          </Link>
        </div>

        {isLoading ? (
          <div className="flex items-center justify-center py-20">
            <div className="w-8 h-8 border-4 border-primary/20 border-t-primary rounded-full animate-spin" />
          </div>
        ) : (
          <div className="space-y-4">
            {listings.map(listing => (
              <Card key={listing.id} className="p-6 hover:border-primary/30 transition-all group">
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                  <div className="flex-1">
                    <div className="flex items-center gap-3 mb-1">
                      <h3 className="text-lg font-bold text-neutral-900 group-hover:text-primary transition-colors">
                        {listing.job_title}
                      </h3>
                      <Badge variant={statusVariants[listing.status] ?? 'neutral'} className="capitalize text-[9px] font-black tracking-widest">
                        {listing.status.toLowerCase()}
                      </Badge>
                    </div>
                    <div className="flex flex-wrap items-center gap-5 text-xs font-semibold text-neutral-500">
                      <span className="flex items-center gap-1.5"><Users size={13} /> {listing.applicants_count} applicants</span>
                      <span className="flex items-center gap-1.5"><Clock size={13} /> Closes {formatDate(listing.closing_date)}</span>
                      {listing.work_mode && <span className="capitalize">{listing.work_mode}</span>}
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <Link href="/review-applications">
                      <Button variant="outline" size="sm" className="h-9 text-xs">
                        <Users size={14} className="mr-1.5" /> View Applicants
                      </Button>
                    </Link>
                    <Button
                      variant="outline" size="sm" className="h-9 text-xs"
                      onClick={() => toggleStatus(listing)}
                      title={listing.status === 'ACTIVE' ? 'Close listing' : 'Activate listing'}
                    >
                      {listing.status === 'ACTIVE'
                        ? <ToggleRight size={16} className="text-success" />
                        : <ToggleLeft size={16} className="text-neutral-400" />}
                    </Button>
                    <Button
                      variant="outline" size="sm" className="h-9 w-9 p-0"
                      onClick={() => openEdit(listing.id)}
                      title="Edit listing"
                    >
                      <Pencil size={14} />
                    </Button>
                    <Button
                      variant="outline" size="sm"
                      className="h-9 w-9 p-0 text-danger hover:bg-danger/5 hover:border-danger/30"
                      onClick={() => deleteListing(listing.id)}
                    >
                      <Trash2 size={14} />
                    </Button>
                  </div>
                </div>
              </Card>
            ))}
          </div>
        )}

        {!isLoading && listings.length === 0 && (
          <div className="py-20 text-center">
            <div className="w-20 h-20 bg-neutral-100 rounded-full flex items-center justify-center mx-auto mb-4 text-neutral-300">
              <Plus size={40} />
            </div>
            <h3 className="text-xl font-bold text-neutral-900">No listings yet</h3>
            <p className="text-neutral-500 mt-1">Post your first job to start receiving applications.</p>
            <Link href="/post-job"><Button className="mt-6">Post a Job</Button></Link>
          </div>
        )}
      </div>

      {/* ── Edit slide-over ── */}
      {editOpen && (
        <div className="fixed inset-0 z-50 flex">
          {/* Backdrop */}
          <div className="flex-1 bg-black/40" onClick={closeEdit} />

          {/* Panel */}
          <div className="w-full max-w-xl bg-white shadow-2xl flex flex-col">
            {/* Header */}
            <div className="flex items-center justify-between px-8 py-5 border-b border-neutral-100">
              <div>
                <h2 className="text-lg font-bold text-neutral-900">Edit Job Listing</h2>
                <p className="text-xs text-neutral-400 mt-0.5">Changes are saved immediately</p>
              </div>
              <button onClick={closeEdit} className="w-9 h-9 rounded-lg flex items-center justify-center hover:bg-neutral-100 transition-colors">
                <X size={18} />
              </button>
            </div>

            {/* Body */}
            <div className="flex-1 overflow-y-auto px-8 py-6">
              {editLoading ? (
                <div className="flex items-center justify-center py-20">
                  <div className="w-8 h-8 border-4 border-primary/20 border-t-primary rounded-full animate-spin" />
                </div>
              ) : (
                <div className="space-y-5">
                  {editError && (
                    <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-sm text-red-700 font-medium">
                      {editError}
                    </div>
                  )}

                  <Input label="Job Title" value={eTitle} onChange={e => setETitle(e.target.value)} required />

                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <label className="text-[10px] font-black text-neutral-900 uppercase tracking-widest block">Category</label>
                      <select value={eCategoryId} onChange={e => setECategoryId(e.target.value)}
                        className="w-full h-10 px-3 bg-white border border-neutral-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20">
                        <option value="">Select category</option>
                        {categories.map(c => <option key={c.id} value={c.id}>{c.category_name}</option>)}
                      </select>
                    </div>
                    <div className="space-y-2">
                      <label className="text-[10px] font-black text-neutral-900 uppercase tracking-widest block">Experience Level</label>
                      <select value={eExperience} onChange={e => setEExperience(e.target.value)}
                        className="w-full h-10 px-3 bg-white border border-neutral-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20">
                        <option value="">Select level</option>
                        {experienceLevels.map(l => <option key={l}>{l}</option>)}
                      </select>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <Input label="Salary Min (RM)" type="number" placeholder="e.g. 3000" value={eSalaryMin} onChange={e => setESalaryMin(e.target.value)} />
                    <Input label="Salary Max (RM)" type="number" placeholder="e.g. 6000" value={eSalaryMax} onChange={e => setESalaryMax(e.target.value)} />
                  </div>

                  <div className="space-y-2">
                    <label className="text-[10px] font-black text-neutral-900 uppercase tracking-widest block">Work Mode</label>
                    <div className="flex gap-2">
                      {workModes.map(mode => (
                        <button key={mode} type="button" onClick={() => setEWorkMode(mode)}
                          className={cn('flex-1 py-2 rounded-lg text-xs font-bold border transition-all',
                            eWorkMode === mode ? 'bg-primary text-white border-primary' : 'bg-white text-neutral-600 border-neutral-200 hover:border-primary/40')}>
                          <MapPin size={11} className="inline mr-1" />{mode}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="space-y-2">
                    <label className="text-[10px] font-black text-neutral-900 uppercase tracking-widest block">Closing Date</label>
                    <div className="relative">
                      <Calendar size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400" />
                      <input type="date" value={eClosing} onChange={e => setEClosing(e.target.value)}
                        className="w-full h-10 pl-9 pr-3 bg-white border border-neutral-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20" />
                    </div>
                  </div>

                  <div className="space-y-2">
                    <label className="text-[10px] font-black text-neutral-900 uppercase tracking-widest block">Job Description</label>
                    <textarea value={eDescription} onChange={e => setEDescription(e.target.value)}
                      className="w-full h-32 p-4 bg-white border border-neutral-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 resize-none"
                      placeholder="Describe the role and responsibilities..." />
                  </div>

                  <div className="space-y-3">
                    <label className="text-[10px] font-black text-neutral-900 uppercase tracking-widest block">Required Skills</label>
                    <div className="flex gap-2">
                      <input
                        ref={skillInputRef}
                        value={eSkillInput}
                        onChange={e => setESkillInput(e.target.value)}
                        onKeyDown={e => e.key === 'Enter' && (e.preventDefault(), addSkill())}
                        placeholder="Type a skill and press Enter"
                        className="flex-1 h-10 px-3 bg-white border border-neutral-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
                      />
                      <Button type="button" variant="outline" size="sm" className="h-10" onClick={addSkill}>
                        <Plus size={16} />
                      </Button>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {eSkills.map(skill => (
                        <span key={skill} className="flex items-center gap-1.5 px-3 py-1.5 bg-indigo-50 text-primary rounded-full text-xs font-bold">
                          {skill}
                          <button type="button" onClick={() => setESkills(prev => prev.filter(s => s !== skill))}
                            className="hover:text-danger">
                            <X size={11} />
                          </button>
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="px-8 py-5 border-t border-neutral-100 flex gap-3">
              <Button variant="outline" fullWidth onClick={closeEdit}>Cancel</Button>
              <Button fullWidth onClick={saveEdit} disabled={editSaving || editLoading}>
                <Save size={15} className="mr-2" />
                {editSaving ? 'Saving...' : 'Save Changes'}
              </Button>
            </div>
          </div>
        </div>
      )}
    </DashboardLayout>
  );
}
