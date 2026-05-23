'use client';

import { createContext, useContext, useState, ReactNode } from 'react';
import { User, UserRole } from '@/src/types';

interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (email: string, role: UserRole) => void;
  logout: () => void;
  signup: (name: string, email: string, role: UserRole) => void;
  updateUser: (user: User) => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(() => {
    if (typeof window === 'undefined') {
      return null;
    }

    const savedUser = localStorage.getItem('mq_user');
    if (savedUser) {
      try {
        return JSON.parse(savedUser);
      } catch (error) {
        console.error('Failed to parse saved user:', error);
        localStorage.removeItem('mq_user');
      }
    }

    return null;
  });
  const [isLoading] = useState(false);

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
  };

  const updateUser = (updatedUser: User) => {
    setUser(updatedUser);
    localStorage.setItem('mq_user', JSON.stringify(updatedUser));
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading,
        isAuthenticated: !!user,
        login,
        logout,
        signup,
        updateUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
