'use client';

import { Mail, CheckCircle, AlertTriangle, XCircle, TrendingUp, TrendingDown, Minus } from 'lucide-react';
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

  const reputationColors = {
    high: 'text-green-600',
    medium: 'text-yellow-600',
    low: 'text-orange-600',
    bad: 'text-red-600',
  };

  const formatDate = (date: Date) => {
    return new Date(date).toLocaleTimeString('en-US', {
      hour: 'numeric',
      minute: '2-digit',
    });
  };

  return (
    <div className="p-4 rounded-lg border bg-white">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <div
            className={cn(
              'w-8 h-8 rounded-lg flex items-center justify-center',
              esp.provider === 'gmail' ? 'bg-red-100' : 'bg-blue-100'
            )}
          >
            <Mail
              className={cn(
                'h-4 w-4',
                esp.provider === 'gmail' ? 'text-red-600' : 'text-blue-600'
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
      <div className="grid grid-cols-2 gap-4 mb-4">
        <div>
          <div className="text-sm text-muted-foreground">Inbox Placement</div>
          <div className="text-lg font-bold text-green-600">{esp.inboxPlacementRate}%</div>
        </div>
        <div>
          <div className="text-sm text-muted-foreground">Spam Placement</div>
          <div
            className={cn(
              'text-lg font-bold',
              esp.spamPlacementRate > 5 ? 'text-red-600' : 'text-muted-foreground'
            )}
          >
            {esp.spamPlacementRate}%
          </div>
        </div>
        {esp.promotionsPlacementRate !== undefined && (
          <div>
            <div className="text-sm text-muted-foreground">Promotions</div>
            <div className="text-lg font-bold text-muted-foreground">
              {esp.promotionsPlacementRate}%
            </div>
          </div>
        )}
        <div>
          <div className="text-sm text-muted-foreground">Trend</div>
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
                'font-medium capitalize',
                esp.reputationTrend === 'improving' && 'text-green-600',
                esp.reputationTrend === 'stable' && 'text-muted-foreground',
                esp.reputationTrend === 'declining' && 'text-red-600'
              )}
            >
              {esp.reputationTrend}
            </span>
          </div>
        </div>
      </div>

      {/* Authentication Status */}
      <div className="pt-3 border-t">
        <div className="text-sm font-medium mb-2">Authentication</div>
        <div className="flex items-center gap-4 text-sm">
          <div className="flex items-center gap-1">
            {esp.spfPassing ? (
              <CheckCircle className="h-3.5 w-3.5 text-green-600" />
            ) : (
              <XCircle className="h-3.5 w-3.5 text-red-600" />
            )}
            <span>SPF</span>
          </div>
          <div className="flex items-center gap-1">
            {esp.dkimPassing ? (
              <CheckCircle className="h-3.5 w-3.5 text-green-600" />
            ) : (
              <XCircle className="h-3.5 w-3.5 text-red-600" />
            )}
            <span>DKIM</span>
          </div>
          <div className="flex items-center gap-1">
            {esp.dmarcPassing ? (
              <CheckCircle className="h-3.5 w-3.5 text-green-600" />
            ) : (
              <XCircle className="h-3.5 w-3.5 text-red-600" />
            )}
            <span>DMARC</span>
          </div>
        </div>
      </div>

      {/* Provider-specific metrics */}
      {esp.provider === 'gmail' && esp.userReportedSpamRate !== undefined && (
        <div className="mt-3 pt-3 border-t">
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">User-reported Spam</span>
            <span
              className={cn(
                'font-medium',
                esp.userReportedSpamRate > 0.1 ? 'text-red-600' : 'text-green-600'
              )}
            >
              {esp.userReportedSpamRate}%
            </span>
          </div>
          {esp.ipReputation && (
            <div className="flex items-center justify-between text-sm mt-1">
              <span className="text-muted-foreground">IP Reputation</span>
              <span className={reputationColors[esp.ipReputation]}>{esp.ipReputation}</span>
            </div>
          )}
        </div>
      )}

      {esp.provider === 'microsoft' && (
        <div className="mt-3 pt-3 border-t">
          {esp.complaintRate !== undefined && (
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">Complaint Rate</span>
              <span
                className={cn(
                  'font-medium',
                  esp.complaintRate > 0.3 ? 'text-red-600' : 'text-green-600'
                )}
              >
                {esp.complaintRate}%
              </span>
            </div>
          )}
          {esp.trapHits !== undefined && (
            <div className="flex items-center justify-between text-sm mt-1">
              <span className="text-muted-foreground">Trap Hits</span>
              <span
                className={cn('font-medium', esp.trapHits > 0 ? 'text-red-600' : 'text-green-600')}
              >
                {esp.trapHits}
              </span>
            </div>
          )}
          {esp.filterResult && (
            <div className="flex items-center justify-between text-sm mt-1">
              <span className="text-muted-foreground">Filter Result</span>
              <Badge
                variant="outline"
                className={cn(
                  esp.filterResult === 'green' && 'bg-green-100 text-green-800',
                  esp.filterResult === 'yellow' && 'bg-yellow-100 text-yellow-800',
                  esp.filterResult === 'red' && 'bg-red-100 text-red-800',
                  'uppercase text-xs'
                )}
              >
                {esp.filterResult}
              </Badge>
            </div>
          )}
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
          ESP Health Summary
        </CardTitle>
      </CardHeader>
      <CardContent>
        {summaries.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            <Mail className="h-10 w-10 mx-auto mb-3 opacity-50" />
            <p className="font-medium">No ESP data available</p>
            <p className="text-sm mt-1">ESP metrics will appear when available</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {summaries.map((esp) => (
              <ESPCard key={esp.provider} esp={esp} />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
