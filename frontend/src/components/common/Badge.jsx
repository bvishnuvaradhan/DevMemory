import React from 'react';

const VARIANT_STYLES = {
  success: 'bg-emerald-50/90 text-emerald-700 border-emerald-200/80',
  danger: 'bg-rose-50/90 text-rose-700 border-rose-200/80',
  warning: 'bg-amber-50/90 text-amber-800 border-amber-200/80',
  info: 'bg-sky-50/90 text-sky-700 border-sky-200/80',
  brand: 'bg-indigo-50/90 text-indigo-700 border-indigo-200/80',
  neutral: 'bg-slate-100/90 text-slate-700 border-slate-200',
  purple: 'bg-purple-50/90 text-purple-700 border-purple-200/80',
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
