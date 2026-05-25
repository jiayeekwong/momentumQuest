'use client';

import { useState } from 'react';
import { Search, Plus, Pencil, Trash2, GraduationCap, Clock, Star, ExternalLink } from 'lucide-react';
import { DashboardLayout } from '@/src/components/Layout';
import { Card, Badge, Button } from '@/src/components/ui';
import { cn } from '@/src/lib/utils';

type CourseStatus = 'active' | 'pending' | 'archived';

type Course = {
  id: string; title: string; provider: string; type: string;
  duration: string; rating: number; status: CourseStatus; skills: string[];
};

const mockCourses: Course[] = [
  { id: '1', title: 'Machine Learning A-Z', provider: 'Udemy', type: 'Course', duration: '44h', rating: 4.8, status: 'active', skills: ['Python', 'Scikit-Learn', 'TensorFlow'] },
  { id: '2', title: 'NLP Specialization', provider: 'deeplearning.ai', type: 'Specialization', duration: '80h', rating: 4.9, status: 'active', skills: ['NLP', 'BERT', 'Python'] },
  { id: '3', title: 'Big Data with Spark', provider: 'Udacity', type: 'Nanodegree', duration: '96h', rating: 4.5, status: 'pending', skills: ['Apache Spark', 'Hadoop', 'PySpark'] },
  { id: '4', title: 'SQL Fundamentals', provider: 'Coursera', type: 'Course', duration: '18h', rating: 4.7, status: 'active', skills: ['SQL', 'PostgreSQL'] },
  { id: '5', title: 'Excel for Business', provider: 'Macquarie Uni', type: 'Course', duration: '12h', rating: 4.3, status: 'archived', skills: ['Excel', 'Data Analysis'] },
];

const statusVariants: Record<CourseStatus, 'success' | 'warning' | 'neutral'> = {
  active: 'success', pending: 'warning', archived: 'neutral',
};

export default function ManageCoursesPage() {
  const [courses, setCourses] = useState<Course[]>(mockCourses);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<'All' | CourseStatus>('All');

  const deleteCourse = (id: string) => setCourses((prev) => prev.filter((c) => c.id !== id));

  const filtered = courses.filter((c) => {
    const matchStatus = statusFilter === 'All' || c.status === statusFilter;
    const matchSearch = c.title.toLowerCase().includes(search.toLowerCase()) || c.provider.toLowerCase().includes(search.toLowerCase());
    return matchStatus && matchSearch;
  });

  return (
    <DashboardLayout title="Manage Courses">
      <div className="max-w-5xl mx-auto space-y-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h2 className="text-2xl font-bold text-neutral-900">Course Library</h2>
            <p className="text-neutral-500 mt-1 text-sm">{courses.filter((c) => c.status === 'active').length} active courses on the platform</p>
          </div>
          <Button className="h-11 px-6"><Plus size={16} className="mr-2" /> Add Course</Button>
        </div>

        <div className="flex flex-col md:flex-row gap-3">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400" size={16} />
            <input type="text" placeholder="Search courses..." value={search} onChange={(e) => setSearch(e.target.value)}
              className="w-full h-10 pl-10 pr-4 bg-white border border-neutral-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20" />
          </div>
          <div className="flex gap-1 p-1 bg-neutral-100 rounded-xl">
            {(['All', 'active', 'pending', 'archived'] as const).map((f) => (
              <button key={f} onClick={() => setStatusFilter(f)}
                className={cn('px-3 py-1.5 text-xs font-bold rounded-lg transition-all capitalize', statusFilter === f ? 'bg-white shadow-sm text-primary' : 'text-neutral-500 hover:text-neutral-900')}>
                {f}
              </button>
            ))}
          </div>
        </div>

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
                      <p className="text-sm font-medium text-neutral-500">{course.provider} · {course.type}</p>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <Badge variant={statusVariants[course.status]} className="capitalize text-[9px] font-black tracking-widest">{course.status}</Badge>
                      <Button variant="outline" size="sm" className="h-8 w-8 p-0"><ExternalLink size={13} /></Button>
                      <Button variant="outline" size="sm" className="h-8 w-8 p-0"><Pencil size={13} /></Button>
                      <Button variant="outline" size="sm" className="h-8 w-8 p-0 text-danger hover:bg-danger/5 hover:border-danger/30"
                        onClick={() => deleteCourse(course.id)}><Trash2 size={13} /></Button>
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center gap-4 mt-2 text-xs font-semibold text-neutral-500">
                    <span className="flex items-center gap-1.5"><Clock size={12} /> {course.duration}</span>
                    <span className="flex items-center gap-1.5"><Star size={12} className="text-amber-400 fill-amber-400" /> {course.rating}</span>
                  </div>
                  <div className="flex flex-wrap gap-1.5 mt-3">
                    {course.skills.map((skill) => (
                      <span key={skill} className="px-2 py-0.5 bg-neutral-100 rounded-full text-[10px] font-bold text-neutral-600">{skill}</span>
                    ))}
                  </div>
                </div>
              </div>
            </Card>
          ))}
        </div>

        {filtered.length === 0 && (
          <div className="py-20 text-center">
            <GraduationCap size={48} className="mx-auto text-neutral-200 mb-4" />
            <h3 className="text-xl font-bold text-neutral-900">No courses found</h3>
            <p className="text-neutral-500 mt-1 text-sm">Try adjusting your search or filter.</p>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
