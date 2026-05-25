import type { Metadata } from 'next';
import './globals.css';
import { AuthProvider } from '@/src/context/AuthContext';

export const metadata: Metadata = {
  title: 'MomentumQuest',
  description: 'Accelerate your career journey',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full bg-white text-neutral-900 font-sans">
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
