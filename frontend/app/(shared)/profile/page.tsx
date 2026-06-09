'use client';

import { useState } from 'react';
import { User, Mail, Building2, GraduationCap, CheckCircle2, Clock, Plus, Edit3, Award, Briefcase, X, KeyRound, ChevronDown, ChevronUp } from 'lucide-react';
import { motion } from 'motion/react';
import { DashboardLayout } from '@/src/components/Layout';
import { Card, Badge, Button, Input } from '@/src/components/ui';
import { useAuth } from '@/src/context/AuthContext';
import { apiFetch } from '@/src/lib/apiFetch';
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
  const { user, updateUser, logout } = useAuth();
  const isCompany = user?.role === 'company';

  // Student header edit
  const [editMode, setEditMode] = useState(false);
  const [name, setName] = useState(user?.name ?? '');

  // Company info edit
  const [companyEditMode, setCompanyEditMode] = useState(false);
  const [companyName, setCompanyName] = useState(user?.name ?? '');
  const [companySaving, setCompanySaving] = useState(false);
  const [companyError, setCompanyError] = useState('');

  // Email change (inside company edit)
  const [emailSectionOpen, setEmailSectionOpen] = useState(false);
  const [newEmail, setNewEmail] = useState('');
  const [currentPassword, setCurrentPassword] = useState('');
  const [emailChanging, setEmailChanging] = useState(false);
  const [emailError, setEmailError] = useState('');
  const [emailSuccess, setEmailSuccess] = useState('');

  // Password change (Account Details card)
  const [pwdOpen, setPwdOpen] = useState(false);
  const [currentPwd, setCurrentPwd] = useState('');
  const [newPwd, setNewPwd] = useState('');
  const [confirmPwd, setConfirmPwd] = useState('');
  const [pwdChanging, setPwdChanging] = useState(false);
  const [pwdError, setPwdError] = useState('');
  const [pwdSuccess, setPwdSuccess] = useState('');

  const saveCompanyInfo = async () => {
    setCompanyError('');
    setCompanySaving(true);
    try {
      const res = await apiFetch('/api/auth/profile/', {
        method: 'PATCH',
        body: JSON.stringify({ company_name: companyName }),
      });
      const data = await res.json();
      if (res.ok) {
        updateUser({ ...user!, name: data.company_name });
        setCompanyEditMode(false);
        setEmailSectionOpen(false);
        setEmailSuccess('');
      } else {
        setCompanyError(data.company_name?.[0] ?? 'Failed to update. Please try again.');
      }
    } catch {
      setCompanyError('Network error. Please try again.');
    } finally {
      setCompanySaving(false);
    }
  };

  const requestEmailChange = async () => {
    setEmailError('');
    setEmailSuccess('');
    setEmailChanging(true);
    try {
      const res = await apiFetch('/api/auth/email-change/', {
        method: 'POST',
        body: JSON.stringify({ new_email: newEmail, password: currentPassword }),
      });
      const data = await res.json();
      if (res.ok) {
        setEmailSuccess(data.detail);
        setNewEmail('');
        setCurrentPassword('');
      } else {
        setEmailError(data.new_email?.[0] ?? data.password?.[0] ?? data.detail ?? 'Something went wrong.');
      }
    } catch {
      setEmailError('Network error. Please try again.');
    } finally {
      setEmailChanging(false);
    }
  };

  const changePassword = async () => {
    setPwdError('');
    setPwdSuccess('');
    setPwdChanging(true);
    try {
      const res = await apiFetch('/api/auth/password-change/', {
        method: 'POST',
        body: JSON.stringify({
          current_password: currentPwd,
          new_password: newPwd,
          confirm_password: confirmPwd,
        }),
      });
      const data = await res.json();
      if (res.ok) {
        setPwdSuccess(data.detail);
        setCurrentPwd('');
        setNewPwd('');
        setConfirmPwd('');
      } else {
        setPwdError(
          data.current_password?.[0] ??
          data.confirm_password?.[0] ??
          data.password?.[0] ??
          data.detail ??
          'Something went wrong.'
        );
      }
    } catch {
      setPwdError('Network error. Please try again.');
    } finally {
      setPwdChanging(false);
    }
  };

  const closeCompanyEdit = () => {
    setCompanyEditMode(false);
    setCompanyName(user?.name ?? '');
    setCompanyError('');
    setEmailSectionOpen(false);
    setEmailError('');
    setEmailSuccess('');
    setNewEmail('');
    setCurrentPassword('');
  };

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
              {editMode && !isCompany ? (
                <div className="space-y-3 mb-4">
                  <Input label="Full Name" value={name} onChange={e => setName(e.target.value)} />
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
            {/* Only show Edit Profile button for students */}
            {!isCompany && (
              <Button
                variant={editMode ? 'primary' : 'outline'}
                size="sm"
                onClick={() => setEditMode(!editMode)}
                className="h-10"
              >
                {editMode
                  ? <><CheckCircle2 size={16} className="mr-2" /> Save</>
                  : <><Edit3 size={16} className="mr-2" /> Edit Profile</>}
              </Button>
            )}
          </div>
        </Card>

        {!isCompany ? (
          /* ── Student: Skill Validation ── */
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
                  ].map(item => (
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
                  <Briefcase size={16} className="text-primary" /> Target Roles
                </h3>
                {user?.targetJobs && user.targetJobs.length > 0 ? (
                  <div className="flex flex-wrap gap-2">
                    {user.targetJobs.map((t) => (
                      <span key={t.id} className="px-3 py-1.5 rounded-full bg-indigo-50 text-primary text-xs font-bold">
                        {t.title_name}
                      </span>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-neutral-400 font-medium">No target roles selected yet.</p>
                )}
                <p className="text-xs text-neutral-500 mt-3 font-medium">The job titles you&apos;re aiming for</p>
              </Card>
            </div>
          </div>
        ) : (
          /* ── Company Information ── */
          <Card className="p-8 space-y-6">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-bold text-neutral-900 flex items-center gap-2">
                <Building2 size={20} className="text-primary" /> Company Information
              </h3>
              {companyEditMode ? (
                <button onClick={closeCompanyEdit}
                  className="w-8 h-8 rounded-lg flex items-center justify-center hover:bg-neutral-100 transition-colors text-neutral-400">
                  <X size={16} />
                </button>
              ) : (
                <Button variant="outline" size="sm" className="h-9"
                  onClick={() => { setCompanyName(user?.name ?? ''); setCompanyEditMode(true); }}>
                  <Edit3 size={14} className="mr-1.5" /> Update Info
                </Button>
              )}
            </div>

            {companyEditMode ? (
              <div className="space-y-5">
                {companyError && (
                  <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700 font-medium">
                    {companyError}
                  </div>
                )}

                {/* Company name */}
                <Input
                  label="Company Name"
                  value={companyName}
                  onChange={e => setCompanyName(e.target.value)}
                  placeholder="Enter your company name"
                />

                {/* Email change collapsible */}
                <div className="border border-neutral-200 rounded-xl overflow-hidden">
                  <button
                    type="button"
                    onClick={() => { setEmailSectionOpen(v => !v); setEmailError(''); setEmailSuccess(''); }}
                    className="w-full flex items-center justify-between px-4 py-3 text-sm font-bold text-neutral-700 hover:bg-neutral-50 transition-colors"
                  >
                    <span className="flex items-center gap-2">
                      <Mail size={15} className="text-primary" /> Change Email Address
                    </span>
                    {emailSectionOpen ? <ChevronUp size={15} className="text-neutral-400" /> : <ChevronDown size={15} className="text-neutral-400" />}
                  </button>

                  {emailSectionOpen && (
                    <div className="px-4 pb-4 pt-1 space-y-4 border-t border-neutral-100 bg-neutral-50/40">
                      <p className="text-xs text-neutral-500 pt-2">
                        Enter your new email address and current password. A verification link will be sent to the new address — the change only takes effect after you click it.
                      </p>

                      {emailError && (
                        <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700 font-medium">
                          {emailError}
                        </div>
                      )}
                      {emailSuccess && (
                        <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-lg text-sm text-emerald-700 font-medium flex items-center gap-2">
                          <CheckCircle2 size={15} /> {emailSuccess}
                        </div>
                      )}

                      <Input
                        label="New Email Address"
                        type="email"
                        placeholder="new@example.com"
                        value={newEmail}
                        onChange={e => setNewEmail(e.target.value)}
                      />
                      <div className="space-y-2">
                        <label className="text-[10px] font-black text-neutral-900 uppercase tracking-widest block">Current Password</label>
                        <div className="relative">
                          <KeyRound size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400" />
                          <input
                            type="password"
                            placeholder="Enter your current password"
                            value={currentPassword}
                            onChange={e => setCurrentPassword(e.target.value)}
                            className="w-full h-10 pl-9 pr-3 bg-white border border-neutral-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
                          />
                        </div>
                      </div>
                      <Button
                        variant="outline"
                        className="w-full h-10 text-sm"
                        onClick={requestEmailChange}
                        disabled={emailChanging || !newEmail.trim() || !currentPassword}
                      >
                        <Mail size={14} className="mr-2" />
                        {emailChanging ? 'Sending...' : 'Send Verification Email'}
                      </Button>
                    </div>
                  )}
                </div>

                <div className="flex gap-3 pt-1">
                  <Button variant="outline" fullWidth onClick={closeCompanyEdit}>Cancel</Button>
                  <Button fullWidth onClick={saveCompanyInfo} disabled={companySaving || !companyName.trim()}>
                    <CheckCircle2 size={15} className="mr-2" />
                    {companySaving ? 'Saving...' : 'Save Changes'}
                  </Button>
                </div>
              </div>
            ) : (
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
            )}
          </Card>
        )}

        {/* Account details */}
        <Card className="p-6">
          <h3 className="text-base font-bold text-neutral-900 mb-4 flex items-center gap-2">
            <User size={16} className="text-primary" /> Account Details
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
            <div>
              <p className="text-[10px] font-black text-neutral-400 uppercase tracking-widest mb-1">Email</p>
              <p className="font-semibold text-neutral-900">{user?.email ?? '—'}</p>
            </div>
            <div>
              <p className="text-[10px] font-black text-neutral-400 uppercase tracking-widest mb-1">Role</p>
              <p className="font-semibold text-neutral-900 capitalize">{user?.role?.toLowerCase() ?? '—'}</p>
            </div>
          </div>
          <div className="mt-6 pt-4 border-t border-neutral-100">
            <div className="border border-neutral-200 rounded-xl overflow-hidden">
              <button
                type="button"
                onClick={() => { setPwdOpen(v => !v); setPwdError(''); setPwdSuccess(''); }}
                className="w-full flex items-center justify-between px-4 py-3 text-sm font-bold text-neutral-700 hover:bg-neutral-50 transition-colors"
              >
                <span className="flex items-center gap-2">
                  <KeyRound size={15} className="text-primary" /> Change Password
                </span>
                {pwdOpen ? <ChevronUp size={15} className="text-neutral-400" /> : <ChevronDown size={15} className="text-neutral-400" />}
              </button>

              {pwdOpen && (
                <div className="px-4 pb-4 pt-1 space-y-4 border-t border-neutral-100 bg-neutral-50/40">
                  <p className="text-xs text-neutral-500 pt-2">
                    After changing your password you will be signed out automatically.
                  </p>

                  {pwdError && (
                    <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700 font-medium">
                      {pwdError}
                    </div>
                  )}
                  {pwdSuccess && (
                    <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-lg text-sm text-emerald-700 font-medium flex items-center gap-2">
                      <CheckCircle2 size={15} /> {pwdSuccess}
                    </div>
                  )}

                  <div className="space-y-2">
                    <label className="text-[10px] font-black text-neutral-900 uppercase tracking-widest block">Current Password</label>
                    <div className="relative">
                      <KeyRound size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400" />
                      <input type="password" placeholder="Enter your current password"
                        value={currentPwd} onChange={e => setCurrentPwd(e.target.value)}
                        className="w-full h-10 pl-9 pr-3 bg-white border border-neutral-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20" />
                    </div>
                  </div>
                  <Input label="New Password" type="password" placeholder="At least 8 characters, include a number and a symbol (e.g. !@#)"
                    value={newPwd} onChange={e => setNewPwd(e.target.value)} />
                  <Input label="Confirm New Password" type="password" placeholder="Repeat new password"
                    value={confirmPwd} onChange={e => setConfirmPwd(e.target.value)} />

                  <Button
                    className="w-full h-10 text-sm"
                    onClick={changePassword}
                    disabled={pwdChanging || !currentPwd || !newPwd || !confirmPwd || !!pwdSuccess}
                  >
                    <KeyRound size={14} className="mr-2" />
                    {pwdChanging ? 'Updating…' : 'Update Password'}
                  </Button>
                </div>
              )}
            </div>
          </div>
        </Card>

      </div>
    </DashboardLayout>
  );
}
