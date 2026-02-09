'use client';

import { useState } from 'react';
import {
  Calendar,
  ChevronUp,
  ChevronDown,
  Pencil,
  Target,
  Sparkles,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { cn } from '@/lib/utils';
import { CampaignMiniCard, CampaignEmptySlot } from './CampaignMiniCard';
import type { CampaignCycle, CampaignSequence } from '@/lib/api';

interface ActiveCycleCardProps {
  cycle: CampaignCycle;
  campaigns: CampaignSequence[];
  selectedCampaignId: string | null;
  onSelectCampaign: (campaignId: string) => void;
  onEditCycle?: () => void;
  onGenerateCampaigns?: () => void;
  isGenerating?: boolean;
  className?: string;
}

function formatDate(dateString?: string) {
  if (!dateString) return null;
  return new Date(dateString).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

// Status badge config
const STATUS_CONFIG: Record<CampaignCycle['status'], { label: string; color: string }> = {
  planned: {
    label: 'Planned',
    color: 'bg-gray-100 text-gray-700',
  },
  active: {
    label: 'Active',
    color: 'bg-blue-100 text-blue-700',
  },
  completed: {
    label: 'Completed',
    color: 'bg-green-100 text-green-700',
  },
};

export function ActiveCycleCard({
  cycle,
  campaigns,
  selectedCampaignId,
  onSelectCampaign,
  onEditCycle,
  onGenerateCampaigns,
  isGenerating,
  className,
}: ActiveCycleCardProps) {
  const [isExpanded, setIsExpanded] = useState(true);

  const statusConfig = STATUS_CONFIG[cycle.status];
  const progress = (cycle.actualCampaigns / cycle.targetCampaigns) * 100;
  const isOddCycle = cycle.cycleNumber % 2 === 1;
  const evolutionGroup = isOddCycle ? 'Odd (1→3→5)' : 'Even (2→4→6)';

  // Calculate empty slots
  const emptySlots = Math.max(0, cycle.targetCampaigns - campaigns.length);

  // Date range display
  const startDate = formatDate(cycle.startDate);
  const endDate = formatDate(cycle.endDate);
  const dateRange = startDate && endDate ? `${startDate} - ${endDate}` : startDate || 'Dates not set';

  return (
    <Card className={cn('border-2', isOddCycle ? 'border-blue-200' : 'border-green-200', className)}>
      <CardHeader
        className="flex flex-row items-center justify-between space-y-0 pb-3 cursor-pointer"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="flex items-center gap-3">
          <div className={cn(
            'flex h-10 w-10 items-center justify-center rounded-lg',
            isOddCycle ? 'bg-blue-100' : 'bg-green-100'
          )}>
            <Target className={cn('w-5 h-5', isOddCycle ? 'text-blue-600' : 'text-green-600')} />
          </div>
          <div>
            <CardTitle className="text-base font-semibold flex items-center gap-2">
              {cycle.cycleName || `Cycle ${cycle.cycleNumber}`}
              <Badge className={statusConfig.color}>{statusConfig.label}</Badge>
            </CardTitle>
            <div className="flex items-center gap-2 text-xs text-muted-foreground mt-1">
              <Calendar className="w-3 h-3" />
              <span>{dateRange}</span>
              <span className="text-muted-foreground/50">•</span>
              <span>{cycle.durationDays} days</span>
              <span className="text-muted-foreground/50">•</span>
              <span className={isOddCycle ? 'text-blue-600' : 'text-green-600'}>
                {evolutionGroup}
              </span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {onEditCycle && (
            <Button
              variant="ghost"
              size="sm"
              className="h-8"
              onClick={(e) => {
                e.stopPropagation();
                onEditCycle();
              }}
            >
              <Pencil className="w-3.5 h-3.5" />
            </Button>
          )}
          {isExpanded ? (
            <ChevronUp className="h-4 w-4 text-muted-foreground" />
          ) : (
            <ChevronDown className="h-4 w-4 text-muted-foreground" />
          )}
        </div>
      </CardHeader>

      {isExpanded && (
        <CardContent className="pt-0 space-y-4">
          {/* Progress bar */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">Campaign Progress</span>
              <span className="font-medium">
                {cycle.actualCampaigns}/{cycle.targetCampaigns} campaigns
              </span>
            </div>
            <Progress value={progress} className="h-2" />
          </div>

          {/* Campaign grid */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {campaigns.map((campaign) => (
              <CampaignMiniCard
                key={campaign.id}
                campaign={campaign}
                isSelected={campaign.id === selectedCampaignId}
                onClick={() => onSelectCampaign(campaign.id)}
              />
            ))}

            {/* Empty slots */}
            {Array.from({ length: Math.min(emptySlots, 4 - campaigns.length) }).map((_, i) => (
              <CampaignEmptySlot
                key={`empty-${i}`}
                onClick={onGenerateCampaigns}
              />
            ))}
          </div>

          {/* Generate more button if under target */}
          {emptySlots > 0 && onGenerateCampaigns && (
            <div className="flex justify-center pt-2">
              <Button
                variant="outline"
                size="sm"
                onClick={onGenerateCampaigns}
                disabled={isGenerating}
                className="gap-2"
              >
                {isGenerating ? (
                  <span className="animate-spin">⏳</span>
                ) : (
                  <Sparkles className="w-4 h-4" />
                )}
                Generate {Math.min(4, emptySlots)} More Campaigns
              </Button>
            </div>
          )}

          {/* Notes */}
          {cycle.notes && (
            <div className="pt-2 border-t">
              <p className="text-xs text-muted-foreground">{cycle.notes}</p>
            </div>
          )}
        </CardContent>
      )}
    </Card>
  );
}
