'use client';

import { useState } from 'react';
import { User, Mail, Building2, GraduationCap, CheckCircle2, Clock, Plus, Edit3, Award, Briefcase } from 'lucide-react';
import { motion } from 'motion/react';
import { DashboardLayout } from '@/src/components/Layout';
import { Card, Badge, Button, Input } from '@/src/components/ui';
import { useAuth } from '@/src/context/AuthContext';
import { cn } from '@/src/lib/utils';

const skills = [
  { name: 'Python', status: 'verified', endorsements: 12 },
  { name: 'SQL', status: 'verified', endorsements: 9 },
  { name: 'Tableau', status: 'verified', endorsements: 7 },
  { name: 'Excel', status: 'verified', endorsements: 5 },
  { name: 'Communication', status: 'pending', endorsements: 0 },
  { name: 'Machine Learning', status: 'pending', endorsements: 0 },
];

export default function ProfilePage() {
  const { user } = useAuth();
  const isCompany = user?.role === 'company';
  const [editMode, setEditMode] = useState(false);
  const [name, setName] = useState(user?.name ?? '');

  return (
    <DashboardLayout title="My Profile">
      <div className="max-w-4xl mx-auto space-y-8">
        {/* Profile header */}
        <Card className="p-8">
          <div className="flex flex-col md:flex-row md:items-start gap-6">
            <div className="w-24 h-24 rounded-2xl bg-gradient-to-br from-primary to-secondary flex items-center justify-center text-white text-3xl font-black shrink-0">
              {(user?.name ?? 'U')[0].toUpperCase()}
            </div>
            <div className="flex-1">
              {editMode ? (
                <div className="space-y-3 mb-4">
                  <Input label="Full Name" value={name} onChange={(e) => setName(e.target.value)} />
                </div>
              ) : (
                <>
                  <h2 className="text-2xl font-black text-neutral-900">{user?.name ?? 'User'}</h2>
                  <p className="text-neutral-500 font-medium mt-1">{user?.email ?? ''}</p>
                </>
              )}
              <div className="flex flex-wrap gap-2 mt-3">
                <Badge variant="primary" className="flex items-center gap-1.5">
                  {isCompany ? <Building2 size={12} /> : <GraduationCap size={12} />}
                  {isCompany ? 'Company Account' : 'Student Account'}
                </Badge>
                {!isCompany && user?.department && (
                  <Badge variant="neutral">{user.department}</Badge>
                )}
              </div>
            </div>
            <Button
              variant={editMode ? 'primary' : 'outline'}
              size="sm"
              onClick={() => setEditMode(!editMode)}
              className="h-10"
            >
              {editMode ? <><CheckCircle2 size={16} className="mr-2" /> Save</> : <><Edit3 size={16} className="mr-2" /> Edit Profile</>}
            </Button>
          </div>
        </Card>

        {!isCompany ? (
          /* Student: Skill Validation */
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2 space-y-6">
              <Card className="p-6">
                <div className="flex items-center justify-between mb-6">
                  <h3 className="text-lg font-bold text-neutral-900 flex items-center gap-2">
                    <Award size={20} className="text-primary" /> Skill Portfolio
                  </h3>
                  <Button variant="outline" size="sm" className="h-8 text-xs">
                    <Plus size={14} className="mr-1.5" /> Add Skill
                  </Button>
                </div>
                <div className="space-y-3">
                  {skills.map((skill, i) => (
                    <motion.div
                      key={skill.name}
                      initial={{ opacity: 0, x: -10 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: i * 0.06 }}
                      className={cn(
                        'p-4 rounded-xl border flex items-center justify-between',
                        skill.status === 'verified'
                          ? 'bg-emerald-50/60 border-emerald-100'
                          : 'bg-neutral-50 border-neutral-100'
                      )}
                    >
                      <div className="flex items-center gap-3">
                        {skill.status === 'verified'
                          ? <CheckCircle2 size={18} className="text-success" />
                          : <Clock size={18} className="text-neutral-400" />}
                        <span className="font-bold text-neutral-900">{skill.name}</span>
                      </div>
                      <div className="flex items-center gap-3">
                        {skill.status === 'verified' && (
                          <span className="text-xs font-semibold text-neutral-500">{skill.endorsements} endorsements</span>
                        )}
                        <Badge variant={skill.status === 'verified' ? 'success' : 'neutral'} className="text-[9px] capitalize">
                          {skill.status}
                        </Badge>
                      </div>
                    </motion.div>
                  ))}
                </div>
              </Card>
            </div>

            <div className="space-y-6">
              <Card className="p-6">
                <h3 className="text-base font-bold text-neutral-900 mb-4">Profile Completion</h3>
                <div className="relative flex items-center justify-center mb-4">
                  <svg className="w-28 h-28 transform -rotate-90">
                    <circle cx="56" cy="56" r="48" stroke="#f3f4f6" strokeWidth="8" fill="transparent" />
                    <circle cx="56" cy="56" r="48" stroke="#4f46e5" strokeWidth="8" fill="transparent"
                      strokeDasharray="301.6" strokeDashoffset={301.6 * (1 - 0.75)} strokeLinecap="round" />
                  </svg>
                  <span className="absolute text-2xl font-black text-neutral-900">75%</span>
                </div>
                <div className="space-y-2 text-sm">
                  {[
                    { label: 'Basic Info', done: true },
                    { label: 'Skills Added', done: true },
                    { label: 'Skills Verified', done: false },
                    { label: 'Resume Uploaded', done: false },
                  ].map((item) => (
                    <div key={item.label} className="flex items-center gap-2">
                      {item.done
                        ? <CheckCircle2 size={14} className="text-success" />
                        : <div className="w-3.5 h-3.5 rounded-full border-2 border-neutral-300" />}
                      <span className={cn('font-medium', item.done ? 'text-neutral-900' : 'text-neutral-400')}>{item.label}</span>
                    </div>
                  ))}
                </div>
              </Card>

              <Card className="p-6">
                <h3 className="text-base font-bold text-neutral-900 mb-4 flex items-center gap-2">
                  <Briefcase size={16} className="text-primary" /> Target Role
                </h3>
                <p className="text-2xl font-black text-primary">{user?.desiredJobCategory ?? 'Data Analyst'}</p>
                <p className="text-xs text-neutral-500 mt-1 font-medium">Your desired job category</p>
              </Card>
            </div>
          </div>
        ) : (
          /* Company profile details */
          <Card className="p-8 space-y-6">
            <h3 className="text-lg font-bold text-neutral-900 flex items-center gap-2">
              <Building2 size={20} className="text-primary" /> Company Information
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="space-y-1">
                <label className="text-[10px] font-black text-neutral-400 uppercase tracking-widest">Company Name</label>
                <p className="text-sm font-bold text-neutral-900">{user?.name ?? 'Company Name'}</p>
              </div>
              <div className="space-y-1">
                <label className="text-[10px] font-black text-neutral-400 uppercase tracking-widest">Email</label>
                <p className="text-sm font-bold text-neutral-900 flex items-center gap-2"><Mail size={14} /> {user?.email ?? ''}</p>
              </div>
              <div className="space-y-1">
                <label className="text-[10px] font-black text-neutral-400 uppercase tracking-widest">Account Type</label>
                <Badge variant="primary" className="flex items-center gap-1.5 w-fit"><Building2 size={12} /> Recruiter / Company</Badge>
              </div>
              <div className="space-y-1">
                <label className="text-[10px] font-black text-neutral-400 uppercase tracking-widest">Status</label>
                <Badge variant="success" className="flex items-center gap-1.5 w-fit"><CheckCircle2 size={12} /> Active</Badge>
              </div>
            </div>
            <div className="pt-4 border-t border-neutral-100">
              <Button variant="outline"><Edit3 size={16} className="mr-2" /> Update Company Info</Button>
            </div>
          </Card>
        )}

        {/* Account info */}
        <Card className="p-6">
          <h3 className="text-base font-bold text-neutral-900 mb-4 flex items-center gap-2">
            <User size={16} className="text-primary" /> Account Details
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
            <div><p className="text-[10px] font-black text-neutral-400 uppercase tracking-widest mb-1">Email</p><p className="font-semibold text-neutral-900">{user?.email ?? '—'}</p></div>
            <div><p className="text-[10px] font-black text-neutral-400 uppercase tracking-widest mb-1">Role</p><p className="font-semibold text-neutral-900 capitalize">{user?.role?.toLowerCase() ?? '—'}</p></div>
          </div>
          <div className="mt-6 pt-4 border-t border-neutral-100">
            <Button variant="outline" size="sm" className="text-danger border-danger/30 hover:bg-danger/5">Change Password</Button>
          </div>
        </Card>
      </div>
    </DashboardLayout>
  );
}
