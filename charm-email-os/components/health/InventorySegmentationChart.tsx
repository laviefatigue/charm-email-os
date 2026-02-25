'use client';

import { useMemo } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { Skull } from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  InventoryLifecycleStatus,
  LIFECYCLE_STATUS_CONFIG,
} from '@/lib/types/inventory';

// Segment configuration for LIVE categories only (dead shown separately)
const SEGMENT_CONFIG = {
  deployed: {
    bg: 'bg-green-500',
    label: 'Deployed',
    description: 'Assigned to campaign and actively sending',
  },
  reserve: {
    bg: 'bg-blue-500',
    label: 'Reserve',
    description: 'Warmed 14+ days, ready to deploy',
  },
  incubating: {
    bg: 'bg-amber-500',
    label: 'Incubating',
    description: 'Warming for less than 14 days',
  },
} as const;

type LiveSegmentType = keyof typeof SEGMENT_CONFIG;
type SegmentType = LiveSegmentType | 'dead';

interface InventorySegmentationChartProps {
  counts: {
    deployed: number;
    dead: number;
    reserve: number;
    incubating: number;
    total: number;
    killedByTrigger?: number;  // System-killed (health metric)
    deactivated?: number;  // Business churn (not a health problem)
  };
  onSegmentClick?: (segment: SegmentType) => void;
  selectedSegment?: SegmentType | null;
  className?: string;
}

export function InventorySegmentationChart({
  counts,
  onSegmentClick,
  selectedSegment,
  className,
}: InventorySegmentationChartProps) {
  // Calculate live count (excludes dead)
  const liveCount = counts.deployed + counts.reserve + counts.incubating;

  // Calculate percentages based on LIVE total only (dead shown separately)
  const percentages = useMemo(() => {
    if (liveCount === 0) {
      return { deployed: 0, reserve: 0, incubating: 0 };
    }
    return {
      deployed: (counts.deployed / liveCount) * 100,
      reserve: (counts.reserve / liveCount) * 100,
      incubating: (counts.incubating / liveCount) * 100,
    };
  }, [counts, liveCount]);

  // Calculate cumulative positions for stacked bar (live segments only)
  const positions = useMemo(() => {
    return {
      deployed: 0,
      reserve: percentages.deployed,
      incubating: percentages.deployed + percentages.reserve,
    };
  }, [percentages]);

  // Separate killed (health issue) from deactivated (business churn)
  const killedByTrigger = counts.killedByTrigger ?? 0;
  const deactivated = counts.deactivated ?? (counts.dead - killedByTrigger);

  // Kill rate = killed / (live + killed) - excludes business churn for accurate health metric
  const killRateBase = liveCount + killedByTrigger;
  const killRate = killRateBase > 0 ? ((killedByTrigger / killRateBase) * 100).toFixed(1) : '0';

  // Total death rate for context (includes all dead)
  const deathRate = counts.total > 0 ? ((counts.dead / counts.total) * 100).toFixed(1) : '0';

  // Live segment order for rendering (left to right) - no dead in main bar
  const liveSegmentOrder: LiveSegmentType[] = ['deployed', 'reserve', 'incubating'];

  return (
    <Card className={cn('', className)}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg font-semibold">Inbox Distribution</CardTitle>
          <div className="text-sm text-muted-foreground">
            <span className="font-medium text-foreground">{liveCount}</span> live
            {counts.dead > 0 && (
              <>
                {' / '}
                <span className="font-medium text-gray-500">{counts.dead}</span> dead
              </>
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* LIVE INVENTORY Section */}
        <div className="space-y-2">
          <div className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
            Live Inventory ({liveCount} inboxes)
          </div>
          <div className="relative h-10 bg-muted rounded-lg overflow-hidden">
            <TooltipProvider>
              {liveSegmentOrder.map((segment) => {
                const percentage = percentages[segment];
                const position = positions[segment];
                const count = counts[segment];
                const config = SEGMENT_CONFIG[segment];

                if (percentage === 0) return null;

                return (
                  <Tooltip key={segment}>
                    <TooltipTrigger asChild>
                      <button
                        onClick={() => onSegmentClick?.(segment)}
                        className={cn(
                          'absolute h-full transition-all hover:brightness-110',
                          config.bg,
                          selectedSegment === segment && 'ring-2 ring-offset-1 ring-foreground'
                        )}
                        style={{
                          left: `${position}%`,
                          width: `${percentage}%`,
                        }}
                      >
                        {/* Show count label if segment is wide enough */}
                        {percentage > 12 && (
                          <span className="absolute inset-0 flex items-center justify-center text-white font-semibold text-sm">
                            {count}
                          </span>
                        )}
                      </button>
                    </TooltipTrigger>
                    <TooltipContent>
                      <p className="font-medium">{config.label}: {count}</p>
                      <p className="text-xs text-muted-foreground">{config.description}</p>
                      <p className="text-xs mt-1">{percentage.toFixed(1)}% of live inventory</p>
                    </TooltipContent>
                  </Tooltip>
                );
              })}
            </TooltipProvider>
          </div>

          {/* Live Inventory Legend */}
          <div className="flex flex-wrap items-center gap-4 text-sm">
            {liveSegmentOrder.map((segment) => {
              const config = SEGMENT_CONFIG[segment];
              const count = counts[segment];
              const percentage = percentages[segment];

              return (
                <button
                  key={segment}
                  onClick={() => onSegmentClick?.(segment)}
                  className={cn(
                    'flex items-center gap-1.5 hover:opacity-80 transition-opacity',
                    selectedSegment === segment && 'underline underline-offset-2'
                  )}
                >
                  <div className={cn('w-3 h-3 rounded-sm', config.bg)} />
                  <span className="font-medium">{count}</span>
                  <span className="text-muted-foreground">{config.label}</span>
                  <span className="text-xs text-muted-foreground">({percentage.toFixed(0)}%)</span>
                </button>
              );
            })}
          </div>
        </div>

        {/* DEAD INBOXES Section - Shown separately with kill vs deactivated breakdown */}
        {counts.dead > 0 && (
          <div className="space-y-2 pt-2 border-t">
            <div className="flex items-center justify-between">
              <div className="text-xs font-medium text-muted-foreground uppercase tracking-wide flex items-center gap-1.5">
                <Skull className="h-3.5 w-3.5 text-gray-500" />
                Dead Inboxes ({counts.dead})
              </div>
              <span className={cn(
                'text-sm font-medium',
                Number(killRate) > 15 ? 'text-red-600' :
                Number(killRate) > 5 ? 'text-amber-600' :
                'text-gray-600'
              )}>
                {killRate}% kill rate
              </span>
            </div>

            {/* Killed by Trigger - Health issue */}
            {killedByTrigger > 0 && (
              <button
                onClick={() => onSegmentClick?.('dead')}
                className={cn(
                  'w-full p-3 rounded-lg bg-red-50 border border-red-200 hover:bg-red-100 transition-colors text-left',
                  selectedSegment === 'dead' && 'ring-2 ring-offset-1 ring-red-500'
                )}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded-sm bg-red-500" />
                    <span className="font-semibold text-red-700">{killedByTrigger}</span>
                    <span className="text-red-600">killed by triggers</span>
                  </div>
                  <div className="text-xs text-red-600">
                    Health problem - review kill triggers
                  </div>
                </div>
              </button>
            )}

            {/* Deactivated - Business churn */}
            {deactivated > 0 && (
              <div className="w-full p-3 rounded-lg bg-gray-50 border border-gray-200 text-left">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded-sm bg-gray-400" />
                    <span className="font-semibold text-gray-600">{deactivated}</span>
                    <span className="text-gray-500">deactivated</span>
                  </div>
                  <div className="text-xs text-gray-500">
                    Business churn - not a health issue
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Summary Stats Row */}
        <div className="grid grid-cols-4 gap-3 pt-2">
          <div className="text-center p-2 rounded-lg bg-green-50">
            <div className="text-lg font-bold text-green-700">{counts.deployed}</div>
            <div className="text-xs text-green-600">Deployed</div>
          </div>
          <div className="text-center p-2 rounded-lg bg-blue-50">
            <div className="text-lg font-bold text-blue-700">{counts.reserve}</div>
            <div className="text-xs text-blue-600">Reserve</div>
          </div>
          <div className="text-center p-2 rounded-lg bg-amber-50">
            <div className="text-lg font-bold text-amber-700">{counts.incubating}</div>
            <div className="text-xs text-amber-600">Incubating</div>
          </div>
          <div className="text-center p-2 rounded-lg bg-gray-100">
            <div className="text-lg font-bold text-gray-500">{counts.dead}</div>
            <div className="text-xs text-gray-500">Dead</div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
