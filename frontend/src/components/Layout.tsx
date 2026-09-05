'use client';

import { ReactNode, useEffect, useRef, useState, useSyncExternalStore } from 'react';
import Link from 'next/link';
import { useRouter, usePathname } from 'next/navigation';
import {
  LayoutDashboard, Target, Briefcase, GraduationCap, FileText,
  UserCircle, LogOut, Bell, ShieldCheck, Megaphone, FileCheck, Users
} from 'lucide-react';
import { useAuth } from '@/src/context/AuthContext';
import { cn } from '@/src/lib/utils';
import { apiFetch } from '@/src/lib/apiFetch';
import { Logo } from './Logo';

interface SidebarItem {
  icon: React.ElementType;
  label: string;
  path: string;
}


interface NotificationItem {
  kind: 'APPLICATION' | 'CERTIFICATE' | 'TRANSCRIPT' | 'ANNOUNCEMENT';
  at: string;
  title: string;
  detail: string;
  status: string | null;
  href: string;
}

// When this browser last opened the panel. Read state is per-browser because
// the feed is derived from existing records rather than stored rows, so there
// is nothing server-side to mark. That is still strictly better than the
// hardcoded dot it replaces, which was unread-forever.
const SEEN_KEY = 'mq_notifications_seen_at';

function readSeenAt(): string {
  try {
    return localStorage.getItem(SEEN_KEY) ?? '';
  } catch {
    return '';
  }
}

// Read through useSyncExternalStore rather than an effect. The server has no
// localStorage, so the first paint has to be the empty snapshot and the real
// value can only arrive on hydration; expressing that as setState inside an
// effect is the cascading render React now warns about. getSnapshot returns a
// string, so React's identity check settles on its own.
const seenAtListeners = new Set<() => void>();

function subscribeSeenAt(onChange: () => void) {
  seenAtListeners.add(onChange);
  // Another tab opening the panel should settle the dot here too.
  window.addEventListener('storage', onChange);
  return () => {
    seenAtListeners.delete(onChange);
    window.removeEventListener('storage', onChange);
  };
}

function writeSeenAt(value: string) {
  try {
    localStorage.setItem(SEEN_KEY, value);
  } catch {
    /* a browser blocking storage still gets a working panel */
  }
  seenAtListeners.forEach(notify => notify());
}

const KIND_ICON: Record<NotificationItem['kind'], typeof Bell> = {
  APPLICATION: Briefcase,
  CERTIFICATE: FileCheck,
  TRANSCRIPT: GraduationCap,
  ANNOUNCEMENT: Megaphone,
};

function relativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return '';
  const minutes = Math.round((Date.now() - then) / 60000);
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(iso).toLocaleDateString('en-MY', { day: 'numeric', month: 'short' });
}

function NotificationBell() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const seenAt = useSyncExternalStore(subscribeSeenAt, readSeenAt, () => '');
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    apiFetch('/api/dashboard/notifications/')
      .then(r => (r.ok ? r.json() : null))
      .then(data => setItems(Array.isArray(data?.results) ? data.results : []))
      .catch(() => {})
      .finally(() => setIsLoading(false));
  }, []);

  // Close on an outside click or Escape, so the panel does not strand the page.
  useEffect(() => {
    if (!open) return;
    const onClick = (event: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onClick);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onClick);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const unreadCount = items.filter(item => !seenAt || item.at > seenAt).length;

  const toggle = () => {
    const next = !open;
    setOpen(next);
    if (next) {
      // Marked seen on open, not on close: the student has now looked at them.
      writeSeenAt(new Date().toISOString());
    }
  };

  return (
    <div className="relative" ref={panelRef}>
      <button
        type="button"
        onClick={toggle}
        aria-label={unreadCount ? `Notifications, ${unreadCount} new` : 'Notifications'}
        aria-expanded={open}
        className="relative rounded-full p-2 text-neutral-600 transition-colors hover:bg-neutral-100"
      >
        <Bell size={20} />
        {unreadCount > 0 && (
          <span className="absolute right-1 top-1 flex h-4 min-w-4 items-center justify-center
                           rounded-full border-2 border-white bg-danger px-1 text-[9px]
                           font-black leading-none text-white">
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 z-50 mt-2 w-80 overflow-hidden rounded-xl border
                        border-neutral-200 bg-white shadow-lg">
          <div className="border-b border-neutral-100 px-4 py-3">
            <p className="text-[10px] font-black uppercase tracking-widest text-neutral-400">
              Notifications
            </p>
          </div>

          <div className="max-h-96 overflow-y-auto">
            {isLoading ? (
              <div className="space-y-2 p-4">
                {[0, 1, 2].map(i => (
                  <div key={i} className="h-10 animate-pulse rounded bg-neutral-100" />
                ))}
              </div>
            ) : items.length === 0 ? (
              <p className="px-4 py-8 text-center text-sm text-neutral-400">
                Nothing new yet. Decisions on your applications and documents
                will show up here.
              </p>
            ) : (
              items.map((item, index) => {
                const Icon = KIND_ICON[item.kind] ?? Bell;
                return (
                  <button
                    key={`${item.kind}-${item.at}-${index}`}
                    type="button"
                    onClick={() => { setOpen(false); router.push(item.href); }}
                    className="flex w-full items-start gap-3 border-b border-neutral-50 px-4 py-3
                               text-left transition-colors last:border-0 hover:bg-neutral-50"
                  >
                    <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center
                                     rounded-lg bg-indigo-50 text-primary">
                      <Icon size={14} />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block text-sm font-semibold text-neutral-900">
                        {item.title}
                      </span>
                      {item.detail && (
                        <span className="mt-0.5 block text-xs leading-snug text-neutral-500">
                          {item.detail}
                        </span>
                      )}
                      <span className="mt-1 block text-[10px] font-medium text-neutral-400">
                        {relativeTime(item.at)}
                      </span>
                    </span>
                  </button>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// Which role each section belongs to.
//
// The sidebar already switched by role, but nothing stopped a student or an
// administrator *navigating* to a company page: the nav simply did not
// offer the link. Opening /post-job while signed in as anything but a
// company reached the form, filled it in, and failed on submit with the
// API's raw "You do not have permission to perform this action." -- which
// reads like a broken account rather than the wrong one.
//
// Routes not listed here are shared (/profile) or public.
const ROUTE_OWNER: Record<string, 'student' | 'company' | 'admin'> = {
  '/dashboard': 'student', '/skill-gap': 'student', '/jobs': 'student',
  '/resources': 'student', '/applications': 'student',
  '/company-dashboard': 'company', '/manage-listings': 'company',
  '/review-applications': 'company', '/post-training': 'company',
  '/post-job': 'company',
  '/admin-dashboard': 'admin', '/approvals': 'admin',
  '/manage-courses': 'admin', '/endorse': 'admin',
  '/post-announcement': 'admin',
};

export function DashboardLayout({ children, title }: { children: ReactNode; title: string }) {
  const { user, isLoading, logout } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!isLoading && !user) {
      router.replace('/login');
    }
  }, [isLoading, user, router]);

  // A page belonging to another role is not shown and not half-shown: the
  // user goes to their own dashboard rather than filling in a form that
  // cannot be submitted.
  const owner = pathname ? ROUTE_OWNER[pathname] : undefined;
  const wrongRole = Boolean(user && owner && owner !== user.role);

  useEffect(() => {
    if (!wrongRole || !user) return;
    router.replace(
      user.role === 'company' ? '/company-dashboard'
      : user.role === 'admin' ? '/admin-dashboard'
      : '/dashboard',
    );
  }, [wrongRole, user, router]);

  if (!isLoading && !user) return null;
  if (wrongRole) return null;

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
            {user?.role === 'student' && <NotificationBell />}
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
