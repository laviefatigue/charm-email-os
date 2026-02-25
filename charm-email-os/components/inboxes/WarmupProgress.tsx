'use client';

import { Progress } from '@/components/ui/progress';
import { cn } from '@/lib/utils';

interface WarmupProgressProps {
  progress: number;
  className?: string;
}

export function WarmupProgress({ progress, className }: WarmupProgressProps) {
  return (
    <div className={cn('flex items-center gap-2', className)}>
      <Progress value={progress} className="h-2 flex-1" />
      <span className="text-xs text-muted-foreground w-10 text-right">{progress}%</span>
    </div>
  );
}
