'use client';

import { Play, Pause } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { StatusBadge } from '@/components/shared';
import type { Campaign } from '@/lib/types';

interface CampaignHeaderProps {
  campaign: Campaign;
  onRun: () => void;
  onPause: () => void;
}

export function CampaignHeader({ campaign, onRun, onPause }: CampaignHeaderProps) {
  const canRun = campaign.status === 'draft' || campaign.status === 'paused';
  const canPause = campaign.status === 'active';

  return (
    <div className="flex items-center justify-between pb-4 border-b">
      <div className="flex items-center gap-3">
        <h2 className="text-xl font-semibold">{campaign.name}</h2>
        <StatusBadge status={campaign.status} />
      </div>

      <div className="flex items-center gap-2">
        {canRun && (
          <Button onClick={onRun} className="bg-primary hover:bg-primary/90">
            <Play className="h-4 w-4 mr-2" />
            RUN
          </Button>
        )}
        {canPause && (
          <Button onClick={onPause} variant="outline">
            <Pause className="h-4 w-4 mr-2" />
            Pause
          </Button>
        )}
      </div>
    </div>
  );
}
