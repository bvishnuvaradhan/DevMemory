import React from 'react';
import { ShieldCheck, Clock, XCircle, AlertTriangle } from 'lucide-react';

export default function FixVerificationBadge({ status = 'PENDING', recurrenceCount = 0 }) {
  const normStatus = (status || 'PENDING').toUpperCase();
  const recCount = Number(recurrenceCount) || 0;

  // If issue has recurred, it must never be claimed as a clean verified fix
  if (normStatus === 'RECURRING' || recCount > 0) {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-rose-500/10 px-2.5 py-1 text-xs font-semibold text-rose-400 border border-rose-500/30">
        <AlertTriangle className="h-3.5 w-3.5 text-rose-400" />
        <span>Fix Recurred ({recCount > 0 ? `${recCount}x` : 'Yes'})</span>
      </span>
    );
  }

  if (normStatus === 'VERIFIED') {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-500/10 px-2.5 py-1 text-xs font-semibold text-emerald-400 border border-emerald-500/30">
        <ShieldCheck className="h-3.5 w-3.5 text-emerald-400" />
        <span>Verified Fix</span>
        <span className="text-[10px] text-emerald-300/80 font-mono">(0x Recurred)</span>
      </span>
    );
  }

  if (normStatus === 'FAILED') {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-rose-500/10 px-2.5 py-1 text-xs font-semibold text-rose-400 border border-rose-500/30">
        <XCircle className="h-3.5 w-3.5 text-rose-400" />
        <span>Verification Failed</span>
      </span>
    );
  }

  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-500/10 px-2.5 py-1 text-xs font-semibold text-amber-400 border border-amber-500/30">
      <Clock className="h-3.5 w-3.5 text-amber-400" />
      <span>Pending Verification</span>
    </span>
  );
}
