'use client';

import { Badge } from '@/components/ui/badge';
import type { DomainLifecyclePhase } from '@/lib/types/health';
import { PHASE_COLORS } from '@/lib/types/health';
import { cn } from '@/lib/utils';

interface DomainPhaseBadgeProps {
  phase: DomainLifecyclePhase;
  showAction?: boolean;
  className?: string;
}

export function DomainPhaseBadge({ phase, showAction = false, className }: DomainPhaseBadgeProps) {
  const config = PHASE_COLORS[phase];

  return (
    <div className={cn('inline-flex flex-col items-start gap-0.5', className)}>
      <Badge className={cn(config.bg, config.text, 'font-medium capitalize hover:opacity-90')}>
        {config.label}
      </Badge>
      {showAction && config.action && (
        <span className="text-xs text-muted-foreground">{config.action}</span>
      )}
    </div>
  );
}
