import React from 'react';
import { ShieldCheck, Clock, XCircle, AlertTriangle } from 'lucide-react';

export default function FixVerificationBadge({ status = 'PENDING', recurrenceCount = 0 }) {
  const normStatus = (status || 'PENDING').toUpperCase();
  const recCount = Number(recurrenceCount) || 0;

  // If issue has recurred, it must never be claimed as a clean verified fix
  if (normStatus === 'RECURRING' || recCount > 0) {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-rose-50 dark:bg-rose-950/60 px-2.5 py-1 text-xs font-semibold text-rose-700 dark:text-rose-300 border border-rose-200 dark:border-rose-800/60 shadow-xs">
        <AlertTriangle className="h-3.5 w-3.5 text-rose-500 dark:text-rose-400" />
        <span>Fix Recurred ({recCount > 0 ? `${recCount}x` : 'Yes'})</span>
      </span>
    );
  }

  if (normStatus === 'VERIFIED') {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 dark:bg-emerald-950/60 px-2.5 py-1 text-xs font-semibold text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800/60 shadow-xs">
        <ShieldCheck className="h-3.5 w-3.5 text-emerald-600 dark:text-emerald-400" />
        <span>Verified Fix</span>
        <span className="text-[10px] text-emerald-600 dark:text-emerald-400 font-mono font-medium">(0x Recurred)</span>
      </span>
    );
  }

  if (normStatus === 'FAILED') {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-rose-50 dark:bg-rose-950/60 px-2.5 py-1 text-xs font-semibold text-rose-700 dark:text-rose-300 border border-rose-200 dark:border-rose-800/60 shadow-xs">
        <XCircle className="h-3.5 w-3.5 text-rose-500 dark:text-rose-400" />
        <span>Verification Failed</span>
      </span>
    );
  }

  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-50 dark:bg-amber-950/60 px-2.5 py-1 text-xs font-semibold text-amber-800 dark:text-amber-300 border border-amber-200 dark:border-amber-800/60 shadow-xs">
      <Clock className="h-3.5 w-3.5 text-amber-600 dark:text-amber-400" />
      <span>Pending Verification</span>
    </span>
  );
}
