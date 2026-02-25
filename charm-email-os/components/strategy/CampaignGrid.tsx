'use client';

import { UnifiedCampaignCard } from './UnifiedCampaignCard';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import type { UnifiedCampaign } from '@/lib/types';

interface CampaignGridProps {
  campaigns: UnifiedCampaign[];
  className?: string;
  onRequestRevisionCampaign?: (campaignNumber: 1 | 2 | 3 | 4) => void;
  onRequestRevisionEmail?: (campaignNumber: 1 | 2 | 3 | 4, position: 1 | 2 | 3 | 4) => void;
  // Approval callbacks
  onApprove?: (campaignId: string) => void;
  onDeny?: (campaignId: string) => void;
  onRequestRevision?: (campaignId: string, comment?: string) => void;
  approvingCampaignId?: string;
  // Spintax callbacks
  onTriggerSpintax?: (campaignId: string) => void;
  spintaxingCampaignId?: string;
  // Push callback
  onPushToEmailBison?: (campaignId: string) => void;
  pushingCampaignId?: string;
}

export function CampaignGrid({
  campaigns,
  className,
  onRequestRevisionCampaign,
  onRequestRevisionEmail,
  onApprove,
  onDeny,
  onRequestRevision,
  approvingCampaignId,
  onTriggerSpintax,
  spintaxingCampaignId,
  onPushToEmailBison,
  pushingCampaignId,
}: CampaignGridProps) {
  // Sort campaigns by campaign number to ensure consistent order
  const sortedCampaigns = [...campaigns].sort((a, b) => a.campaignNumber - b.campaignNumber);

  // Count campaigns by status for summary
  const statusCounts = campaigns.reduce((acc, c) => {
    acc[c.status] = (acc[c.status] || 0) + 1;
    return acc;
  }, {} as Record<string, number>);

  return (
    <div className={cn('space-y-4', className)}>
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold flex items-center gap-2">
          <span>Campaigns</span>
          <span className="text-sm font-normal text-muted-foreground">
            ({campaigns.length} of 4)
          </span>
        </h3>
        <div className="flex items-center gap-2">
          {statusCounts.approved && (
            <Badge variant="outline" className="text-xs bg-green-50 text-green-700 border-green-200">
              {statusCounts.approved} approved
            </Badge>
          )}
          {statusCounts.draft && (
            <Badge variant="outline" className="text-xs bg-yellow-50 text-yellow-700 border-yellow-200">
              {statusCounts.draft} pending
            </Badge>
          )}
          {statusCounts.spintaxed && (
            <Badge variant="outline" className="text-xs bg-purple-50 text-purple-700 border-purple-200">
              {statusCounts.spintaxed} ready
            </Badge>
          )}
        </div>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        {sortedCampaigns.map((campaign) => (
          <UnifiedCampaignCard
            key={campaign.id}
            campaign={campaign}
            onRequestRevisionCampaign={
              onRequestRevisionCampaign
                ? () => onRequestRevisionCampaign(campaign.campaignNumber)
                : undefined
            }
            onRequestRevisionEmail={
              onRequestRevisionEmail
                ? (position) => onRequestRevisionEmail(campaign.campaignNumber, position)
                : undefined
            }
            onApprove={onApprove ? () => onApprove(campaign.id) : undefined}
            onDeny={onDeny ? () => onDeny(campaign.id) : undefined}
            onRequestRevision={
              onRequestRevision
                ? (comment) => onRequestRevision(campaign.id, comment)
                : undefined
            }
            isApproving={approvingCampaignId === campaign.id}
            onTriggerSpintax={onTriggerSpintax ? () => onTriggerSpintax(campaign.id) : undefined}
            isSpintaxing={spintaxingCampaignId === campaign.id}
            onPushToEmailBison={onPushToEmailBison ? () => onPushToEmailBison(campaign.id) : undefined}
            isPushing={pushingCampaignId === campaign.id}
          />
        ))}
      </div>
    </div>
  );
}
