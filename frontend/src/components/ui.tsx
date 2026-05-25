'use client';

import * as React from 'react';
import { cn } from '@/src/lib/utils';
import { Slot } from '@radix-ui/react-slot';

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'outline' | 'danger' | 'ghost';
  fullWidth?: boolean;
  isLoading?: boolean;
  size?: 'sm' | 'md' | 'lg';
  children?: React.ReactNode;
  className?: string;
  asChild?: boolean;
}

export function Button({
  children,
  variant = 'primary',
  fullWidth,
  isLoading,
  size = 'md',
  className,
  asChild = false,
  ...props
}: ButtonProps) {
  const Comp = asChild ? Slot : 'button';
  const variants = {
    primary: 'bg-primary text-white hover:opacity-90 shadow-subtle',
    secondary: 'bg-secondary text-white hover:opacity-90 shadow-subtle',
    outline: 'border border-neutral-300 text-neutral-600 hover:bg-neutral-100',
    danger: 'bg-danger text-white hover:opacity-90',
    ghost: 'text-neutral-600 hover:bg-neutral-100',
  };
  const sizes = {
    sm: 'h-8 px-3 text-xs',
    md: 'h-10 px-4 text-sm',
    lg: 'h-12 px-6 text-base',
  };

  return (
    <Comp
      className={cn(
        'rounded-lg font-medium transition-all flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed',
        variants[variant],
        sizes[size],
        fullWidth && 'w-full',
        className
      )}
      {...props}
    >
      {asChild ? (
        children
      ) : (
        <>
          {isLoading && (
            <svg className="animate-spin h-4 w-4 text-current" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
            </svg>
          )}
          {children}
        </>
      )}
    </Comp>
  );
}

export function Badge({
  children,
  variant = 'neutral',
  className,
  ...props
}: {
  children: React.ReactNode;
  variant?: 'neutral' | 'success' | 'warning' | 'danger' | 'primary' | 'secondary';
  className?: string;
} & React.HTMLAttributes<HTMLSpanElement>) {
  const variants = {
    neutral: 'bg-neutral-100 text-neutral-600',
    success: 'bg-emerald-50 text-success border border-emerald-100',
    warning: 'bg-amber-50 text-warning border border-amber-100',
    danger: 'bg-red-50 text-danger border border-red-100',
    primary: 'bg-indigo-50 text-primary border border-indigo-100',
    secondary: 'bg-sky-50 text-secondary border border-sky-100',
  };
  return (
    <span className={cn('px-2.5 py-0.5 rounded-full text-xs font-medium', variants[variant], className)} {...props}>
      {children}
    </span>
  );
}

export function Card({
  children,
  className,
  hover,
  ...props
}: {
  children: React.ReactNode;
  className?: string;
  hover?: boolean;
} & React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        'bg-white rounded-lg border border-neutral-100 p-6',
        hover && 'hover:shadow-md transition-shadow cursor-pointer',
        className
      )}
      {...props}
    >
      {children}
    </div>
  );
}

export function Input({
  label,
  error,
  icon,
  className,
  ...props
}: {
  label?: string;
  error?: string;
  icon?: React.ReactNode;
} & React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <div className="space-y-1.5 flex-1">
      {label && (
        <label className="text-[10px] font-black text-neutral-900 uppercase tracking-widest block">
          {label}
        </label>
      )}
      <div className="relative">
        {icon && (
          <span className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400">
            {icon}
          </span>
        )}
        <input
          className={cn(
            'w-full h-10 px-3 bg-white border border-neutral-300 rounded-lg text-sm transition-all focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary',
            icon && 'pl-9',
            error && 'border-danger focus:ring-danger/20',
            className
          )}
          {...props}
        />
      </div>
      {error && <p className="text-xs text-danger">{error}</p>}
    </div>
  );
}
