'use client';

import { Globe, Inbox, AlertTriangle, Clock } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { DomainPhaseBadge } from './DomainPhaseBadge';
import { HealthScoreRing } from './HealthScoreRing';
import type { DomainHealthMetrics } from '@/lib/types/health';
import { HEALTH_STATE_COLORS } from '@/lib/types/health';
import { cn } from '@/lib/utils';

interface DomainHealthCardProps {
  domain: DomainHealthMetrics;
  onClick?: () => void;
}

export function DomainHealthCard({ domain, onClick }: DomainHealthCardProps) {
  const stateColor = HEALTH_STATE_COLORS.domain[domain.state];

  return (
    <div
      className={cn(
        'p-4 rounded-lg border transition-all',
        domain.state === 'live' && 'border-green-200 bg-green-50/50 hover:border-green-300',
        domain.state === 'flagged' && 'border-yellow-200 bg-yellow-50/50 hover:border-yellow-300',
        domain.state === 'dead' && 'border-red-200 bg-red-50/50 hover:border-red-300',
        onClick && 'cursor-pointer'
      )}
      onClick={onClick}
    >
      {/* Header */}
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2 min-w-0">
          <Globe className="h-4 w-4 text-muted-foreground flex-shrink-0" />
          <span className="font-medium text-sm truncate">{domain.domain}</span>
        </div>
        <Badge className={cn(stateColor.bg, stateColor.text, 'uppercase text-xs')}>
          {domain.state}
        </Badge>
      </div>

      {/* Main content */}
      <div className="flex items-center gap-4">
        {/* Health Score Ring */}
        <HealthScoreRing score={domain.overallHealthScore} size="md" />

        {/* Stats */}
        <div className="flex-1 space-y-2">
          {/* Inbox count */}
          <div className="flex items-center gap-2 text-sm">
            <Inbox className="h-3.5 w-3.5 text-muted-foreground" />
            <span>
              <span className="font-medium text-green-600">{domain.liveInboxes}</span>
              <span className="text-muted-foreground">/{domain.totalInboxes} live</span>
            </span>
            {domain.deadInboxes > 0 && (
              <span className="text-xs text-red-600 flex items-center gap-0.5">
                <AlertTriangle className="h-3 w-3" />
                {domain.deadInboxes} dead
              </span>
            )}
          </div>

          {/* Warming count */}
          {domain.warmingInboxes > 0 && (
            <div className="text-xs text-muted-foreground">
              {domain.warmingInboxes} warming
            </div>
          )}
        </div>
      </div>

      {/* Footer */}
      <div className="mt-3 pt-3 border-t flex items-center justify-between">
        <DomainPhaseBadge phase={domain.phase} />
        <div className="flex items-center gap-1 text-xs text-muted-foreground">
          <Clock className="h-3 w-3" />
          {domain.daysUntilRotation > 0 ? (
            <span>{domain.daysUntilRotation}d to rotation</span>
          ) : (
            <span className="text-red-600 font-medium">Rotation overdue</span>
          )}
        </div>
      </div>

      {/* ESP Reputation indicators */}
      <div className="mt-2 flex gap-2">
        {domain.gmailReputation && (
          <div className="flex items-center gap-1 text-xs">
            <span className="text-muted-foreground">Gmail:</span>
            <span
              className={cn(
                'font-medium',
                domain.gmailReputation === 'high' && 'text-green-600',
                domain.gmailReputation === 'medium' && 'text-yellow-600',
                (domain.gmailReputation === 'low' || domain.gmailReputation === 'bad') &&
                  'text-red-600'
              )}
            >
              {domain.gmailReputation}
            </span>
          </div>
        )}
        {domain.microsoftReputation && (
          <div className="flex items-center gap-1 text-xs">
            <span className="text-muted-foreground">MS:</span>
            <span
              className={cn(
                'font-medium',
                domain.microsoftReputation === 'high' && 'text-green-600',
                domain.microsoftReputation === 'medium' && 'text-yellow-600',
                (domain.microsoftReputation === 'low' || domain.microsoftReputation === 'bad') &&
                  'text-red-600'
              )}
            >
              {domain.microsoftReputation}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
