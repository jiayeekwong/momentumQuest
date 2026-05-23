import React from "react";
import { cn } from "@/src/lib/utils";

type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  fullWidth?: boolean;
  isLoading?: boolean;
  size?: "sm" | "md" | "lg";
};

export function Button({
  children,
  className,
  fullWidth = false,
  isLoading = false,
  size = "md",
  disabled,
  ...props
}: ButtonProps) {
  const sizeClasses = {
    sm: "px-3 py-2 text-sm",
    md: "px-4 py-2.5 text-sm",
    lg: "px-5 py-3 text-base",
  };

  return (
    <button
      className={cn(
        "rounded-lg bg-indigo-600 font-semibold text-white transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60",
        "focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2",
        sizeClasses[size],
        fullWidth && "w-full",
        className
      )}
      disabled={disabled || isLoading}
      {...props}
    >
      {isLoading ? "Loading..." : children}
    </button>
  );
}

type InputProps = React.InputHTMLAttributes<HTMLInputElement> & {
  label?: string;
};

export function Input({ label, className, id, ...props }: InputProps) {
  const inputId = id || props.name || label;

  return (
    <div>
      {label && (
        <label
          htmlFor={inputId}
          className="mb-2 block text-sm font-semibold text-gray-900"
        >
          {label}
        </label>
      )}

      <input
        id={inputId}
        className={cn(
          "w-full rounded-lg border border-gray-300 bg-white px-4 py-3 text-sm text-gray-900",
          "placeholder:text-gray-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-200",
          className
        )}
        {...props}
      />
    </div>
  );
}

type CardProps = React.HTMLAttributes<HTMLDivElement>;

export function Card({ children, className, ...props }: CardProps) {
  return (
    <div
      className={cn("rounded-2xl bg-white shadow-xl", className)}
      {...props}
    >
      {children}
    </div>
  );
}