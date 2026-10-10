import React from 'react';

const VARIANT_STYLES = {
  success: 'bg-emerald-50/90 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300 border-emerald-200/80 dark:border-emerald-800/60',
  danger: 'bg-rose-50/90 dark:bg-rose-950/60 text-rose-700 dark:text-rose-300 border-rose-200/80 dark:border-rose-800/60',
  warning: 'bg-amber-50/90 dark:bg-amber-950/60 text-amber-800 dark:text-amber-300 border-amber-200/80 dark:border-amber-800/60',
  info: 'bg-sky-50/90 dark:bg-sky-950/60 text-sky-700 dark:text-sky-300 border-sky-200/80 dark:border-sky-800/60',
  brand: 'bg-indigo-50/90 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-300 border-indigo-200/80 dark:border-indigo-800/60',
  neutral: 'bg-slate-100/90 dark:bg-slate-800/90 text-slate-700 dark:text-slate-300 border-slate-200 dark:border-slate-700',
  purple: 'bg-purple-50/90 dark:bg-purple-950/60 text-purple-700 dark:text-purple-300 border-purple-200/80 dark:border-purple-800/60',
};

export default function Badge({
  children,
  variant = 'neutral',
  size = 'sm',
  dot = false,
  className = '',
}) {
  const base = 'inline-flex items-center gap-1.5 font-medium rounded-full border shadow-xs';
  const sizeClasses = size === 'xs' ? 'px-2 py-0.5 text-xs' : 'px-2.5 py-1 text-xs';
  const variantClass = VARIANT_STYLES[variant] || VARIANT_STYLES.neutral;

  return (
    <span className={`${base} ${sizeClasses} ${variantClass} ${className}`}>
      {dot && (
        <span
          className={`h-1.5 w-1.5 rounded-full ${
            variant === 'success'
              ? 'bg-emerald-500'
              : variant === 'danger'
              ? 'bg-rose-500'
              : variant === 'warning'
              ? 'bg-amber-500'
              : 'bg-indigo-500'
          }`}
        />
      )}
      {children}
    </span>
  );
}
