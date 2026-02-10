'use client';

import { cn } from '@/lib/utils';
import type { DomainHealthMetrics, DomainLifecyclePhase, DomainsByPhase } from '@/lib/types/health';
import { PHASE_COLORS, groupDomainsByPhase } from '@/lib/types/health';

interface DomainPhaseDistributionProps {
  domains: DomainHealthMetrics[];
  className?: string;
}

const PHASE_ORDER: DomainLifecyclePhase[] = [
  'warming',
  'ramping',
  'establishing',
  'peak',
  'monitoring',
  'rotation',
];

const PHASE_DAYS: Record<DomainLifecyclePhase, string> = {
  warming: '0-14d',
  ramping: '14-30d',
  establishing: '30-90d',
  peak: '90-180d',
  monitoring: '180-240d',
  rotation: '240d+',
};

export function DomainPhaseDistribution({ domains, className }: DomainPhaseDistributionProps) {
  const distribution = groupDomainsByPhase(domains);
  const total = domains.length;

  if (total === 0) {
    return (
      <div className={cn('text-sm text-muted-foreground text-center py-4', className)}>
        No domains to display
      </div>
    );
  }

  return (
    <div className={cn('space-y-3', className)}>
      <h4 className="text-sm font-medium">Domain Lifecycle Distribution</h4>

      {/* Segmented bar */}
      <div className="flex h-8 rounded-md overflow-hidden border">
        {PHASE_ORDER.map(phase => {
          const count = distribution[phase];
          if (count === 0) return null;

          const percentage = (count / total) * 100;
          const config = PHASE_COLORS[phase];

          return (
            <div
              key={phase}
              className={cn(
                config.bg,
                'flex items-center justify-center min-w-[40px] transition-all',
                config.text
              )}
              style={{ width: `${percentage}%` }}
              title={`${config.label}: ${count} domains (${percentage.toFixed(0)}%)`}
            >
              <span className="text-xs font-semibold">{count}</span>
            </div>
          );
        })}
      </div>

      {/* Legend */}
      <div className="grid grid-cols-3 md:grid-cols-6 gap-2 text-xs">
        {PHASE_ORDER.map(phase => {
          const count = distribution[phase];
          const config = PHASE_COLORS[phase];

          return (
            <div key={phase} className="flex flex-col items-center gap-0.5">
              <div className={cn(
                'w-full py-1 px-2 rounded text-center',
                count > 0 ? config.bg : 'bg-gray-50',
                count > 0 ? config.text : 'text-gray-400'
              )}>
                <span className="font-semibold">{count}</span>
              </div>
              <span className={cn(
                'text-center',
                count > 0 ? 'text-foreground' : 'text-muted-foreground'
              )}>
                {config.label}
              </span>
              <span className="text-muted-foreground">{PHASE_DAYS[phase]}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
