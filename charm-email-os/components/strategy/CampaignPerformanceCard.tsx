'use client';

import {
  Send,
  Eye,
  MessageCircle,
  AlertTriangle,
  RefreshCw,
  ExternalLink,
  TrendingUp,
  TrendingDown,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import type { CampaignPerformanceMetrics } from '@/lib/api';

interface CampaignPerformanceCardProps {
  metrics: CampaignPerformanceMetrics;
  emailbisonCampaignId?: string;
  lastSync?: string;
  onRefresh?: () => Promise<void>;
  isRefreshing?: boolean;
  className?: string;
}

// Helper to format percentage with color coding
function formatRate(rate: number, type: 'open' | 'reply' | 'bounce'): { value: string; trend: 'good' | 'bad' | 'neutral' } {
  const formatted = `${(rate * 100).toFixed(1)}%`;

  // Benchmark thresholds (customize based on your data)
  if (type === 'open') {
    return { value: formatted, trend: rate >= 0.4 ? 'good' : rate >= 0.2 ? 'neutral' : 'bad' };
  }
  if (type === 'reply') {
    return { value: formatted, trend: rate >= 0.03 ? 'good' : rate >= 0.01 ? 'neutral' : 'bad' };
  }
  if (type === 'bounce') {
    return { value: formatted, trend: rate <= 0.02 ? 'good' : rate <= 0.05 ? 'neutral' : 'bad' };
  }

  return { value: formatted, trend: 'neutral' };
}

function MetricCard({
  icon: Icon,
  label,
  value,
  rate,
  rateType,
}: {
  icon: React.ElementType;
  label: string;
  value: number;
  rate?: number;
  rateType?: 'open' | 'reply' | 'bounce';
}) {
  const rateInfo = rate !== undefined && rateType ? formatRate(rate, rateType) : null;

  return (
    <div className="bg-white rounded-lg border p-3">
      <div className="flex items-center gap-2 mb-1">
        <Icon className="w-4 h-4 text-muted-foreground" />
        <span className="text-xs font-medium text-muted-foreground">{label}</span>
      </div>
      <div className="flex items-baseline gap-2">
        <span className="text-2xl font-bold">{value.toLocaleString()}</span>
        {rateInfo && (
          <span
            className={cn(
              'text-sm flex items-center gap-0.5',
              rateInfo.trend === 'good' && 'text-green-600',
              rateInfo.trend === 'bad' && 'text-red-600',
              rateInfo.trend === 'neutral' && 'text-yellow-600'
            )}
          >
            {rateInfo.trend === 'good' && <TrendingUp className="w-3 h-3" />}
            {rateInfo.trend === 'bad' && <TrendingDown className="w-3 h-3" />}
            {rateInfo.value}
          </span>
        )}
      </div>
    </div>
  );
}

export function CampaignPerformanceCard({
  metrics,
  emailbisonCampaignId,
  lastSync,
  onRefresh,
  isRefreshing,
  className,
}: CampaignPerformanceCardProps) {
  return (
    <Card className={cn('border-blue-200 bg-blue-50/50', className)}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm flex items-center gap-2">
            <div className="flex h-6 w-6 items-center justify-center rounded bg-blue-100">
              <TrendingUp className="w-3.5 h-3.5 text-blue-600" />
            </div>
            Campaign Performance
          </CardTitle>
          <div className="flex items-center gap-2">
            {lastSync && (
              <span className="text-xs text-muted-foreground">
                Last synced: {new Date(lastSync).toLocaleString()}
              </span>
            )}
            {onRefresh && (
              <Button
                variant="ghost"
                size="sm"
                className="h-7"
                onClick={onRefresh}
                disabled={isRefreshing}
              >
                <RefreshCw className={cn('w-3.5 h-3.5', isRefreshing && 'animate-spin')} />
              </Button>
            )}
            {emailbisonCampaignId && (
              <Badge variant="outline" className="text-xs bg-white">
                <ExternalLink className="w-3 h-3 mr-1" />
                EmailBison
              </Badge>
            )}
          </div>
        </div>
      </CardHeader>

      <CardContent className="pt-2">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <MetricCard
            icon={Send}
            label="Emails Sent"
            value={metrics.emailsSent}
          />
          <MetricCard
            icon={Eye}
            label="Opens"
            value={metrics.opens}
            rate={metrics.openRate}
            rateType="open"
          />
          <MetricCard
            icon={MessageCircle}
            label="Replies"
            value={metrics.replies}
            rate={metrics.replyRate}
            rateType="reply"
          />
          <MetricCard
            icon={AlertTriangle}
            label="Bounces"
            value={metrics.bounces}
            rate={metrics.bounceRate}
            rateType="bounce"
          />
        </div>

        {metrics.unsubscribes > 0 && (
          <div className="mt-3 text-xs text-muted-foreground">
            Unsubscribes: {metrics.unsubscribes}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
