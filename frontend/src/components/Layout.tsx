'use client';

import { ReactNode, useEffect } from 'react';
import Link from 'next/link';
import { useRouter, usePathname } from 'next/navigation';
import {
  LayoutDashboard, Target, Briefcase, GraduationCap, FileText,
  UserCircle, LogOut, Bell, ShieldCheck, Megaphone, FileCheck, Users
} from 'lucide-react';
import { useAuth } from '@/src/context/AuthContext';
import { cn } from '@/src/lib/utils';
import { Logo } from './Logo';

interface SidebarItem {
  icon: React.ElementType;
  label: string;
  path: string;
}

export function DashboardLayout({ children, title }: { children: ReactNode; title: string }) {
  const { user, isLoading, logout } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!isLoading && !user) {
      router.replace('/login');
    }
  }, [isLoading, user, router]);

  if (!isLoading && !user) return null;

  const studentItems: SidebarItem[] = [
    { icon: LayoutDashboard, label: 'Dashboard', path: '/dashboard' },
    { icon: Target, label: 'Skill Gap', path: '/skill-gap' },
    { icon: FileText, label: 'Job Marketplace', path: '/jobs' },
    { icon: GraduationCap, label: 'Learning Resources', path: '/resources' },
    { icon: FileCheck, label: 'My Applications', path: '/applications' },
    { icon: UserCircle, label: 'Profile', path: '/profile' },
  ];

  const companyItems: SidebarItem[] = [
    { icon: LayoutDashboard, label: 'Dashboard', path: '/company-dashboard' },
    { icon: Briefcase, label: 'Manage Listings', path: '/manage-listings' },
    { icon: Users, label: 'Review Applicants', path: '/review-applications' },
    { icon: GraduationCap, label: 'Training Programme', path: '/post-training' },
    { icon: UserCircle, label: 'Profile', path: '/profile' },
  ];

  const adminItems: SidebarItem[] = [
    { icon: LayoutDashboard, label: 'Dashboard', path: '/admin-dashboard' },
    { icon: ShieldCheck, label: 'Pending Approvals', path: '/approvals' },
    { icon: GraduationCap, label: 'Manage Courses', path: '/manage-courses' },
    { icon: FileCheck, label: 'Endorse Certificates', path: '/endorse' },
    { icon: Megaphone, label: 'Post Announcement', path: '/post-announcement' },
  ];

  const menuItems =
    !user ? [] :
    user.role === 'student' ? studentItems :
    user.role === 'company' ? companyItems :
    adminItems;

  const handleLogout = () => {
    logout();
    router.push('/login');
  };

  return (
    <div className="flex min-h-screen bg-neutral-100">
      {/* Sidebar */}
      <aside className="w-60 bg-white border-r border-neutral-200 fixed h-full z-20 flex flex-col">
        <div className="h-16 px-6 flex items-center border-b border-neutral-100">
          <Logo size="sm" layout="horizontal" />
        </div>
        <nav className="flex-1 p-4 space-y-1">
          {menuItems.map((item) => {
            const isActive = pathname === item.path;
            return (
              <Link
                key={item.path}
                href={item.path}
                className={cn(
                  'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors',
                  isActive
                    ? 'bg-indigo-50 text-primary'
                    : 'text-neutral-600 hover:bg-neutral-100 hover:text-neutral-900'
                )}
              >
                <item.icon size={18} />
                {item.label}
              </Link>
            );
          })}
        </nav>
        <div className="p-4 border-t border-neutral-100">
          <button
            onClick={handleLogout}
            className="flex items-center gap-3 px-3 py-2.5 w-full text-left rounded-lg text-sm font-medium text-neutral-600 hover:bg-red-50 hover:text-danger transition-colors"
          >
            <LogOut size={18} />
            Logout
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <div className="flex-1 ml-60 flex flex-col">
        <header className="h-16 bg-white border-b border-neutral-200 sticky top-0 z-10 px-8 flex items-center justify-between">
          <span className="text-lg font-semibold text-neutral-900">{title}</span>
          <div className="flex items-center gap-4">
            {user?.role === 'student' && (
              <button className="p-2 text-neutral-600 hover:bg-neutral-100 rounded-full relative">
                <Bell size={20} />
                <span className="absolute top-2 right-2 w-2 h-2 bg-danger rounded-full border-2 border-white" />
              </button>
            )}
            <div className="flex items-center gap-3 pl-4 border-l border-neutral-200">
              <div className="text-right hidden sm:block">
                <p className="text-sm font-semibold text-neutral-900 leading-none">{user?.name}</p>
                <p className="text-xs text-neutral-500 capitalize mt-1">{user?.role}</p>
              </div>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={user?.avatar || `https://api.dicebear.com/7.x/avataaars/svg?seed=default`}
                alt="Avatar"
                className="w-9 h-9 rounded-full bg-neutral-200 border border-neutral-100"
              />
            </div>
          </div>
        </header>
        <main className="p-8 pb-16">{children}</main>
      </div>
    </div>
  );
}
