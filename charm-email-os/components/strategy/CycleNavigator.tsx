'use client';

import { Plus, Check } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import type { CampaignCycle } from '@/lib/api';

interface CycleNavigatorProps {
  cycles: CampaignCycle[];
  activeCycleId: string | null;
  onSelect: (cycleId: string) => void;
  onAddCycle?: () => void;
  className?: string;
}

// Visual hints for odd/even evolution groups
function getCycleColor(cycleNumber: number, status: CampaignCycle['status']) {
  const isOdd = cycleNumber % 2 === 1;

  if (status === 'completed') {
    return isOdd
      ? 'border-blue-300 bg-blue-50 text-blue-700'
      : 'border-green-300 bg-green-50 text-green-700';
  }

  if (status === 'active') {
    return isOdd
      ? 'border-blue-500 bg-blue-500 text-white shadow-sm shadow-blue-200'
      : 'border-green-500 bg-green-500 text-white shadow-sm shadow-green-200';
  }

  // Planned
  return 'border-gray-300 bg-white text-gray-600 hover:bg-gray-50';
}

export function CycleNavigator({
  cycles,
  activeCycleId,
  onSelect,
  onAddCycle,
  className,
}: CycleNavigatorProps) {
  // Sort cycles by number
  const sortedCycles = [...cycles].sort((a, b) => a.cycleNumber - b.cycleNumber);

  return (
    <div className={cn('flex items-center gap-2', className)}>
      <span className="text-sm font-medium text-muted-foreground mr-2">Cycles:</span>

      <div className="flex items-center gap-1.5 flex-wrap">
        {sortedCycles.map((cycle) => {
          const isSelected = cycle.id === activeCycleId;
          const colorClass = getCycleColor(cycle.cycleNumber, cycle.status);

          return (
            <button
              key={cycle.id}
              onClick={() => onSelect(cycle.id)}
              className={cn(
                'relative flex items-center justify-center min-w-[40px] h-9 px-3 rounded-full border-2 font-medium text-sm transition-all',
                colorClass,
                isSelected && 'ring-2 ring-offset-2 ring-primary',
                'hover:scale-105'
              )}
              title={cycle.cycleName || `Cycle ${cycle.cycleNumber}`}
            >
              {cycle.status === 'completed' && (
                <Check className="w-3 h-3 mr-1" />
              )}
              <span>{cycle.cycleNumber}</span>

              {/* Status indicator dot for active */}
              {cycle.status === 'active' && (
                <span className="absolute -top-0.5 -right-0.5 w-2.5 h-2.5 bg-yellow-400 rounded-full border-2 border-white animate-pulse" />
              )}
            </button>
          );
        })}

        {/* Add cycle button */}
        {onAddCycle && (
          <Button
            variant="outline"
            size="sm"
            className="h-9 px-3 rounded-full border-dashed"
            onClick={onAddCycle}
          >
            <Plus className="w-4 h-4" />
          </Button>
        )}
      </div>

      {/* Legend */}
      <div className="hidden md:flex items-center gap-3 ml-4 text-xs text-muted-foreground">
        <div className="flex items-center gap-1">
          <div className="w-3 h-3 rounded-full bg-blue-500" />
          <span>Odd (1,3,5)</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-3 h-3 rounded-full bg-green-500" />
          <span>Even (2,4,6)</span>
        </div>
      </div>
    </div>
  );
}
