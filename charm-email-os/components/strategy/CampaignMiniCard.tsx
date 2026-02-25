'use client';

import {
  Target,
  Users,
  TrendingUp,
  Shield,
  Star,
  CheckCircle2,
  XCircle,
  Clock,
  Send,
  Loader2,
} from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import type { CampaignSequence, CampaignAngle } from '@/lib/api';

interface CampaignMiniCardProps {
  campaign: CampaignSequence;
  isSelected?: boolean;
  onClick?: () => void;
  className?: string;
}

// Map campaign angles to display info
const ANGLE_INFO: Record<CampaignAngle, { label: string; shortLabel: string; icon: typeof Target; color: string }> = {
  custom_signal: {
    label: 'Research Signal',
    shortLabel: 'Signal',
    icon: Target,
    color: 'text-blue-600 bg-blue-50 border-blue-200',
  },
  persona_pain: {
    label: 'Persona Pain',
    shortLabel: 'Pain',
    icon: Users,
    color: 'text-purple-600 bg-purple-50 border-purple-200',
  },
  case_study: {
    label: 'Case Study',
    shortLabel: 'Proof',
    icon: TrendingUp,
    color: 'text-green-600 bg-green-50 border-green-200',
  },
  risk_efficiency: {
    label: 'Risk/Efficiency',
    shortLabel: 'Risk',
    icon: Shield,
    color: 'text-orange-600 bg-orange-50 border-orange-200',
  },
};

// Status badge config
const STATUS_CONFIG: Record<string, { label: string; icon: typeof Clock; color: string }> = {
  pending: {
    label: 'Pending',
    icon: Clock,
    color: 'bg-yellow-50 text-yellow-700 border-yellow-200',
  },
  approved: {
    label: 'Approved',
    icon: CheckCircle2,
    color: 'bg-green-50 text-green-700 border-green-200',
  },
  denied: {
    label: 'Denied',
    icon: XCircle,
    color: 'bg-red-50 text-red-700 border-red-200',
  },
  spintax_pending: {
    label: 'Processing',
    icon: Loader2,
    color: 'bg-purple-50 text-purple-700 border-purple-200',
  },
  spintaxed: {
    label: 'Ready',
    icon: CheckCircle2,
    color: 'bg-purple-50 text-purple-700 border-purple-200',
  },
  pushed: {
    label: 'Sent',
    icon: Send,
    color: 'bg-blue-50 text-blue-700 border-blue-200',
  },
};

export function CampaignMiniCard({
  campaign,
  isSelected,
  onClick,
  className,
}: CampaignMiniCardProps) {
  const angle = campaign.campaignAngle || 'custom_signal';
  const angleInfo = ANGLE_INFO[angle];
  const AngleIcon = angleInfo.icon;
  const statusInfo = STATUS_CONFIG[campaign.status] || STATUS_CONFIG.pending;
  const StatusIcon = statusInfo.icon;

  // Get a short name for display
  const displayName = campaign.campaignName?.split(' ').slice(0, 3).join(' ') || 'Campaign';

  return (
    <Card
      className={cn(
        'cursor-pointer transition-all hover:shadow-md',
        isSelected && 'ring-2 ring-primary shadow-md',
        className
      )}
      onClick={onClick}
    >
      <CardContent className="p-3">
        {/* Angle badge */}
        <div className={cn('inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium border mb-2', angleInfo.color)}>
          <AngleIcon className="w-3 h-3" />
          <span>{angleInfo.shortLabel}</span>
        </div>

        {/* Status + Version row */}
        <div className="flex items-center justify-between mb-2">
          <Badge variant="outline" className={cn('text-xs border', statusInfo.color)}>
            <StatusIcon className={cn('w-3 h-3 mr-1', campaign.status === 'spintax_pending' && 'animate-spin')} />
            {statusInfo.label}
          </Badge>
          {campaign.campaignVersion && (
            <Badge variant="secondary" className="text-xs">
              v{campaign.campaignVersion}
            </Badge>
          )}
        </div>

        {/* Campaign name */}
        <p className="text-sm font-medium truncate mb-1" title={campaign.campaignName}>
          {displayName}
        </p>

        {/* Target persona/segment */}
        {(campaign.targetPersona || campaign.targetSegment) && (
          <p className="text-xs text-muted-foreground truncate">
            {campaign.targetPersona || campaign.targetSegment}
          </p>
        )}

        {/* Score */}
        {campaign.score && (
          <div className="flex items-center gap-1 mt-2 text-xs text-muted-foreground">
            <Star className="w-3 h-3 text-yellow-500 fill-yellow-500" />
            <span>{campaign.score}/100</span>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// Empty slot card for incomplete cycles
export function CampaignEmptySlot({
  onClick,
  className,
}: {
  onClick?: () => void;
  className?: string;
}) {
  return (
    <Card
      className={cn(
        'cursor-pointer border-dashed transition-all hover:border-primary hover:bg-muted/50',
        className
      )}
      onClick={onClick}
    >
      <CardContent className="p-3 flex flex-col items-center justify-center min-h-[120px] text-muted-foreground">
        <div className="w-10 h-10 rounded-full border-2 border-dashed border-muted-foreground/30 flex items-center justify-center mb-2">
          <Target className="w-5 h-5 text-muted-foreground/50" />
        </div>
        <span className="text-xs">Generate</span>
      </CardContent>
    </Card>
  );
}
