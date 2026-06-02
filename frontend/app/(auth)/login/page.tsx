'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { motion } from 'motion/react';
import { Button, Input, Card } from '@/src/components/ui';
import { Logo } from '@/src/components/Logo';
import { useAuth } from '@/src/context/AuthContext';

export default function LoginPage() {
  const router = useRouter();
  const { loginFromBackend } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    setIsLoading(true);

    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/auth/login/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      });
      const data = await res.json();

      if (!res.ok) {
        setError(data.detail === 'No active account found with the given credentials'
          ? 'Incorrect email or password.'
          : data.detail || 'Login failed.');
        return;
      }

      localStorage.setItem('accessToken', data.access);
      localStorage.setItem('refreshToken', data.refresh);

      const profileRes = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/auth/profile/`, {
        headers: { Authorization: `Bearer ${data.access}` },
      });
      const profileData = await profileRes.json();

      if (!profileRes.ok) { setError('Failed to load user profile.'); return; }

      loginFromBackend(profileData, data.access);

      const role = profileData.role as string;
      if (role === 'STUDENT') router.push('/dashboard');
      else if (role === 'COMPANY') router.push('/company-dashboard');
      else if (role === 'ADMIN') router.push('/admin-dashboard');
      else router.push('/dashboard');
    } catch {
      setError('Cannot connect to server. Make sure the Django backend is running.');
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-primary to-secondary flex flex-col items-center justify-center p-4">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-md"
      >
        <div className="text-center mb-8 flex flex-col items-center">
          <Logo size="lg" theme="dark" layout="vertical" className="mb-2" />
          <p className="text-white/80 font-medium mt-3">Accelerate your career journey</p>
        </div>

        <Card className="p-8 rounded-2xl shadow-2xl">
          <h2 className="text-2xl font-bold text-neutral-900 mb-6">Welcome back</h2>
          <form onSubmit={handleLogin} className="space-y-5">
            <Input
              label="Email Address"
              type="email"
              placeholder="name@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
            <div className="space-y-1">
              <Input
                label="Password"
                type="password"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
              <div className="text-right pt-1">
                <Link href="/forgot-password" className="text-xs font-semibold text-primary hover:underline">
                  Forgot password?
                </Link>
              </div>
            </div>

            {error && (
              <div className="rounded-lg bg-red-50 border border-red-100 p-3 text-sm text-danger font-medium">
                {error}
              </div>
            )}

            <Button type="submit" fullWidth size="lg" isLoading={isLoading} className="mt-2">
              Login
            </Button>
          </form>

          <div className="mt-8 pt-6 border-t border-neutral-100 text-center">
            <p className="text-sm text-neutral-600">
              Don&apos;t have an account?{' '}
              <Link href="/signup" className="font-semibold text-primary hover:underline">
                Sign up
              </Link>
            </p>
          </div>
        </Card>
      </motion.div>
    </div>
  );
}
