'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { motion, AnimatePresence } from 'motion/react';
import { ChevronLeft, ChevronRight, CheckCircle2, Mail, User, Building2 } from 'lucide-react';
import { Button, Input, Card } from '@/src/components/ui';
import { Logo } from '@/src/components/Logo';
import { cn } from '@/src/lib/utils';

type SignupRole = 'STUDENT' | 'COMPANY';

export default function SignupPage() {
  const [step, setStep] = useState(1);
  const [role, setRole] = useState<SignupRole>('STUDENT');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [department, setDepartment] = useState('');
  const [desiredJobCategory, setDesiredJobCategory] = useState('');
  const [jobCategories, setJobCategories] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/scrape-jobs/categories/`)
      .then((r) => r.json())
      .then((data: { category_name: string }[]) =>
        setJobCategories(data.map((c) => c.category_name))
      )
      .catch(() => {});
  }, []);

  const steps = [
    { title: 'Account Details', icon: Mail },
    { title: 'Role Details', icon: User },
    { title: 'Verify Email', icon: CheckCircle2 },
  ];

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError('');

    const pwRegex = /^(?=.*[A-Za-z])(?=.*\d)(?=.*[!@#$%^&*(),.?":{}|<>_\-+=/\\[\]~`]).{8,}$/;
    if (!pwRegex.test(password)) {
      setError('Password must be 8+ chars with a letter, digit, and special character.');
      return;
    }
    if (password !== confirmPassword) { setError('Passwords do not match.'); return; }

    setIsLoading(true);
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/auth/register/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email, password, confirm_password: confirmPassword, role, name,
          department: role === 'STUDENT' ? department : '',
          desired_job_category: role === 'STUDENT' ? desiredJobCategory : '',
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        const msg = data.detail
          ? (Array.isArray(data.detail) ? data.detail.join(' ') : data.detail)
          : Object.entries(data).map(([k, v]) => `${k}: ${Array.isArray(v) ? (v as string[]).join(' ') : v}`).join('\n');
        setError(msg);
        return;
      }
      setStep(3);
    } catch {
      setError('Signup failed. Make sure the Django backend is running.');
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-primary to-secondary flex flex-col items-center justify-center p-4">
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="w-full max-w-xl">
        <div className="text-center mb-8 flex flex-col items-center">
          <Logo size="lg" theme="dark" layout="vertical" className="mb-2" />
          <p className="text-white/80 font-medium mt-3">Join the next generation of talent</p>
        </div>

        <Card className="p-0 overflow-hidden rounded-2xl shadow-2xl">
          {/* Stepper */}
          <div className="bg-neutral-50 px-8 py-6 border-b border-neutral-100 flex items-center justify-between">
            {steps.map((s, i) => (
              <div key={i} className="flex flex-col items-center gap-2 flex-1 relative">
                {i < steps.length - 1 && (
                  <div className={cn('absolute h-[2px] w-full top-5 left-1/2 -z-0', step > i + 1 ? 'bg-primary' : 'bg-neutral-200')} />
                )}
                <div className={cn(
                  'w-10 h-10 rounded-full flex items-center justify-center z-10 transition-all border-2',
                  step === i + 1 ? 'bg-primary border-primary text-white' :
                  step > i + 1 ? 'bg-success border-success text-white' : 'bg-white border-neutral-200 text-neutral-400'
                )}>
                  {step > i + 1 ? <CheckCircle2 size={18} /> : <s.icon size={18} />}
                </div>
                <span className={cn('text-[10px] font-black uppercase tracking-widest', step === i + 1 ? 'text-primary' : 'text-neutral-400')}>
                  {s.title}
                </span>
              </div>
            ))}
          </div>

          <div className="p-8">
            <AnimatePresence mode="wait">
              {step === 1 && (
                <motion.div key="step1" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }} className="space-y-5">
                  <h3 className="text-xl font-bold text-neutral-900">Create your account</h3>
                  <Input label="Full Name" placeholder="Jane Doe" value={name} onChange={(e) => setName(e.target.value)} required />
                  <Input label="Email Address" type="email" placeholder="jane@example.com" value={email} onChange={(e) => setEmail(e.target.value)} required />
                  <div className="grid grid-cols-2 gap-4">
                    <Input label="Password" type="password" placeholder="••••••••" value={password} onChange={(e) => setPassword(e.target.value)} required />
                    <Input label="Confirm Password" type="password" placeholder="••••••••" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} required />
                  </div>

                  <div className="space-y-2">
                    <label className="text-[10px] font-black text-neutral-900 uppercase tracking-widest block">I am joining as a</label>
                    <div className="grid grid-cols-2 gap-4">
                      {([
                        { id: 'STUDENT', label: 'Student', icon: User, desc: 'Find your dream job' },
                        { id: 'COMPANY', label: 'Company', icon: Building2, desc: 'Hire top talent' },
                      ] as const).map((r) => (
                        <div
                          key={r.id}
                          onClick={() => setRole(r.id)}
                          className={cn(
                            'p-4 border-2 rounded-xl cursor-pointer transition-all flex flex-col gap-2',
                            role === r.id ? 'border-primary bg-indigo-50/50' : 'border-neutral-100 hover:border-neutral-200'
                          )}
                        >
                          <r.icon className={role === r.id ? 'text-primary' : 'text-neutral-400'} size={24} />
                          <span className={cn('text-sm font-bold', role === r.id ? 'text-primary' : 'text-neutral-900')}>{r.label}</span>
                          <span className="text-[10px] text-neutral-400 font-medium">{r.desc}</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  <Button fullWidth onClick={() => setStep(2)} className="mt-4 h-12">
                    Next Step <ChevronRight size={18} className="ml-1" />
                  </Button>
                </motion.div>
              )}

              {step === 2 && (
                <motion.div key="step2" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }} className="space-y-5">
                  <h3 className="text-xl font-bold text-neutral-900">{role === 'STUDENT' ? 'Student Details' : 'Company Details'}</h3>
                  {role === 'STUDENT' ? (
                    <>
                      <div className="space-y-2">
                        <label className="text-[10px] font-black text-neutral-900 uppercase tracking-widest block">Department</label>
                        <select
                          className="w-full h-10 px-3 bg-white border border-neutral-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
                          value={department}
                          onChange={(e) => setDepartment(e.target.value)}
                        >
                          <option value="">Select department</option>
                          <option>Artificial Intelligence</option>
                          <option>Multimedia</option>
                          <option>Information System</option>
                          <option>Software Engineering</option>
                          <option>Computer System &amp; Networking</option>
                        </select>
                      </div>
                      <div className="space-y-2">
                        <label className="text-[10px] font-black text-neutral-900 uppercase tracking-widest block">Desired Job Category</label>
                        <select
                          className="w-full h-10 px-3 bg-white border border-neutral-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
                          value={desiredJobCategory}
                          onChange={(e) => setDesiredJobCategory(e.target.value)}
                        >
                          <option value="">Select a job category</option>
                          {jobCategories.map((cat) => (
                            <option key={cat} value={cat}>{cat}</option>
                          ))}
                        </select>
                      </div>
                    </>
                  ) : (
                    <p className="text-sm text-neutral-500">Your company account will be created with the name: <strong>{name}</strong></p>
                  )}

                  {error && (
                    <div className="rounded-lg bg-red-50 border border-red-100 p-3 text-sm text-danger whitespace-pre-line">
                      {error}
                    </div>
                  )}

                  <div className="flex gap-4 pt-2">
                    <Button variant="outline" fullWidth onClick={() => { setStep(1); setError(''); }} className="h-12">
                      <ChevronLeft size={18} className="mr-1" /> Back
                    </Button>
                    <Button fullWidth isLoading={isLoading} onClick={(e) => handleSubmit(e as React.FormEvent)} className="h-12">
                      Create Account
                    </Button>
                  </div>
                </motion.div>
              )}

              {step === 3 && (
                <motion.div key="step3" initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} className="text-center py-8 space-y-6">
                  <div className="w-20 h-20 bg-emerald-50 text-success rounded-full flex items-center justify-center mx-auto">
                    <Mail size={40} />
                  </div>
                  <div>
                    <h3 className="text-2xl font-black text-neutral-900">Check your inbox</h3>
                    <p className="text-neutral-600 mt-2">We&apos;ve sent a verification link to <strong>{email}</strong>. Click it to activate your account.</p>
                  </div>
                  <div className="pt-4">
                    <Link href="/login">
                      <Button fullWidth className="h-12">Return to Login</Button>
                    </Link>
                    <p className="text-sm text-neutral-400 font-medium mt-4">
                      Didn&apos;t receive it?{' '}
                      <button className="text-primary font-bold hover:underline" onClick={() => setStep(2)}>Resend email</button>
                    </p>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </Card>

        <p className="text-center text-white/70 text-sm mt-6">
          Already have an account?{' '}
          <Link href="/login" className="text-white font-semibold hover:underline">Login</Link>
        </p>
      </motion.div>
    </div>
  );
}
