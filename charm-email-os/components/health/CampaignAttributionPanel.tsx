'use client';

import { Megaphone, AlertTriangle, Skull, Shield } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import type { CampaignHealthMetrics } from '@/lib/types/health';
import { cn } from '@/lib/utils';

interface CampaignAttributionPanelProps {
  campaigns: CampaignHealthMetrics[];
}

export function CampaignAttributionPanel({ campaigns }: CampaignAttributionPanelProps) {
  // Sort by risk level: critical > high > medium > low
  const riskOrder = { critical: 0, high: 1, medium: 2, low: 3 };
  const sortedCampaigns = [...campaigns].sort(
    (a, b) => riskOrder[a.riskLevel] - riskOrder[b.riskLevel]
  );

  const criticalCampaigns = campaigns.filter((c) => c.riskLevel === 'critical').length;
  const highRiskCampaigns = campaigns.filter((c) => c.riskLevel === 'high').length;
  const quarantinedCampaigns = campaigns.filter((c) => c.state === 'quarantined').length;

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <Megaphone className="h-5 w-5" />
            Campaign Attribution
          </CardTitle>
          <div className="flex items-center gap-2 text-sm">
            {quarantinedCampaigns > 0 && (
              <span className="flex items-center gap-1 text-yellow-600">
                <Shield className="h-4 w-4" />
                {quarantinedCampaigns} quarantined
              </span>
            )}
            {criticalCampaigns > 0 && (
              <span className="flex items-center gap-1 text-red-600">
                <Skull className="h-4 w-4" />
                {criticalCampaigns} critical
              </span>
            )}
            {highRiskCampaigns > 0 && (
              <span className="flex items-center gap-1 text-orange-600">
                <AlertTriangle className="h-4 w-4" />
                {highRiskCampaigns} high risk
              </span>
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {campaigns.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            <Megaphone className="h-10 w-10 mx-auto mb-3 opacity-50" />
            <p className="font-medium">No campaigns found</p>
            <p className="text-sm mt-1">Campaign attribution will appear here</p>
          </div>
        ) : (
          <div className="space-y-1">
            {/* Header row */}
            <div className="grid grid-cols-12 gap-2 text-xs font-medium text-muted-foreground py-2 border-b">
              <div className="col-span-4">Campaign</div>
              <div className="col-span-2 text-center">Killed (7d)</div>
              <div className="col-span-2 text-center">Bounce %</div>
              <div className="col-span-2 text-center">Risk</div>
              <div className="col-span-2 text-center">Status</div>
            </div>

            {/* Campaign rows */}
            {sortedCampaigns.map((campaign) => (
              <div
                key={campaign.campaignId}
                className={cn(
                  'grid grid-cols-12 gap-2 py-3 items-center text-sm border-b last:border-0',
                  campaign.state === 'quarantined' && 'bg-yellow-50/50'
                )}
              >
                <div className="col-span-4 truncate">
                  <div className="font-medium">{campaign.campaignName}</div>
                  <div className="text-xs text-muted-foreground">
                    {campaign.totalSent.toLocaleString()} sent
                  </div>
                </div>
                <div className="col-span-2 text-center">
                  {campaign.inboxesKilled7d > 0 ? (
                    <span className="flex items-center justify-center gap-1 text-red-600">
                      <Skull className="h-3.5 w-3.5" />
                      {campaign.inboxesKilled7d}
                    </span>
                  ) : (
                    <span className="text-muted-foreground">0</span>
                  )}
                </div>
                <div
                  className={cn(
                    'col-span-2 text-center font-medium',
                    campaign.bounceRate > 5 && 'text-red-600',
                    campaign.bounceRate > 3 && campaign.bounceRate <= 5 && 'text-orange-600',
                    campaign.bounceRate > 2 && campaign.bounceRate <= 3 && 'text-yellow-600'
                  )}
                >
                  {campaign.bounceRate.toFixed(1)}%
                </div>
                <div className="col-span-2 text-center">
                  <Badge
                    variant={
                      campaign.riskLevel === 'critical'
                        ? 'destructive'
                        : campaign.riskLevel === 'high'
                        ? 'secondary'
                        : campaign.riskLevel === 'medium'
                        ? 'outline'
                        : 'default'
                    }
                    className={cn(
                      campaign.riskLevel === 'high' && 'bg-orange-100 text-orange-800',
                      campaign.riskLevel === 'medium' && 'bg-yellow-100 text-yellow-800'
                    )}
                  >
                    {campaign.riskLevel}
                  </Badge>
                </div>
                <div className="col-span-2 text-center">
                  {campaign.state === 'quarantined' ? (
                    <Badge variant="secondary" className="bg-yellow-100 text-yellow-800">
                      <Shield className="h-3 w-3 mr-1" />
                      Quarantined
                    </Badge>
                  ) : (
                    <span className="text-xs text-green-600">Active</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
