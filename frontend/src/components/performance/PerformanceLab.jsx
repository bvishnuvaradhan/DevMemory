import React from 'react';
import {
  ResponsiveContainer,
  ComposedChart,
  Line,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
} from 'recharts';
import {
  TrendingUp,
  AlertTriangle,
  Clock,
  Gauge,
  Activity,
  CheckCircle2,
  Database,
} from 'lucide-react';
import StatCard from '../common/StatCard';
import Badge from '../common/Badge';
import EmptyState from '../common/EmptyState';

export default function PerformanceLab({ performanceData, isMock = true }) {
  if (
    !performanceData ||
    !Array.isArray(performanceData.runs) ||
    performanceData.runs.length === 0
  ) {
    return (
      <EmptyState
        title="No Performance Benchmarks Recorded"
        description="Run commands repeatedly with 'devmemory run -- <command>' to establish execution baselines and detect timing regressions."
        icon={Gauge}
      />
    );
  }

  const {
    baselineMs,
    medianMs,
    runs = [],
    projectName,
    tolerancePercent = 20,
  } = performanceData;

  const validRuns = Array.isArray(runs) ? runs : [];
  const latestRun = validRuns[validRuns.length - 1];

  const numBaseline = Number(baselineMs);
  const hasValidBaseline = Number.isFinite(numBaseline) && numBaseline > 0;
  const numTolerance = Number(tolerancePercent) > 0 ? Number(tolerancePercent) : 20;

  // Calculate regression on latest run only when comparable baseline is present
  const latestDuration = latestRun ? Number(latestRun.durationMs) : NaN;
  const isLatestRegression =
    hasValidBaseline &&
    Number.isFinite(latestDuration) &&
    latestDuration > numBaseline * (1 + numTolerance / 100);

  const deltaMs =
    hasValidBaseline && Number.isFinite(latestDuration)
      ? Math.round(latestDuration - numBaseline)
      : 0;
  const deltaPercent =
    hasValidBaseline && Number.isFinite(latestDuration)
      ? Math.round((deltaMs / numBaseline) * 100)
      : 0;

  // Custom Recharts Tooltip
  const CustomTooltip = ({ active, payload, label }) => {
    if (active && payload && payload.length) {
      const data = payload[0].payload;
      return (
        <div className="rounded-xl border border-slate-200 bg-white/95 backdrop-blur-md p-3 shadow-xl text-xs font-mono space-y-1 text-slate-800">
          <div className="text-slate-500 font-semibold">{data.command}</div>
          <div className="text-slate-900 flex items-center justify-between gap-4">
            <span>Duration:</span>
            <span className="font-bold text-indigo-600">{data.durationMs}ms</span>
          </div>
          {hasValidBaseline && (
            <div className="text-slate-500 flex items-center justify-between gap-4">
              <span>Baseline:</span>
              <span className="font-medium text-emerald-600">{baselineMs}ms</span>
            </div>
          )}
          <div className="text-slate-500 flex items-center justify-between gap-4 pt-1 border-t border-slate-100">
            <span>Status:</span>
            <span className={data.exitCode === 0 ? 'text-emerald-600 font-semibold' : 'text-rose-600 font-semibold'}>
              Exit {data.exitCode}
            </span>
          </div>
          {data.isRegression && (
            <div className="text-rose-600 font-bold text-[10px] uppercase pt-1">
              ⚠️ Regression Detected (+{data.regressionDeltaMs}ms)
            </div>
          )}
        </div>
      );
    }
    return null;
  };

  return (
    <div className="space-y-6">
      {/* Mock data disclaimer if applicable */}
      {isMock && (
        <div className="rounded-xl border border-amber-200 bg-amber-50/80 px-4 py-2.5 text-xs text-amber-900 flex items-center justify-between font-mono shadow-xs">
          <div className="flex items-center gap-2">
            <Database className="h-4 w-4 text-amber-600" />
            <span>
              <strong>Demonstration Performance Data:</strong> Measurements shown are sample benchmark distributions.
            </span>
          </div>
          <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] text-amber-900 border border-amber-300 font-semibold">
            MOCK BENCHMARK
          </span>
        </div>
      )}

      {/* Regression Alert Banner (if regression detected) */}
      {isLatestRegression && (
        <div className="rounded-2xl border border-rose-200 bg-rose-50/90 p-4 flex items-start justify-between gap-4 shadow-xs">
          <div className="flex items-start gap-3">
            <AlertTriangle className="h-5 w-5 text-rose-500 shrink-0 mt-0.5" />
            <div>
              <h4 className="text-sm font-semibold text-rose-950 font-mono">
                Potential Performance Regression Flagged
              </h4>
              <p className="mt-1 text-xs text-rose-900/80 leading-relaxed">
                Latest execution of <code className="bg-rose-100 px-1 py-0.5 rounded font-mono text-rose-950">{latestRun.command}</code> clocked at <strong>{latestRun.durationMs}ms</strong>, which is <strong>+{deltaMs}ms (+{deltaPercent}%)</strong> slower than the established median baseline of <strong>{baselineMs}ms</strong>.
              </p>
            </div>
          </div>
          <Badge variant="danger" size="xs">
            +{deltaPercent}% Delta
          </Badge>
        </div>
      )}

      {/* Benchmark KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard
          title="Baseline Target"
          value={hasValidBaseline ? `${baselineMs}ms` : 'Not Set'}
          subtitle={hasValidBaseline ? `Calculated median benchmark` : 'Needs more runs'}
          icon={Gauge}
        />
        <StatCard
          title="Median Duration"
          value={medianMs ? `${medianMs}ms` : 'N/A'}
          subtitle={`Across ${runs.length} benchmark runs`}
          icon={Activity}
        />
        <StatCard
          title="Latest Run"
          value={`${latestRun?.durationMs ?? 0}ms`}
          subtitle={latestRun?.timestamp ? `At ${latestRun.timestamp}` : ''}
          icon={Clock}
          trend={hasValidBaseline ? `${deltaPercent >= 0 ? '+' : ''}${deltaPercent}%` : undefined}
          trendPositive={!isLatestRegression}
        />
        <StatCard
          title="Regression Status"
          value={isLatestRegression ? 'REGRESSED' : 'NORMAL'}
          subtitle={isLatestRegression ? `Exceeds +${tolerancePercent}% tolerance` : 'Within normal variance'}
          icon={TrendingUp}
          badgeText={isLatestRegression ? 'Alert' : 'Passing'}
          badgeVariant={isLatestRegression ? 'neutral' : 'success'}
        />
      </div>

      {/* Recharts Timeline Graph */}
      <div className="rounded-2xl border border-white/80 bg-white/75 backdrop-blur-md p-5 shadow-glass">
        <div className="flex items-center justify-between border-b border-slate-100 pb-4 mb-4">
          <div>
            <h3 className="text-sm font-semibold text-slate-900 font-mono flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-brand-500" />
              Command Execution Duration Timeline
            </h3>
            <p className="text-xs text-slate-500">
              Historical command durations (ms) compared against established baseline.
            </p>
          </div>
          <div className="flex items-center gap-4 text-xs font-mono">
            <span className="flex items-center gap-1.5 text-brand-600 font-medium">
              <span className="h-2 w-2 rounded-full bg-brand-500" />
              Duration (ms)
            </span>
            {hasValidBaseline && (
              <span className="flex items-center gap-1.5 text-emerald-600 font-medium">
                <span className="h-0.5 w-3 bg-emerald-500" />
                Baseline ({baselineMs}ms)
              </span>
            )}
          </div>
        </div>

        <div className="h-72 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={runs} margin={{ top: 10, right: 20, left: -10, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
              <XAxis
                dataKey="timestamp"
                stroke="#94A3B8"
                tick={{ fontSize: 11, fill: '#64748B', fontFamily: 'monospace' }}
              />
              <YAxis
                stroke="#94A3B8"
                tick={{ fontSize: 11, fill: '#64748B', fontFamily: 'monospace' }}
                unit="ms"
              />
              <Tooltip content={<CustomTooltip />} />
              {hasValidBaseline && (
                <ReferenceLine
                  y={baselineMs}
                  stroke="#10b981"
                  strokeDasharray="4 4"
                  strokeWidth={2}
                  label={{
                    value: `Baseline: ${baselineMs}ms`,
                    fill: '#047857',
                    fontSize: 10,
                    fontFamily: 'monospace',
                    position: 'top',
                  }}
                />
              )}
              <Line
                type="monotone"
                dataKey="durationMs"
                stroke="#6478F5"
                strokeWidth={2.5}
                dot={(props) => {
                  const { cx, cy, payload } = props;
                  if (!Number.isFinite(cx) || !Number.isFinite(cy)) return null;
                  const isReg = payload?.isRegression;
                  return (
                    <circle
                      key={`dot-${payload?.id || cx}`}
                      cx={cx}
                      cy={cy}
                      r={isReg ? 6 : 4}
                      fill={isReg ? '#e11d48' : '#6478f5'}
                      stroke="#ffffff"
                      strokeWidth={2}
                    />
                  );
                }}
                activeDot={{ r: 7, fill: '#4f46e5' }}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Historical Benchmark Runs Table */}
      <div className="overflow-hidden rounded-2xl border border-white/80 bg-white/75 backdrop-blur-md shadow-glass">
        <div className="border-b border-slate-100 px-5 py-3.5 flex items-center justify-between">
          <h4 className="text-xs font-semibold text-slate-900 font-mono uppercase tracking-wider">
            Benchmark Run Records ({runs.length})
          </h4>
          <span className="text-[11px] font-mono text-slate-500 font-medium">
            Tolerance Threshold: ±{tolerancePercent}%
          </span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs font-mono">
            <thead className="bg-slate-50/80 text-slate-500 border-b border-slate-200/80">
              <tr>
                <th className="px-5 py-2.5">Run #</th>
                <th className="px-5 py-2.5">Timestamp</th>
                <th className="px-5 py-2.5">Command</th>
                <th className="px-5 py-2.5">Duration</th>
                <th className="px-5 py-2.5">Delta vs Baseline</th>
                <th className="px-5 py-2.5">Exit</th>
                <th className="px-5 py-2.5">Regression Assessment</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700">
              {runs.map((r, i) => {
                const diff = hasValidBaseline ? r.durationMs - baselineMs : 0;
                return (
                  <tr key={r.id || i} className="hover:bg-slate-50/60 transition-colors">
                    <td className="px-5 py-3 font-semibold text-slate-500">
                      #{r.runIndex || i + 1}
                    </td>
                    <td className="px-5 py-3 text-slate-500">{r.timestamp}</td>
                    <td className="px-5 py-3 text-slate-900">
                      <code className="bg-slate-100 px-2 py-0.5 rounded-lg border border-slate-200/80">
                        {r.command}
                      </code>
                    </td>
                    <td className="px-5 py-3 font-bold text-indigo-600">
                      {r.durationMs}ms
                    </td>
                    <td className="px-5 py-3">
                      {hasValidBaseline ? (
                        <span className={`font-semibold ${diff > 0 ? 'text-rose-600' : 'text-emerald-600'}`}>
                          {diff > 0 ? `+${diff}ms` : `${diff}ms`}
                        </span>
                      ) : (
                        <span className="text-slate-400">—</span>
                      )}
                    </td>
                    <td className="px-5 py-3">
                      <Badge variant={r.exitCode === 0 ? 'success' : 'danger'} size="xs">
                        {r.exitCode}
                      </Badge>
                    </td>
                    <td className="px-5 py-3">
                      {r.isRegression ? (
                        <Badge variant="danger" size="xs" dot>
                          Regression
                        </Badge>
                      ) : (
                        <Badge variant="success" size="xs">
                          Normal
                        </Badge>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
