'use client';

import { useState, useEffect } from 'react';
import { Search, Plus, Pencil, Trash2, GraduationCap, X } from 'lucide-react';

import { DashboardLayout } from '@/src/components/Layout';
import { Card, Button } from '@/src/components/ui';
import { apiFetch } from '@/src/lib/apiFetch';

const DEPARTMENTS = [
  'Artificial Intelligence',
  'Software Engineering',
  'Information Systems',
  'Computer System & Networking',
  'Multimedia',
  'Compulsory',
];

interface Course {
  id: number;
  title: string;
  department: string;
  skill: string | null;
  course_url: string;
  updated_at: string;
}

interface CourseForm {
  title: string;
  department: string;
  skill_name: string;
}

const emptyForm: CourseForm = { title: '', department: '', skill_name: '' };

export default function ManageCoursesPage() {
  const [courses, setCourses] = useState<Course[]>([]);
  const [search, setSearch] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);
  const [form, setForm] = useState<CourseForm>(emptyForm);
  const [saving, setSaving] = useState(false);
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
    (c.department ?? '').toLowerCase().includes(search.toLowerCase())
  );

  const openAdd = () => {
    setEditId(null);
    setForm(emptyForm);
    setFormError('');
    setModalOpen(true);
  };

  const openEdit = (course: Course) => {
    setEditId(course.id);
    setForm({
      title:      course.title,
      department: course.department ?? '',
      skill_name: course.skill ?? '',
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
        setCourses(prev => prev.map(c => c.id === editId ? { ...c, ...saved, skill: saved.skill ?? form.skill_name } : c));
      } else {
        setCourses(prev => [...prev, { ...saved, skill: saved.skill ?? form.skill_name }]);
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
          <input type="text" placeholder="Search by title or department..." value={search} onChange={(e) => setSearch(e.target.value)}
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
                        <h3 className="font-bold text-neutral-900 group-hover:text-primary transition-colors">{course.title}</h3>
                        {course.department && (
                          <p className="text-sm font-medium text-neutral-500">{course.department}</p>
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
                    {course.skill && (
                      <span className="inline-block mt-2 px-2 py-0.5 bg-indigo-50 text-primary rounded-full text-[10px] font-bold">
                        {course.skill}
                      </span>
                    )}
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
                <label className="text-[10px] font-black text-neutral-900 uppercase tracking-widest block mb-1.5">Title *</label>
                <input required value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
                  className="w-full h-10 px-3 border border-neutral-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
                  placeholder="e.g. Introduction to Machine Learning" />
              </div>
              <div>
                <label className="text-[10px] font-black text-neutral-900 uppercase tracking-widest block mb-1.5">Department</label>
                <select required value={form.department} onChange={e => setForm(f => ({ ...f, department: e.target.value }))}
                  className="w-full h-10 px-3 border border-neutral-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 bg-white">
                  <option value="">Select department</option>
                  {DEPARTMENTS.map(d => <option key={d} value={d}>{d}</option>)}
                </select>
              </div>
              <div>
                <label className="text-[10px] font-black text-neutral-900 uppercase tracking-widest block mb-1.5">Skill *</label>
                <input required value={form.skill_name} onChange={e => setForm(f => ({ ...f, skill_name: e.target.value }))}
                  className="w-full h-10 px-3 border border-neutral-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
                  placeholder="e.g. Python" />
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
