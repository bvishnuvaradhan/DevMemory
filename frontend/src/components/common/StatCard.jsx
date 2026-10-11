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
      className={`relative overflow-hidden rounded-2xl border border-white/85 dark:border-slate-800/80 bg-white/75 dark:bg-slate-900/75 p-3.5 sm:p-5 backdrop-blur-md shadow-glass hover:shadow-glass-hover hover:border-indigo-200/80 dark:hover:border-indigo-800/80 hover:-translate-y-0.5 transition-all duration-200 ${className}`}
    >
      <div className="flex items-center justify-between">
        <span className="text-[11px] sm:text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
          {title}
        </span>
        {Icon && (
          <div className="flex h-8 w-8 sm:h-9 sm:w-9 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-50 dark:from-indigo-950/60 to-purple-50 dark:to-purple-950/40 text-indigo-600 dark:text-indigo-400 border border-indigo-100/80 dark:border-indigo-800/50 shadow-xs shrink-0">
            <Icon className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
          </div>
        )}
      </div>

      <div className="mt-2.5 sm:mt-3 flex items-baseline gap-1.5 sm:gap-2">
        <span className="text-xl sm:text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-100 font-mono truncate">
          {value}
        </span>
        {trend && (
          <span
            className={`text-xs font-semibold ${
              trendPositive ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'
            }`}
          >
            {trend}
          </span>
        )}
      </div>

      {subtitle && (
        <p className="mt-1 text-xs text-slate-500 dark:text-slate-400 line-clamp-1">{subtitle}</p>
      )}

      {badgeText && (
        <div className="mt-3">
          <span
            className={`inline-block rounded-full px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider border ${
              badgeVariant === 'success'
                ? 'bg-emerald-50 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800'
                : 'bg-indigo-50 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-300 border-indigo-200 dark:border-indigo-800'
            }`}
          >
            {badgeText}
          </span>
        </div>
      )}
    </div>
  );
}
