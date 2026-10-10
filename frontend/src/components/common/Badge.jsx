import React from 'react';

const VARIANT_STYLES = {
  success: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30',
  danger: 'bg-rose-500/10 text-rose-400 border-rose-500/30',
  warning: 'bg-amber-500/10 text-amber-400 border-amber-500/30',
  info: 'bg-sky-500/10 text-sky-400 border-sky-500/30',
  brand: 'bg-indigo-500/10 text-indigo-300 border-indigo-500/30',
  neutral: 'bg-slate-800 text-slate-300 border-slate-700',
  purple: 'bg-purple-500/10 text-purple-300 border-purple-500/30',
};

export default function Badge({
  children,
  variant = 'neutral',
  size = 'sm',
  dot = false,
  className = '',
}) {
  const base = 'inline-flex items-center gap-1.5 font-medium rounded-full border';
  const sizeClasses = size === 'xs' ? 'px-2 py-0.5 text-xs' : 'px-2.5 py-1 text-xs';
  const variantClass = VARIANT_STYLES[variant] || VARIANT_STYLES.neutral;

  return (
    <span className={`${base} ${sizeClasses} ${variantClass} ${className}`}>
      {dot && (
        <span
          className={`h-1.5 w-1.5 rounded-full ${
            variant === 'success'
              ? 'bg-emerald-400'
              : variant === 'danger'
              ? 'bg-rose-400'
              : variant === 'warning'
              ? 'bg-amber-400'
              : 'bg-indigo-400'
          }`}
        />
      )}
      {children}
    </span>
  );
}
