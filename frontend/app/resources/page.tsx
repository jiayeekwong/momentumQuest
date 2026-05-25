'use client';

import { useState } from 'react';
import { Search, BookOpen, PlayCircle, Clock, Star, ExternalLink, Filter } from 'lucide-react';
import { DashboardLayout } from '@/src/components/Layout';
import { Card, Badge, Button } from '@/src/components/ui';
import { cn } from '@/src/lib/utils';

const categories = ['All', 'Data Science', 'Programming', 'Analytics', 'AI & ML', 'Soft Skills'];

const resources = [
  {
    id: '1', title: 'Machine Learning A-Z', provider: 'Udemy', category: 'AI & ML', type: 'Course',
    duration: '44h', rating: 4.8, enrolled: '850K', level: 'Beginner', color: 'bg-indigo-600',
    skills: ['Python', 'Scikit-Learn', 'TensorFlow'],
  },
  {
    id: '2', title: 'SQL for Data Analysis', provider: 'Coursera', category: 'Analytics', type: 'Course',
    duration: '18h', rating: 4.7, enrolled: '320K', level: 'Beginner', color: 'bg-sky-600',
    skills: ['SQL', 'PostgreSQL', 'Window Functions'],
  },
  {
    id: '3', title: 'NLP Specialization', provider: 'deeplearning.ai', category: 'AI & ML', type: 'Specialization',
    duration: '80h', rating: 4.9, enrolled: '210K', level: 'Intermediate', color: 'bg-violet-600',
    skills: ['NLP', 'Python', 'BERT', 'Transformers'],
  },
  {
    id: '4', title: 'Tableau Desktop Specialist', provider: 'Tableau', category: 'Analytics', type: 'Certification',
    duration: '12h', rating: 4.6, enrolled: '95K', level: 'Beginner', color: 'bg-emerald-600',
    skills: ['Tableau', 'Data Viz', 'Dashboard Design'],
  },
  {
    id: '5', title: 'Big Data with Spark & Hadoop', provider: 'Udacity', category: 'Data Science', type: 'Nanodegree',
    duration: '96h', rating: 4.5, enrolled: '60K', level: 'Advanced', color: 'bg-orange-600',
    skills: ['Apache Spark', 'Hadoop', 'PySpark'],
  },
  {
    id: '6', title: 'Communication for Engineers', provider: 'LinkedIn', category: 'Soft Skills', type: 'Course',
    duration: '6h', rating: 4.4, enrolled: '450K', level: 'Beginner', color: 'bg-blue-700',
    skills: ['Presentation', 'Writing', 'Stakeholder Management'],
  },
];

const levelVariants: Record<string, 'success' | 'warning' | 'danger'> = {
  Beginner: 'success', Intermediate: 'warning', Advanced: 'danger',
};

export default function ResourcesPage() {
  const [category, setCategory] = useState('All');
  const [search, setSearch] = useState('');

  const filtered = resources.filter((r) => {
    const matchCat = category === 'All' || r.category === category;
    const matchSearch = r.title.toLowerCase().includes(search.toLowerCase()) || r.provider.toLowerCase().includes(search.toLowerCase());
    return matchCat && matchSearch;
  });

  return (
    <DashboardLayout title="Learning Resources">
      <div className="max-w-6xl mx-auto space-y-8">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h2 className="text-2xl font-bold text-neutral-900">Curated Learning Paths</h2>
            <p className="text-neutral-500 mt-1">Upskill with the best courses handpicked for your career goals.</p>
          </div>
          <div className="flex items-center gap-3">
            <div className="relative w-full md:w-64">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400" size={16} />
              <input
                type="text"
                placeholder="Search resources..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-full h-10 pl-10 pr-4 bg-white border border-neutral-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
              />
            </div>
            <Button variant="outline" size="sm" className="h-10 shrink-0"><Filter size={16} className="mr-2" /> Filter</Button>
          </div>
        </div>

        {/* Category tabs */}
        <div className="flex flex-wrap gap-2">
          {categories.map((cat) => (
            <button
              key={cat}
              onClick={() => setCategory(cat)}
              className={cn(
                'px-4 py-2 rounded-full text-xs font-bold transition-all border',
                category === cat
                  ? 'bg-primary text-white border-primary'
                  : 'bg-white text-neutral-600 border-neutral-200 hover:border-primary/40'
              )}
            >
              {cat}
            </button>
          ))}
        </div>

        {/* Resource grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {filtered.map((res) => (
            <Card key={res.id} className="p-0 overflow-hidden flex flex-col group hover:shadow-lg transition-all duration-300">
              <div className={cn('h-36 flex items-center justify-center p-6 text-white relative', res.color)}>
                <PlayCircle size={52} className="opacity-0 group-hover:opacity-100 transition-opacity z-10 absolute" />
                <div className="text-center group-hover:opacity-10 transition-opacity">
                  <BookOpen size={32} className="mx-auto mb-2 opacity-60" />
                  <h5 className="text-lg font-black leading-tight">{res.title}</h5>
                </div>
              </div>
              <div className="p-5 flex-1 flex flex-col gap-4">
                <div className="flex items-start justify-between">
                  <div>
                    <p className="text-[10px] font-black text-neutral-400 uppercase tracking-widest">{res.provider}</p>
                    <h4 className="font-bold text-neutral-900 mt-0.5">{res.title}</h4>
                  </div>
                  <Badge variant={levelVariants[res.level]} className="text-[9px] shrink-0">{res.level}</Badge>
                </div>

                <div className="flex items-center gap-4 text-xs font-semibold text-neutral-500">
                  <span className="flex items-center gap-1"><Clock size={12} /> {res.duration}</span>
                  <span className="flex items-center gap-1"><Star size={12} className="text-amber-400 fill-amber-400" /> {res.rating}</span>
                  <span>{res.enrolled} enrolled</span>
                </div>

                <div className="flex flex-wrap gap-1.5">
                  {res.skills.map((skill) => (
                    <Badge key={skill} variant="neutral" className="text-[9px] px-2 py-0.5">{skill}</Badge>
                  ))}
                </div>

                <div className="flex gap-2 mt-auto">
                  <Badge variant="primary" className="text-[9px] flex items-center gap-1">{res.type}</Badge>
                  <Button fullWidth size="sm" className="h-8 text-xs">
                    Enrol Now <ExternalLink size={12} className="ml-1" />
                  </Button>
                </div>
              </div>
            </Card>
          ))}
        </div>

        {filtered.length === 0 && (
          <div className="py-20 text-center">
            <BookOpen size={48} className="mx-auto text-neutral-200 mb-4" />
            <h3 className="text-lg font-bold text-neutral-900">No resources found</h3>
            <p className="text-neutral-500 mt-1 text-sm">Try adjusting your search or category filter.</p>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
