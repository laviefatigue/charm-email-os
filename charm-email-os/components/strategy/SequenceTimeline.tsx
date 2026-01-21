'use client';

import { cn } from '@/lib/utils';

interface SequenceTimelineProps {
  currentPosition?: number;
  className?: string;
}

const TIMELINE_STEPS = [
  { position: 1, day: 0, type: 'new' as const, label: 'Email 1' },
  { position: 2, day: 3, type: 'thread' as const, label: 'Email 2' },
  { position: 3, day: 7, type: 'new' as const, label: 'Email 3' },
  { position: 4, day: 11, type: 'thread' as const, label: 'Email 4' },
];

export function SequenceTimeline({ currentPosition, className }: SequenceTimelineProps) {
  return (
    <div className={cn('py-3', className)}>
      {/* Day labels */}
      <div className="flex justify-between px-2 text-xs text-muted-foreground mb-1">
        {TIMELINE_STEPS.map((step) => (
          <span key={step.position} className="text-center w-16">
            Day {step.day}
          </span>
        ))}
      </div>

      {/* Timeline dots and lines */}
      <div className="flex items-center px-2">
        {TIMELINE_STEPS.map((step, index) => (
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
            {index < TIMELINE_STEPS.length - 1 && (
              <div className="flex-1 h-0.5 bg-gray-200 mx-1" />
            )}
          </div>
        ))}
      </div>

      {/* Labels */}
      <div className="flex justify-between px-2 text-xs mt-1">
        {TIMELINE_STEPS.map((step) => (
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
