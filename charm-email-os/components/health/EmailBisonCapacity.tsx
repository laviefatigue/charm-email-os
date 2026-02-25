'use client';

import { useState, useEffect, useCallback } from 'react';
import { Mail, RefreshCw, AlertTriangle, Loader2 } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { cn } from '@/lib/utils';
import { api } from '@/lib/api';

interface EmailBisonCapacityData {
  liveInboxes: number;
  totalInboxes: number;
  dailySendLimit: number;
  warmingInboxes: number;
  deadInboxes: number;
  warmupDistribution: {
    range_0_25: number;
    range_25_50: number;
    range_50_75: number;
    range_75_100: number;
  };
  lastSynced: string;
}

interface EmailBisonCapacityProps {
  clientId: string;
  className?: string;
}

function WarmupDistributionBar({
  label,
  count,
  total,
  color,
}: {
  label: string;
  count: number;
  total: number;
  color: string;
}) {
  const percentage = total > 0 ? (count / total) * 100 : 0;

  return (
    <div className="flex items-center gap-3 text-sm">
      <span className="w-16 text-muted-foreground text-xs">{label}</span>
      <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
        <div
          className={cn('h-full rounded-full transition-all duration-300', color)}
          style={{ width: `${percentage}%` }}
        />
      </div>
      <span className="w-8 text-xs text-muted-foreground text-right">{count}</span>
    </div>
  );
}

export function EmailBisonCapacity({ clientId, className }: EmailBisonCapacityProps) {
  const [data, setData] = useState<EmailBisonCapacityData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSyncing, setIsSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchCapacity = useCallback(async (forceSync = false) => {
    try {
      if (forceSync) {
        setIsSyncing(true);
      } else {
        setIsLoading(true);
      }
      setError(null);

      const response = await api.health.getEmailBisonCapacity(clientId, forceSync);
      setData(response);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setIsLoading(false);
      setIsSyncing(false);
    }
  }, [clientId]);

  useEffect(() => {
    fetchCapacity();
  }, [fetchCapacity]);

  const handleSync = () => {
    fetchCapacity(true);
  };

  const formatTime = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  // Loading state
  if (isLoading && !data) {
    return (
      <Card className={className}>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2">
            <Mail className="h-5 w-5" />
            Sending Capacity
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        </CardContent>
      </Card>
    );
  }

  // Error state
  if (error && !data) {
    return (
      <Card className={className}>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2">
            <Mail className="h-5 w-5" />
            Sending Capacity
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-center py-6 text-muted-foreground">
            <AlertTriangle className="h-8 w-8 mx-auto mb-2 text-yellow-500" />
            <p className="text-sm">Failed to load capacity data</p>
            <Button variant="link" size="sm" onClick={() => fetchCapacity()}>
              Retry
            </Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (!data) return null;

  const livePercentage = data.totalInboxes > 0
    ? (data.liveInboxes / data.totalInboxes) * 100
    : 0;

  const warmingTotal = data.warmupDistribution.range_0_25 +
    data.warmupDistribution.range_25_50 +
    data.warmupDistribution.range_50_75 +
    data.warmupDistribution.range_75_100;

  const capacityStatus = livePercentage >= 50 ? 'healthy' : livePercentage >= 25 ? 'warning' : 'critical';

  return (
    <Card className={className}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <Mail className="h-5 w-5" />
            Sending Capacity
            <span className="text-xs font-normal text-muted-foreground">(EmailBison)</span>
          </CardTitle>
          <div className="flex items-center gap-2">
            {data.lastSynced && (
              <span className="text-xs text-muted-foreground">
                {formatTime(data.lastSynced)}
              </span>
            )}
            <Button
              variant="ghost"
              size="sm"
              onClick={handleSync}
              disabled={isSyncing}
              className="h-7 px-2"
            >
              <RefreshCw className={cn('h-3.5 w-3.5', isSyncing && 'animate-spin')} />
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-5">
        {/* Primary Stats */}
        <div className="grid grid-cols-2 gap-4">
          {/* Live Inboxes */}
          <div className="space-y-2">
            <div className="flex items-baseline justify-between">
              <span className="text-sm text-muted-foreground">Live Inboxes</span>
              <span className={cn(
                'text-lg font-bold',
                capacityStatus === 'healthy' && 'text-green-600',
                capacityStatus === 'warning' && 'text-yellow-600',
                capacityStatus === 'critical' && 'text-red-600'
              )}>
                {data.liveInboxes}
                <span className="text-sm font-normal text-muted-foreground">
                  /{data.totalInboxes}
                </span>
              </span>
            </div>
            <Progress
              value={livePercentage}
              className={cn(
                'h-2',
                capacityStatus === 'healthy' && '[&>div]:bg-green-500',
                capacityStatus === 'warning' && '[&>div]:bg-yellow-500',
                capacityStatus === 'critical' && '[&>div]:bg-red-500'
              )}
            />
          </div>

          {/* Daily Send Limit */}
          <div className="space-y-2">
            <div className="flex items-baseline justify-between">
              <span className="text-sm text-muted-foreground">Daily Limit</span>
              <span className="text-lg font-bold">
                {data.dailySendLimit.toLocaleString()}
              </span>
            </div>
            <p className="text-xs text-muted-foreground">
              Based on warmup progress
            </p>
          </div>
        </div>

        {/* Secondary Stats */}
        <div className="grid grid-cols-2 gap-4 pt-2 border-t">
          <div className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">Warming</span>
            <span className="text-sm font-medium text-blue-600">{data.warmingInboxes}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">Dead/Paused</span>
            <span className={cn(
              'text-sm font-medium',
              data.deadInboxes > 50 ? 'text-red-600' : 'text-gray-600'
            )}>
              {data.deadInboxes}
            </span>
          </div>
        </div>

        {/* Warmup Distribution */}
        {warmingTotal > 0 && (
          <div className="pt-3 border-t space-y-2">
            <h4 className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Warmup Progress
            </h4>
            <div className="space-y-1.5">
              <WarmupDistributionBar
                label="0-25%"
                count={data.warmupDistribution.range_0_25}
                total={warmingTotal}
                color="bg-red-400"
              />
              <WarmupDistributionBar
                label="25-50%"
                count={data.warmupDistribution.range_25_50}
                total={warmingTotal}
                color="bg-yellow-400"
              />
              <WarmupDistributionBar
                label="50-75%"
                count={data.warmupDistribution.range_50_75}
                total={warmingTotal}
                color="bg-blue-400"
              />
              <WarmupDistributionBar
                label="75-100%"
                count={data.warmupDistribution.range_75_100}
                total={warmingTotal}
                color="bg-green-400"
              />
            </div>
          </div>
        )}

        {/* Warning */}
        {data.deadInboxes > 100 && (
          <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-3 text-sm text-yellow-800">
            <AlertTriangle className="h-4 w-4 inline mr-1" />
            {data.deadInboxes} dead inboxes - consider cleanup or replacement
          </div>
        )}
      </CardContent>
    </Card>
  );
}
