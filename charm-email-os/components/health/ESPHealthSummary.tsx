'use client';

import { Mail, TrendingUp, TrendingDown, Minus } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import type { ESPHealthSummary as ESPHealthSummaryType } from '@/lib/types/health';
import { cn } from '@/lib/utils';

interface ESPHealthSummaryProps {
  summaries: ESPHealthSummaryType[];
}

function ESPCard({ esp }: { esp: ESPHealthSummaryType }) {
  const trendIcon = {
    improving: TrendingUp,
    stable: Minus,
    declining: TrendingDown,
  };
  const TrendIcon = trendIcon[esp.reputationTrend];

  const formatDate = (date: Date) => {
    return new Date(date).toLocaleTimeString('en-US', {
      hour: 'numeric',
      minute: '2-digit',
    });
  };

  // Build trigger breakdown for display
  const triggerBreakdown = [
    { label: 'Spam', count: esp.spamKills, color: 'text-red-600' },
    { label: 'Blocked', count: esp.blockKills, color: 'text-orange-600' },
    { label: 'Unknown', count: esp.unknownKills, color: 'text-yellow-600' },
    { label: 'Bounce', count: esp.bounceKills, color: 'text-amber-600' },
    { label: 'Disconnect', count: esp.disconnectKills, color: 'text-blue-600' },
  ].filter(t => t.count > 0);

  return (
    <div className="p-4 rounded-lg border bg-white">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <div
            className={cn(
              'w-8 h-8 rounded-lg flex items-center justify-center',
              esp.provider === 'gmail' ? 'bg-red-100' :
              esp.provider === 'microsoft' ? 'bg-blue-100' : 'bg-gray-100'
            )}
          >
            <Mail
              className={cn(
                'h-4 w-4',
                esp.provider === 'gmail' ? 'text-red-600' :
                esp.provider === 'microsoft' ? 'text-blue-600' : 'text-gray-600'
              )}
            />
          </div>
          <div>
            <h4 className="font-semibold capitalize">{esp.provider}</h4>
            <span className="text-xs text-muted-foreground">
              Updated {formatDate(esp.lastUpdated)}
            </span>
          </div>
        </div>
        <Badge
          variant={
            esp.reputation === 'high'
              ? 'default'
              : esp.reputation === 'medium'
              ? 'secondary'
              : 'destructive'
          }
          className={cn(
            'uppercase',
            esp.reputation === 'medium' && 'bg-yellow-100 text-yellow-800'
          )}
        >
          {esp.reputation}
        </Badge>
      </div>

      {/* Metrics Grid */}
      <div className="grid grid-cols-3 gap-4 mb-4">
        <div>
          <div className="text-sm text-muted-foreground">Live</div>
          <div className="text-lg font-bold text-green-600">{esp.liveInboxes}</div>
        </div>
        <div>
          <div className="text-sm text-muted-foreground">Dead</div>
          <div className={cn(
            'text-lg font-bold',
            esp.deadInboxes > 0 ? 'text-red-600' : 'text-muted-foreground'
          )}>
            {esp.deadInboxes}
          </div>
        </div>
        <div>
          <div className="text-sm text-muted-foreground">Kill Rate</div>
          <div className={cn(
            'text-lg font-bold',
            esp.killRate >= 30 ? 'text-red-600' :
            esp.killRate >= 15 ? 'text-orange-600' :
            esp.killRate >= 5 ? 'text-yellow-600' : 'text-green-600'
          )}>
            {esp.killRate}%
          </div>
        </div>
      </div>

      {/* Health Score + Trend */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <div className="text-sm text-muted-foreground">Avg Health Score</div>
          <div className="text-lg font-bold">{esp.avgHealthScore}</div>
        </div>
        <div className="flex items-center gap-1">
          <TrendIcon
            className={cn(
              'h-4 w-4',
              esp.reputationTrend === 'improving' && 'text-green-600',
              esp.reputationTrend === 'stable' && 'text-muted-foreground',
              esp.reputationTrend === 'declining' && 'text-red-600'
            )}
          />
          <span
            className={cn(
              'text-sm font-medium capitalize',
              esp.reputationTrend === 'improving' && 'text-green-600',
              esp.reputationTrend === 'stable' && 'text-muted-foreground',
              esp.reputationTrend === 'declining' && 'text-red-600'
            )}
          >
            {esp.reputationTrend}
          </span>
        </div>
      </div>

      {/* Kill Trigger Breakdown */}
      {triggerBreakdown.length > 0 && (
        <div className="pt-3 border-t">
          <div className="text-sm font-medium mb-2">Kill Triggers</div>
          <div className="space-y-1">
            {triggerBreakdown.map((trigger) => (
              <div key={trigger.label} className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">{trigger.label}</span>
                <span className={cn('font-medium', trigger.color)}>{trigger.count}</span>
              </div>
            ))}
          </div>
          {esp.topTrigger && (
            <div className="mt-2 text-xs text-muted-foreground">
              Top trigger: <span className="font-medium">{esp.topTrigger}</span>
            </div>
          )}
        </div>
      )}

      {/* No kills state */}
      {triggerBreakdown.length === 0 && esp.totalInboxes > 0 && (
        <div className="pt-3 border-t">
          <div className="text-sm text-green-600 font-medium">No kill triggers detected</div>
        </div>
      )}
    </div>
  );
}

export function ESPHealthSummary({ summaries }: ESPHealthSummaryProps) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2">
          <Mail className="h-5 w-5" />
          ESP Kill Rate Analysis
        </CardTitle>
      </CardHeader>
      <CardContent>
        {summaries.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            <Mail className="h-10 w-10 mx-auto mb-3 opacity-50" />
            <p className="font-medium">No ESP Data Available</p>
            <p className="text-sm mt-1">ESP data will appear once inboxes are synced</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {summaries.map((esp) => (
              <ESPCard key={esp.provider} esp={esp} />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
