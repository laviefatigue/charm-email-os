'use client';

import { useMemo, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { Badge } from '@/components/ui/badge';
import { ChevronDown, ChevronRight, AlertTriangle, ShieldAlert, ListX, Clock } from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  KillBreakdownResponse,
  KillCategory,
  KILL_CATEGORY_CONFIG,
} from '@/lib/types/health';

// Category icons mapping
const CATEGORY_ICONS = {
  reputation: ShieldAlert,
  listQuality: ListX,
  prematureDeployment: Clock,
  other: AlertTriangle,
} as const;

type CategoryKey = keyof typeof KILL_CATEGORY_CONFIG;

interface KillBreakdownChartProps {
  breakdown: KillBreakdownResponse | null;
  className?: string;
  showProviderSplit?: boolean;
}

export function KillBreakdownChart({
  breakdown,
  className,
  showProviderSplit = true,
}: KillBreakdownChartProps) {
  const [expandedCategory, setExpandedCategory] = useState<CategoryKey | null>(null);

  // Calculate category data with percentages
  const categoryData = useMemo(() => {
    if (!breakdown || breakdown.totalKilled === 0) {
      return [];
    }

    const categories: { key: CategoryKey; data: KillCategory; config: typeof KILL_CATEGORY_CONFIG[CategoryKey] }[] = [
      { key: 'reputation', data: breakdown.reputation, config: KILL_CATEGORY_CONFIG.reputation },
      { key: 'listQuality', data: breakdown.listQuality, config: KILL_CATEGORY_CONFIG.listQuality },
      { key: 'prematureDeployment', data: breakdown.prematureDeployment, config: KILL_CATEGORY_CONFIG.prematureDeployment },
      { key: 'other', data: breakdown.other, config: KILL_CATEGORY_CONFIG.other },
    ];

    // Filter out empty categories and sort by count
    return categories
      .filter(c => c.data.count > 0)
      .sort((a, b) => b.data.count - a.data.count);
  }, [breakdown]);

  // Calculate cumulative positions for stacked bar
  const barPositions = useMemo(() => {
    if (!breakdown || breakdown.totalKilled === 0) {
      return [];
    }

    let cumulative = 0;
    return categoryData.map(cat => {
      const start = cumulative;
      const width = cat.data.percentage;
      cumulative += width;
      return { ...cat, start, width };
    });
  }, [categoryData, breakdown]);

  // Get trigger details for a category
  const getTriggerDetails = (category: CategoryKey) => {
    if (!breakdown) return [];

    const categoryTriggers = breakdown[category]?.triggers || [];
    return breakdown.raw.filter(r => categoryTriggers.includes(r.trigger));
  };

  if (!breakdown) {
    return (
      <Card className={cn('', className)}>
        <CardHeader className="pb-2">
          <CardTitle className="text-lg font-semibold">Kill Trigger Breakdown</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center py-8 text-muted-foreground">
            Loading kill breakdown data...
          </div>
        </CardContent>
      </Card>
    );
  }

  if (breakdown.totalKilled === 0) {
    return (
      <Card className={cn('', className)}>
        <CardHeader className="pb-2">
          <CardTitle className="text-lg font-semibold">Kill Trigger Breakdown</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
            <Badge variant="outline" className="mb-2 text-green-600 border-green-300">
              No Deaths
            </Badge>
            <p className="text-sm">No inboxes killed by triggers in the last 30 days</p>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className={cn('', className)}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg font-semibold">Kill Trigger Breakdown</CardTitle>
          <div className="text-sm text-muted-foreground">
            <span className="font-medium text-foreground">{breakdown.totalKilled}</span> killed (30d)
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Stacked Bar Chart */}
        <div className="space-y-2">
          <div className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
            Distribution by Category
          </div>
          <div className="relative h-10 bg-muted rounded-lg overflow-hidden">
            <TooltipProvider>
              {barPositions.map(({ key, data, config, start, width }) => {
                const Icon = CATEGORY_ICONS[key];

                if (width === 0) return null;

                return (
                  <Tooltip key={key}>
                    <TooltipTrigger asChild>
                      <button
                        onClick={() => setExpandedCategory(expandedCategory === key ? null : key)}
                        className={cn(
                          'absolute h-full transition-all hover:brightness-110',
                          expandedCategory === key && 'ring-2 ring-offset-1 ring-foreground'
                        )}
                        style={{
                          left: `${start}%`,
                          width: `${width}%`,
                          backgroundColor: config.color,
                        }}
                      >
                        {/* Show count label if segment is wide enough */}
                        {width > 15 && (
                          <span className="absolute inset-0 flex items-center justify-center text-white font-semibold text-sm">
                            {data.count}
                          </span>
                        )}
                      </button>
                    </TooltipTrigger>
                    <TooltipContent>
                      <p className="font-medium">{config.label}: {data.count}</p>
                      <p className="text-xs text-muted-foreground">{config.description}</p>
                      <p className="text-xs mt-1">{data.percentage.toFixed(1)}% of kills</p>
                    </TooltipContent>
                  </Tooltip>
                );
              })}
            </TooltipProvider>
          </div>
        </div>

        {/* Category Legend with Expandable Details */}
        <div className="space-y-2">
          {categoryData.map(({ key, data, config }) => {
            const Icon = CATEGORY_ICONS[key];
            const isExpanded = expandedCategory === key;
            const triggerDetails = getTriggerDetails(key);

            return (
              <div key={key} className="space-y-1">
                <button
                  onClick={() => setExpandedCategory(isExpanded ? null : key)}
                  className="w-full flex items-center justify-between p-2 rounded-lg hover:bg-muted/50 transition-colors text-left"
                >
                  <div className="flex items-center gap-2">
                    <div
                      className="w-3 h-3 rounded-sm"
                      style={{ backgroundColor: config.color }}
                    />
                    <Icon className="h-4 w-4 text-muted-foreground" />
                    <span className="font-medium">{data.count}</span>
                    <span className="text-muted-foreground">{config.label}</span>
                    <span className="text-xs text-muted-foreground">
                      ({data.percentage.toFixed(0)}%)
                    </span>
                  </div>
                  {triggerDetails.length > 0 && (
                    isExpanded ? (
                      <ChevronDown className="h-4 w-4 text-muted-foreground" />
                    ) : (
                      <ChevronRight className="h-4 w-4 text-muted-foreground" />
                    )
                  )}
                </button>

                {/* Expanded Details */}
                {isExpanded && triggerDetails.length > 0 && (
                  <div
                    className="ml-5 pl-4 border-l-2 space-y-2 py-2"
                    style={{ borderColor: config.color }}
                  >
                    {/* Action Item */}
                    <div className="text-xs text-muted-foreground bg-muted/50 p-2 rounded">
                      <span className="font-medium">Action:</span> {config.action}
                    </div>

                    {/* Trigger Details */}
                    <div className="text-sm space-y-1">
                      {triggerDetails.map(detail => (
                        <div key={detail.trigger} className="flex items-center justify-between">
                          <span className="text-muted-foreground">
                            {formatTriggerName(detail.trigger)}
                          </span>
                          <div className="flex items-center gap-2 text-xs">
                            <span className="font-medium">{detail.count}</span>
                            {showProviderSplit && (detail.gmailCount > 0 || detail.microsoftCount > 0) && (
                              <span className="text-muted-foreground">
                                (G: {detail.gmailCount} / M: {detail.microsoftCount})
                              </span>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Provider Summary */}
        {showProviderSplit && (breakdown.byProvider.gmail > 0 || breakdown.byProvider.microsoft > 0) && (
          <div className="pt-2 border-t">
            <div className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-2">
              By Provider
            </div>
            <div className="flex gap-4">
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full bg-blue-500" />
                <span className="text-sm font-medium">{breakdown.byProvider.gmail}</span>
                <span className="text-sm text-muted-foreground">Gmail</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full bg-cyan-500" />
                <span className="text-sm font-medium">{breakdown.byProvider.microsoft}</span>
                <span className="text-sm text-muted-foreground">Microsoft</span>
              </div>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// Helper to format trigger names for display
function formatTriggerName(trigger: string): string {
  const names: Record<string, string> = {
    'spam_complaint': 'Spam Complaints',
    'hard_blocked_24h': 'Policy Blocks (24h)',
    'hard_unknown_24h': 'Invalid Addresses (24h)',
    'hard_bounces_24h': 'Hard Bounces (24h)',
    'fresh_inbox_bounce': 'Fresh Inbox Bounces',
    'hard_bounce_rate_7d': 'High Bounce Rate (7d)',
    'bounce_rate_all_7d': 'Total Bounce Rate (7d)',
    'provider_block': 'Provider Block',
    'consecutive_hard_bounces': 'Consecutive Bounces',
  };
  return names[trigger] || trigger.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
}
