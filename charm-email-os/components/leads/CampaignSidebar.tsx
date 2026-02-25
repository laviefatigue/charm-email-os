'use client';

import { Megaphone } from 'lucide-react';
import { cn } from '@/lib/utils';
import { StatusBadge } from '@/components/shared';
import type { Campaign } from '@/lib/types';
import { formatNumber } from '@/lib/utils';

interface CampaignSidebarProps {
  campaigns: Campaign[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

export function CampaignSidebar({ campaigns, selectedId, onSelect }: CampaignSidebarProps) {
  return (
    <div className="space-y-2">
      {campaigns.map((campaign) => (
        <button
          key={campaign.id}
          onClick={() => onSelect(campaign.id)}
          className={cn(
            'w-full text-left p-3 rounded-lg border transition-all',
            selectedId === campaign.id
              ? 'border-primary bg-primary/5 ring-1 ring-primary'
              : 'border-border hover:border-muted-foreground/30 hover:bg-muted/50'
          )}
        >
          <div className="flex items-start gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-muted">
              <Megaphone className="h-4 w-4 text-muted-foreground" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="font-medium text-sm truncate">{campaign.name}</p>
              <div className="flex items-center gap-2 mt-1">
                <span className="text-xs text-muted-foreground">
                  {formatNumber(campaign.leadsTotal)}/{formatNumber(campaign.leadsCapacity)}
                </span>
                <StatusBadge status={campaign.status} />
              </div>
            </div>
          </div>
        </button>
      ))}
    </div>
  );
}
