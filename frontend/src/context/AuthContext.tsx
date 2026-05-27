'use client';

import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { User, UserRole } from '@/src/types';

interface BackendProfile {
  email: string;
  role: string;
  name?: string;
  student_name?: string;
  company_name?: string;
  department?: string;
  desired_job_category?: string;
}

interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (email: string, role: UserRole) => void;
  loginFromBackend: (profileData: BackendProfile, accessToken: string) => void;
  logout: () => void;
  signup: (name: string, email: string, role: UserRole) => void;
  updateUser: (user: User) => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // Cross-tab logout: when another tab clears mq_user (e.g. email confirmation), log out here too
  useEffect(() => {
    const handleStorage = (e: StorageEvent) => {
      if ((e.key === 'mq_user' || e.key === 'accessToken') && !e.newValue) {
        setUser(null);
      }
    };
    window.addEventListener('storage', handleStorage);
    return () => window.removeEventListener('storage', handleStorage);
  }, []);

  useEffect(() => {
    const saved = localStorage.getItem('mq_user');
    if (saved) {
      try { setUser(JSON.parse(saved)); setIsLoading(false); return; } catch { localStorage.removeItem('mq_user'); }
    }

    // mq_user missing — try to restore session from a stored access token
    const accessToken = localStorage.getItem('accessToken');
    if (!accessToken) { setIsLoading(false); return; }

    fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/auth/profile/`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    })
      .then(async res => {
        if (!res.ok) throw new Error('unauthorized');
        const profileData = await res.json();
        const role = profileData.role.toLowerCase() as UserRole;
        const name =
          profileData.student_name ||
          profileData.company_name ||
          profileData.admin_name ||
          profileData.email.split('@')[0];
        const restored: User = {
          id: profileData.email,
          name,
          email: profileData.email,
          role,
          avatar: `https://api.dicebear.com/7.x/avataaars/svg?seed=${profileData.email}`,
          department: profileData.department,
          desiredJobCategory: profileData.desired_job_category,
          companyName: profileData.company_name,
        };
        setUser(restored);
        localStorage.setItem('mq_user', JSON.stringify(restored));
      })
      .catch(() => {
        localStorage.removeItem('accessToken');
        localStorage.removeItem('refreshToken');
      })
      .finally(() => setIsLoading(false));
  }, []);

  const login = (email: string, role: UserRole) => {
    const mockUser: User = {
      id: `user_${Date.now()}`,
      name: email.split('@')[0],
      email,
      role,
      avatar: `https://api.dicebear.com/7.x/avataaars/svg?seed=${email}`,
      department: role === 'student' ? 'Computer Science' : undefined,
      companyName: role === 'company' ? 'TechCorp Solutions' : undefined,
    };
    setUser(mockUser);
    localStorage.setItem('mq_user', JSON.stringify(mockUser));
    localStorage.setItem('mq_role', role);
  };

  const loginFromBackend = (profileData: BackendProfile, accessToken: string) => {
    const role = profileData.role.toLowerCase() as UserRole;
    const name =
      profileData.name ||
      profileData.student_name ||
      profileData.company_name ||
      profileData.email.split('@')[0];

    const newUser: User = {
      id: profileData.email,
      name,
      email: profileData.email,
      role,
      avatar: `https://api.dicebear.com/7.x/avataaars/svg?seed=${profileData.email}`,
      department: profileData.department,
      desiredJobCategory: profileData.desired_job_category,
      companyName: profileData.company_name,
    };

    setUser(newUser);
    localStorage.setItem('mq_user', JSON.stringify(newUser));
    localStorage.setItem('mq_role', role);
    localStorage.setItem('accessToken', accessToken);
  };

  const signup = (name: string, email: string, role: UserRole) => {
    const newUser: User = {
      id: `user_${Date.now()}`,
      name,
      email,
      role,
      avatar: `https://api.dicebear.com/7.x/avataaars/svg?seed=${email}`,
      department: role === 'student' ? 'Computer Science' : undefined,
      companyName: role === 'company' ? 'New Company' : undefined,
    };
    setUser(newUser);
    localStorage.setItem('mq_user', JSON.stringify(newUser));
    localStorage.setItem('mq_role', role);
  };

  const logout = () => {
    setUser(null);
    localStorage.removeItem('mq_user');
    localStorage.removeItem('mq_role');
    localStorage.removeItem('accessToken');
    localStorage.removeItem('refreshToken');
    localStorage.removeItem('userRole');
    localStorage.removeItem('userEmail');
  };

  const updateUser = (updatedUser: User) => {
    setUser(updatedUser);
    localStorage.setItem('mq_user', JSON.stringify(updatedUser));
  };

  return (
    <AuthContext.Provider value={{ user, isLoading, isAuthenticated: !!user, login, loginFromBackend, logout, signup, updateUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within an AuthProvider');
  return context;
};
