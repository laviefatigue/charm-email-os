'use client';

import { useMemo } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import {
  InventoryLifecycleStatus,
  LIFECYCLE_STATUS_CONFIG,
} from '@/lib/types/inventory';

// Segment configuration for the 4-segment chart
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
  dead: {
    bg: 'bg-gray-400',
    label: 'Dead',
    description: 'Killed or flagged for removal',
  },
} as const;

type SegmentType = keyof typeof SEGMENT_CONFIG;

interface InventorySegmentationChartProps {
  counts: {
    deployed: number;
    dead: number;
    reserve: number;
    incubating: number;
    total: number;
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
  // Calculate percentages for each segment
  const percentages = useMemo(() => {
    if (counts.total === 0) {
      return { deployed: 0, reserve: 0, incubating: 0, dead: 0 };
    }
    return {
      deployed: (counts.deployed / counts.total) * 100,
      reserve: (counts.reserve / counts.total) * 100,
      incubating: (counts.incubating / counts.total) * 100,
      dead: (counts.dead / counts.total) * 100,
    };
  }, [counts]);

  // Calculate cumulative positions for stacked bar
  const positions = useMemo(() => {
    return {
      deployed: 0,
      reserve: percentages.deployed,
      incubating: percentages.deployed + percentages.reserve,
      dead: percentages.deployed + percentages.reserve + percentages.incubating,
    };
  }, [percentages]);

  // Calculate live vs dead ratio
  const liveCount = counts.deployed + counts.reserve + counts.incubating;
  const deathRate = counts.total > 0 ? ((counts.dead / counts.total) * 100).toFixed(1) : '0';

  // Segment order for rendering (left to right)
  const segmentOrder: SegmentType[] = ['deployed', 'reserve', 'incubating', 'dead'];

  return (
    <Card className={cn('', className)}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg font-semibold">Inventory Segmentation</CardTitle>
          <div className="text-sm text-muted-foreground">
            <span className="font-medium text-foreground">{liveCount}</span> live
            {' / '}
            <span className="font-medium text-foreground">{counts.total}</span> total
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Main Stacked Bar */}
        <div className="space-y-2">
          <div className="relative h-12 bg-muted rounded-lg overflow-hidden">
            <TooltipProvider>
              {segmentOrder.map((segment) => {
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
                        {percentage > 8 && (
                          <span className="absolute inset-0 flex items-center justify-center text-white font-semibold text-sm">
                            {count}
                          </span>
                        )}
                      </button>
                    </TooltipTrigger>
                    <TooltipContent>
                      <p className="font-medium">{config.label}: {count}</p>
                      <p className="text-xs text-muted-foreground">{config.description}</p>
                      <p className="text-xs mt-1">{percentage.toFixed(1)}% of total</p>
                    </TooltipContent>
                  </Tooltip>
                );
              })}
            </TooltipProvider>
          </div>

          {/* Legend */}
          <div className="flex flex-wrap items-center gap-4 text-sm">
            {segmentOrder.map((segment) => {
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

        {/* Death Rate Indicator */}
        <div className="flex items-center justify-between p-3 rounded-lg bg-muted/50">
          <div className="flex items-center gap-4">
            <div>
              <span className="text-sm text-muted-foreground">Death Rate:</span>
              <span className={cn(
                'ml-2 font-semibold',
                Number(deathRate) > 30 ? 'text-red-600' :
                Number(deathRate) > 15 ? 'text-yellow-600' :
                'text-green-600'
              )}>
                {deathRate}%
              </span>
            </div>
            <div className="text-sm text-muted-foreground border-l pl-4">
              <span className="font-medium text-emerald-600">{counts.reserve}</span> ready to deploy
            </div>
          </div>
          <div className="text-xs text-muted-foreground">
            {Number(deathRate) > 30 && 'High death rate - review kill triggers'}
            {Number(deathRate) <= 30 && Number(deathRate) > 15 && 'Moderate death rate - monitor closely'}
            {Number(deathRate) <= 15 && 'Healthy death rate'}
          </div>
        </div>

        {/* Quick Stats Row */}
        <div className="grid grid-cols-4 gap-3">
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
            <div className="text-lg font-bold text-gray-700">{counts.dead}</div>
            <div className="text-xs text-gray-600">Dead</div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
