'use client';

import { cn } from '@/lib/utils';
import type { SequenceSummaryStep } from '@/lib/types';

interface SequenceTimelineProps {
  currentPosition?: number;
  steps?: SequenceSummaryStep[];
  className?: string;
}

const DEFAULT_STEPS = [
  { position: 1, day: 0, type: 'new' as const, label: 'Email 1' },
  { position: 2, day: 3, type: 'thread' as const, label: 'Email 2' },
  { position: 3, day: 7, type: 'new' as const, label: 'Email 3' },
  { position: 4, day: 11, type: 'thread' as const, label: 'Email 4' },
];

export function SequenceTimeline({ currentPosition, steps, className }: SequenceTimelineProps) {
  // If dynamic steps are provided, use them
  if (steps && steps.length > 0) {
    return (
      <div className={cn('', className)}>
        <div className="grid grid-cols-4 gap-4">
          {steps.map((step, index) => (
            <div
              key={index}
              className={cn(
                'relative p-4 rounded-lg border-2',
                index === 0 ? 'border-primary bg-primary/5' : 'border-muted'
              )}
            >
              {/* Connector line */}
              {index < steps.length - 1 && (
                <div className="absolute top-1/2 -right-2 w-4 h-0.5 bg-muted" />
              )}

              {/* Day badge */}
              <div className="text-xs font-semibold text-muted-foreground mb-1">
                {step.day}
              </div>

              {/* Title */}
              <div className="font-medium text-sm mb-1">{step.title}</div>

              {/* Description */}
              <div className="text-xs text-muted-foreground">{step.description}</div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  // Legacy hardcoded timeline
  return (
    <div className={cn('py-3', className)}>
      {/* Day labels */}
      <div className="flex justify-between px-2 text-xs text-muted-foreground mb-1">
        {DEFAULT_STEPS.map((step) => (
          <span key={step.position} className="text-center w-16">
            Day {step.day}
          </span>
        ))}
      </div>

      {/* Timeline dots and lines */}
      <div className="flex items-center px-2">
        {DEFAULT_STEPS.map((step, index) => (
          <div key={step.position} className="flex items-center flex-1 last:flex-none">
            {/* Dot */}
            <div
              className={cn(
                'w-3 h-3 rounded-full border-2 flex-shrink-0',
                currentPosition === step.position
                  ? 'bg-blue-500 border-blue-500'
                  : 'bg-white border-gray-300'
              )}
            />
            {/* Line connecting to next dot */}
            {index < DEFAULT_STEPS.length - 1 && (
              <div className="flex-1 h-0.5 bg-gray-200 mx-1" />
            )}
          </div>
        ))}
      </div>

      {/* Labels */}
      <div className="flex justify-between px-2 text-xs mt-1">
        {DEFAULT_STEPS.map((step) => (
          <div key={step.position} className="text-center w-16">
            <span className="font-medium">{step.label}</span>
            <br />
            <span className={cn(
              'text-[10px]',
              step.type === 'new' ? 'text-blue-600' : 'text-gray-500'
            )}>
              {step.type === 'new' ? '(New)' : '(Thread)'}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
