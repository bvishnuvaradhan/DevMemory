import React from 'react';

export default function StatCard({
  title,
  value,
  subtitle,
  icon: Icon,
  trend,
  trendPositive = true,
  badgeText,
  badgeVariant = 'neutral',
  className = '',
}) {
  return (
    <div
      className={`relative overflow-hidden rounded-xl border border-slate-800/80 bg-slate-900/60 p-5 backdrop-blur shadow-sm hover:border-slate-700/80 transition-colors ${className}`}
    >
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
          {title}
        </span>
        {Icon && (
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-slate-800/80 text-brand-400 border border-slate-700/50">
            <Icon className="h-4 w-4" />
          </div>
        )}
      </div>

      <div className="mt-3 flex items-baseline gap-2">
        <span className="text-2xl font-bold tracking-tight text-white font-mono">
          {value}
        </span>
        {trend && (
          <span
            className={`text-xs font-medium ${
              trendPositive ? 'text-emerald-400' : 'text-rose-400'
            }`}
          >
            {trend}
          </span>
        )}
      </div>

      {subtitle && (
        <p className="mt-1 text-xs text-slate-400 line-clamp-1">{subtitle}</p>
      )}

      {badgeText && (
        <div className="mt-3">
          <span
            className={`inline-block rounded px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${
              badgeVariant === 'success'
                ? 'bg-emerald-500/15 text-emerald-300'
                : 'bg-brand-500/15 text-brand-300'
            }`}
          >
            {badgeText}
          </span>
        </div>
      )}
    </div>
  );
}
