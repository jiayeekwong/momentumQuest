'use client';

import { useState } from 'react';
import { Target, CheckCircle2, AlertCircle, PlayCircle, ExternalLink, GraduationCap } from 'lucide-react';
import { motion } from 'motion/react';
import { DashboardLayout } from '@/src/components/Layout';
import { Card, Badge, Button } from '@/src/components/ui';
import { cn } from '@/src/lib/utils';

export default function SkillGapPage() {
  const [selectedJob, setSelectedJob] = useState('Data Analyst');

  return (
    <DashboardLayout title="Skill Gap Analysis">
      <div className="max-w-6xl mx-auto space-y-8">
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-6">
          <div>
            <h2 className="text-2xl font-bold text-neutral-900 mb-1">Career Transformation Roadmap</h2>
            <p className="text-neutral-600">Identify and bridge the gap between your skills and industry requirements.</p>
          </div>
          <div className="w-full md:w-64">
            <label className="text-xs font-bold text-neutral-400 uppercase tracking-wider mb-2 block">Target Job Category</label>
            <select
              value={selectedJob}
              onChange={(e) => setSelectedJob(e.target.value)}
              className="w-full h-11 px-4 bg-white border border-neutral-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
            >
              <option>Data Analyst</option>
              <option>Software Engineer</option>
              <option>UI/UX Designer</option>
              <option>Cloud Architect</option>
            </select>
          </div>
        </div>

        <Card className="bg-indigo-600 border-none p-8 text-white relative overflow-hidden">
          <div className="relative z-10 flex flex-col md:flex-row items-center gap-10">
            <div className="w-48 h-48 relative flex items-center justify-center shrink-0">
              <svg className="w-full h-full transform -rotate-90">
                <circle cx="96" cy="96" r="80" stroke="currentColor" strokeWidth="12" fill="transparent" className="text-white/20" />
                <circle cx="96" cy="96" r="80" stroke="currentColor" strokeWidth="12" fill="transparent" strokeDasharray="502.4" strokeDashoffset={502.4 * (1 - 0.72)} strokeLinecap="round" className="text-white" />
              </svg>
              <div className="absolute text-center">
                <span className="text-4xl font-black block">72%</span>
                <span className="text-xs font-medium uppercase tracking-widest text-indigo-100">Match</span>
              </div>
            </div>
            <div className="flex-1 space-y-4">
              <Badge variant="secondary" className="bg-white/20 text-white border-none">STRONG MATCH</Badge>
              <h3 className="text-3xl font-bold">Almost ready for {selectedJob} roles</h3>
              <p className="text-indigo-50 text-lg">You have 8 of 11 critical skills. 3 more puts you in the top 5% of candidates.</p>
              <div className="flex flex-wrap gap-4 pt-2">
                <div className="flex items-center gap-2 px-4 py-2 bg-white/10 rounded-lg">
                  <CheckCircle2 size={20} className="text-emerald-300" />
                  <span className="text-sm font-semibold">8 Skills Verified</span>
                </div>
                <div className="flex items-center gap-2 px-4 py-2 bg-white/10 rounded-lg">
                  <AlertCircle size={20} className="text-amber-300" />
                  <span className="text-sm font-semibold">3 Skills Missing</span>
                </div>
              </div>
            </div>
          </div>
          <div className="absolute top-0 right-0 w-96 h-96 bg-white/5 rounded-full -mr-32 -mt-32 blur-3xl" />
        </Card>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          <section>
            <div className="flex items-center gap-2 mb-4">
              <CheckCircle2 className="text-success" size={20} />
              <h4 className="text-lg font-bold text-neutral-900">Verified Skills</h4>
            </div>
            <Card className="p-4 bg-neutral-50/50">
              <div className="flex flex-wrap gap-2">
                {['Python', 'SQL', 'Excel', 'Tableau', 'Statistics', 'Project Management', 'Agile', 'Communication'].map((skill) => (
                  <Badge key={skill} variant="success" className="bg-white px-3 py-1.5 flex items-center gap-1.5">
                    <CheckCircle2 size={14} /> {skill}
                  </Badge>
                ))}
              </div>
            </Card>
          </section>

          <section>
            <div className="flex items-center gap-2 mb-4">
              <AlertCircle className="text-danger" size={20} />
              <h4 className="text-lg font-bold text-neutral-900">Missing Core Skills</h4>
            </div>
            <div className="space-y-4">
              {[
                { name: 'Natural Language Processing', demand: 85, priority: 'HIGH', color: 'danger' },
                { name: 'Apache Spark', demand: 62, priority: 'MEDIUM', color: 'warning' },
                { name: 'Hadoop Eco-system', demand: 45, priority: 'LOW', color: 'success' },
              ].map((gap, i) => (
                <Card key={i} className="p-4 group hover:border-primary/50 transition-colors">
                  <div className="flex items-start justify-between mb-3">
                    <div>
                      <h5 className="font-bold text-neutral-900">{gap.name}</h5>
                      <span className="text-[10px] font-bold text-neutral-400 uppercase tracking-widest">Industry Demand</span>
                    </div>
                    <Badge variant={gap.color as 'danger' | 'warning' | 'success'}>{gap.priority}</Badge>
                  </div>
                  <div className="relative w-full h-1.5 bg-neutral-100 rounded-full overflow-hidden">
                    <motion.div
                      initial={{ width: 0 }}
                      animate={{ width: `${gap.demand}%` }}
                      transition={{ delay: 0.5, duration: 1 }}
                      className={cn('absolute top-0 left-0 h-full rounded-full',
                        gap.color === 'danger' ? 'bg-danger' : gap.color === 'warning' ? 'bg-warning' : 'bg-success'
                      )}
                    />
                  </div>
                  <div className="mt-4 flex items-center justify-between">
                    <span className="text-xs font-semibold text-neutral-600">{gap.demand}% demand</span>
                    <Button variant="outline" size="sm" className="h-8 text-xs">Find Resources</Button>
                  </div>
                </Card>
              ))}
            </div>
          </section>
        </div>

        <section>
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-2">
              <GraduationCap className="text-primary" size={24} />
              <h4 className="text-xl font-bold text-neutral-900">Recommended Learning Paths</h4>
            </div>
            <Button variant="ghost" className="text-primary text-sm font-bold">Explore All</Button>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {[
              { title: 'NLP Specialization', platform: 'Coursera', color: 'bg-indigo-600', type: 'Specialization' },
              { title: 'Big Data with Spark', platform: 'Udacity', color: 'bg-secondary', type: 'Nanodegree' },
              { title: 'Data Sci Foundations', platform: 'LinkedIn', color: 'bg-blue-700', type: 'Course' },
            ].map((res, i) => (
              <Card key={i} className="p-0 overflow-hidden flex flex-col group hover:shadow-lg transition-all duration-300">
                <div className={cn('h-32 flex items-center justify-center p-6 text-white relative', res.color)}>
                  <PlayCircle size={48} className="opacity-0 group-hover:opacity-100 transition-opacity z-10" />
                  <h5 className="text-lg font-black text-center group-hover:opacity-20 transition-opacity">{res.title}</h5>
                </div>
                <div className="p-5 flex-1 flex flex-col">
                  <div className="flex items-center justify-between mb-4">
                    <span className="text-[10px] font-black text-neutral-400 uppercase tracking-widest">{res.platform}</span>
                    <Badge variant="primary">{res.type}</Badge>
                  </div>
                  <Button fullWidth className="mt-auto">Enrol Now</Button>
                </div>
              </Card>
            ))}
          </div>
        </section>
      </div>
    </DashboardLayout>
  );
}
