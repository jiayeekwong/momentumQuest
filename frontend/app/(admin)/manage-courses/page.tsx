'use client';

import { useState, useEffect } from 'react';
import { Search, Plus, Pencil, Trash2, GraduationCap, X } from 'lucide-react';

import { DashboardLayout } from '@/src/components/Layout';
import { Card, Button } from '@/src/components/ui';
import { apiFetch } from '@/src/lib/apiFetch';
import { cn } from '@/src/lib/utils';
import { useDepartments } from '@/src/lib/privacyNotice';

interface Course {
  id: number;
  /** The university's own code, as it prints it: WIX1001. Null on the courses
   *  that were added before the field existed. */
  course_code: string | null;
  title: string;
  /** Every department that runs it. A module is commonly shared. */
  departments: string[];
  skill: string | null;
  /** Every skill it teaches, the headline one first. */
  skill_names: string[];
  course_url: string;
  updated_at: string;
}

interface CourseForm {
  course_code: string;
  title: string;
  departments: string[];
  skill_names: string[];
}

const emptyForm: CourseForm = { course_code: '', title: '', departments: [], skill_names: [] };

export default function ManageCoursesPage() {
  const [courses, setCourses] = useState<Course[]>([]);
  const [search, setSearch] = useState('');
  // What is being typed in the skill box, before Enter adds it.
  const [skillDraft, setSkillDraft] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);
  const [form, setForm] = useState<CourseForm>(emptyForm);
  const [saving, setSaving] = useState(false);
  // Course departments include "Compulsory", which is not something a
  // student can belong to, so this is the wider of the two server lists.
  const { course_departments: DEPARTMENTS } = useDepartments();
  const [formError, setFormError] = useState('');

  useEffect(() => {
    apiFetch('/api/resources/courses/')
      .then(r => r.json())
      .then(data => setCourses(Array.isArray(data) ? data : (data.results ?? [])))
      .catch(() => {})
      .finally(() => setIsLoading(false));
  }, []);

  const filtered = courses.filter(c =>
    c.title.toLowerCase().includes(search.toLowerCase()) ||
    (c.departments ?? []).some(d => d.toLowerCase().includes(search.toLowerCase())) ||
    (c.course_code ?? '').toLowerCase().includes(search.toLowerCase())
  );

  const openAdd = () => {
    setEditId(null);
    setForm(emptyForm);
    setSkillDraft('');
    setFormError('');
    setModalOpen(true);
  };

  const openEdit = (course: Course) => {
    setEditId(course.id);
    setForm({
      course_code: course.course_code ?? '',
      title:       course.title,
      departments: course.departments ?? [],
      skill_names: course.skill_names ?? [],
    });
    setFormError('');
    setModalOpen(true);
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setFormError('');
    try {
      const url     = editId ? `/api/resources/courses/${editId}/` : '/api/resources/courses/';
      const method  = editId ? 'PATCH' : 'POST';
      const payload = { ...form, course_url: '' };
      const res     = await apiFetch(url, { method, body: JSON.stringify(payload) });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        setFormError(err.detail ?? JSON.stringify(err));
        return;
      }
      const saved: Course = await res.json();
      if (editId) {
        setCourses(prev => prev.map(c => (c.id === editId ? { ...c, ...saved } : c)));
      } else {
        setCourses(prev => [...prev, saved]);
      }
      setModalOpen(false);
    } catch {
      setFormError('Something went wrong.');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm('Delete this course?')) return;
    const res = await apiFetch(`/api/resources/courses/${id}/`, { method: 'DELETE' });
    if (res.status === 204 || res.ok) {
      setCourses(prev => prev.filter(c => c.id !== id));
    }
  };

  return (
    <DashboardLayout title="Manage Courses">
      <div className="max-w-5xl mx-auto space-y-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h2 className="text-2xl font-bold text-neutral-900">Course Library</h2>
            <p className="text-neutral-500 mt-1 text-sm">{courses.length} course{courses.length !== 1 ? 's' : ''} on the platform</p>
          </div>
          <Button className="h-11 px-6" onClick={openAdd}><Plus size={16} className="mr-2" /> Add Course</Button>
        </div>

        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400" size={16} />
          <input type="text" placeholder="Search by code, title or department..." value={search} onChange={(e) => setSearch(e.target.value)}
            className="w-full h-10 pl-10 pr-4 bg-white border border-neutral-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20" />
        </div>

        {isLoading ? (
          <div className="space-y-3">
            {[1, 2, 3].map(i => <div key={i} className="h-24 bg-neutral-100 animate-pulse rounded-2xl" />)}
          </div>
        ) : (
          <div className="space-y-3">
            {filtered.map((course) => (
              <Card key={course.id} className="p-5 hover:border-primary/20 transition-all group">
                <div className="flex items-start gap-4">
                  <div className="w-12 h-12 bg-indigo-50 rounded-xl flex items-center justify-center text-primary shrink-0">
                    <GraduationCap size={22} />
                  </div>
                  <div className="flex-1">
                    <div className="flex flex-col md:flex-row md:items-start justify-between gap-2">
                      <div>
                        <h3 className="font-bold text-neutral-900 group-hover:text-primary transition-colors">
                          {course.course_code && (
                            <span className="font-mono text-primary mr-2">{course.course_code}</span>
                          )}
                          {course.title}
                        </h3>
                        {course.departments?.length > 0 && (
                          <p className="text-sm font-medium text-neutral-500">
                            {course.departments.join(' · ')}
                          </p>
                        )}
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        <Button variant="outline" size="sm" className="h-8 w-8 p-0" onClick={() => openEdit(course)}>
                          <Pencil size={13} />
                        </Button>
                        <Button variant="outline" size="sm" className="h-8 w-8 p-0 text-danger hover:bg-danger/5 hover:border-danger/30"
                          onClick={() => handleDelete(course.id)}>
                          <Trash2 size={13} />
                        </Button>
                      </div>
                    </div>
                    {/* Every skill, not just the headline one. The card read
                        course.skill -- the single foreign key -- so a course
                        saved with four skills listed one, and the only way to
                        see the rest was to open the edit form. */}
                    {(course.skill_names?.length ? course.skill_names
                      : course.skill ? [course.skill] : []).map((name, i) => (
                      <span key={name}
                        className="inline-block mt-2 mr-1.5 px-2 py-0.5 bg-indigo-50 text-primary rounded-full text-[10px] font-bold">
                        {i === 0 && <span className="mr-1 opacity-50">main</span>}
                        {name}
                      </span>
                    ))}
                  </div>
                </div>
              </Card>
            ))}
          </div>
        )}

        {!isLoading && filtered.length === 0 && (
          <div className="py-20 text-center">
            <GraduationCap size={48} className="mx-auto text-neutral-200 mb-4" />
            <h3 className="text-xl font-bold text-neutral-900">No courses found</h3>
            <p className="text-neutral-500 mt-1 text-sm">Try adjusting your search or add a new course.</p>
          </div>
        )}
      </div>

      {/* Add / Edit modal */}
      {modalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm px-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md p-8">
            <div className="flex items-center justify-between mb-6">
              <h3 className="text-lg font-black text-neutral-900">{editId ? 'Edit Course' : 'Add Course'}</h3>
              <button onClick={() => setModalOpen(false)} className="w-8 h-8 flex items-center justify-center rounded-lg hover:bg-neutral-100">
                <X size={18} />
              </button>
            </div>
            <form onSubmit={handleSave} className="space-y-4">
              <div>
                <label className="text-[10px] font-black text-neutral-900 uppercase tracking-widest block mb-1.5">Course code</label>
                <input value={form.course_code} onChange={e => setForm(f => ({ ...f, course_code: e.target.value }))}
                  className="w-full h-10 px-3 border border-neutral-300 rounded-lg text-sm uppercase focus:outline-none focus:ring-2 focus:ring-primary/20"
                  placeholder="e.g. WIX1001" />
              </div>
              <div>
                <label className="text-[10px] font-black text-neutral-900 uppercase tracking-widest block mb-1.5">Title *</label>
                <input required value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
                  className="w-full h-10 px-3 border border-neutral-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
                  placeholder="e.g. Introduction to Machine Learning" />
              </div>
              <div>
                <label className="text-[10px] font-black text-neutral-900 uppercase tracking-widest block mb-1.5">Department</label>
                {/* Several, because a module is commonly shared -- Compulsory
                    for one cohort and a department's elective for another. A
                    single select made the administrator pick one and be wrong
                    for everybody else. */}
                <div className="flex flex-wrap gap-2">
                  {DEPARTMENTS.map(d => {
                    const chosen = form.departments.includes(d);
                    return (
                      <button key={d} type="button"
                        onClick={() => setForm(f => ({
                          ...f,
                          departments: chosen
                            ? f.departments.filter(x => x !== d)
                            : [...f.departments, d],
                        }))}
                        className={cn(
                          'px-3 py-1.5 rounded-lg border text-xs font-semibold transition-colors',
                          chosen
                            ? 'bg-primary text-white border-primary'
                            : 'bg-white text-neutral-600 border-neutral-300 hover:border-primary/40')}>
                        {d}
                      </button>
                    );
                  })}
                </div>
              </div>
              <div>
                <label className="text-[10px] font-black text-neutral-900 uppercase tracking-widest block mb-1.5">Skill *</label>
                {/* A course called "Web Programming" teaches HTML, CSS and
                    JavaScript. One field is what produced Skill rows whose
                    name was a comma separated list. The first is the headline
                    one, which is what the rest of the application reads. */}
                {form.skill_names.length > 0 && (
                  <div className="flex flex-wrap gap-2 mb-2">
                    {form.skill_names.map((name, i) => (
                      <span key={name}
                        className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-indigo-50 text-primary rounded-lg text-xs font-bold">
                        {i === 0 && <span className="text-[9px] uppercase tracking-wider opacity-60">main</span>}
                        {name}
                        <button type="button" aria-label={`Remove ${name}`}
                          onClick={() => setForm(f => ({
                            ...f, skill_names: f.skill_names.filter(x => x !== name),
                          }))}
                          className="hover:text-danger">×</button>
                      </span>
                    ))}
                  </div>
                )}
                <input value={skillDraft}
                  onChange={e => setSkillDraft(e.target.value)}
                  onKeyDown={e => {
                    if (e.key !== 'Enter' && e.key !== ',') return;
                    e.preventDefault();
                    const name = skillDraft.trim();
                    if (!name || form.skill_names.includes(name)) return;
                    setForm(f => ({ ...f, skill_names: [...f.skill_names, name] }));
                    setSkillDraft('');
                  }}
                  className="w-full h-10 px-3 border border-neutral-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
                  placeholder="e.g. Python — press Enter to add" />
              </div>
              {formError && <p className="text-xs text-danger font-semibold">{formError}</p>}
              <div className="flex gap-3 pt-2">
                <Button type="button" variant="outline" fullWidth onClick={() => setModalOpen(false)}>Cancel</Button>
                <Button type="submit" fullWidth disabled={saving}>{saving ? 'Saving…' : editId ? 'Save Changes' : 'Add Course'}</Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </DashboardLayout>
  );
}
