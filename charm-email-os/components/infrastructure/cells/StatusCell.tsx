'use client';

/**
 * Column 6: Status Cell - Clay.com Style
 * Shows Live/Flagged/Dead status with inbox counts and progress
 */

import { useMemo } from 'react';
import type { WaterfallDomain, DomainStatus } from '@/lib/types/infrastructure';
import {
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Mail,
  Clock,
  WifiOff,
  Skull,
  Eye,
  RefreshCw,
  AlertOctagon,
  ShieldAlert,
  Plug,
} from 'lucide-react';

// Flagged reason type - explains WHY a domain is flagged
type FlaggedReason = 'inbox_killed' | 'all_disconnected' | null;

interface StatusCellProps {
  domain: WaterfallDomain;
}

const STATUS_CONFIG: Record<
  DomainStatus,
  {
    label: string;
    icon: typeof CheckCircle2;
    dotColor: string;
    pillClass: string;
    progressColor: string;
  }
> = {
  live: {
    label: 'Live',
    icon: CheckCircle2,
    dotColor: 'bg-green-500',
    pillClass: 'bg-green-50 text-green-700 border-green-200',
    progressColor: 'bg-green-500',
  },
  flagged: {
    label: 'Flagged',
    icon: AlertTriangle,
    dotColor: 'bg-amber-500',
    pillClass: 'bg-amber-50 text-amber-700 border-amber-200',
    progressColor: 'bg-amber-500',
  },
  monitoring: {
    label: 'Monitoring',
    icon: Eye,
    dotColor: 'bg-blue-500',
    pillClass: 'bg-blue-50 text-blue-700 border-blue-200',
    progressColor: 'bg-blue-500',
  },
  dead: {
    label: 'Dead',
    icon: XCircle,
    dotColor: 'bg-red-500',
    pillClass: 'bg-red-50 text-red-700 border-red-200',
    progressColor: 'bg-red-500',
  },
};

// Flagged sub-types with distinct styling
const FLAGGED_VARIANT_CONFIG = {
  inbox_killed: {
    label: 'Flagged',
    icon: AlertTriangle,
    pillClass: 'bg-amber-50 text-amber-700 border-amber-200',
  },
  all_disconnected: {
    label: 'Disconnected',
    icon: WifiOff,
    pillClass: 'bg-orange-50 text-orange-600 border-orange-200',
  },
} as const;

// Rotation recommendation styling - only show when action needed
// Using perceptually balanced colors (inspired by OKLCH design principles)
const ROTATION_CONFIG = {
  not_applicable: null,
  healthy: null, // Don't show - everything is fine (intentional minimalism)
  monitor: {
    label: 'Monitor',
    icon: Eye,
    // Soft indigo - subtle attention without alarm
    pillClass: 'bg-indigo-50 text-indigo-600 border-indigo-200',
    animate: false,
  },
  consider_rotate: {
    label: 'Consider Rotate',
    icon: RefreshCw,
    // Warm amber - moderate attention
    pillClass: 'bg-amber-50 text-amber-700 border-amber-300',
    animate: false,
  },
  rotate_now: {
    label: 'Rotate Now',
    icon: AlertOctagon,
    // Warm rose - urgent but not harsh (softer than bootstrap red)
    pillClass: 'bg-rose-50 text-rose-700 border-rose-300',
    animate: true, // Subtle pulse
  },
} as const;

export function StatusCell({ domain }: StatusCellProps) {
  // Legacy domains with inboxes should show status even without HyperTide order
  const isLegacyWithInboxes = domain.domainSource === 'legacy' && domain.totalInboxCount > 0;

  // Not yet provisioned (unless legacy with inboxes)
  if (!isLegacyWithInboxes && (domain.hypertideStatus !== 'complete' || domain.totalInboxCount === 0)) {
    return (
      <div className="flex flex-col items-start justify-center gap-1.5">
        <div className="flex items-center gap-2 text-gray-400">
          <div className="w-2 h-2 rounded-full bg-gray-200" />
          <span className="text-sm">Awaiting sync</span>
        </div>
        <div className="flex items-center gap-1 text-xs text-gray-400">
          <Clock className="w-3 h-3" />
          No inboxes synced yet
        </div>
      </div>
    );
  }

  // Compute flagged reason - helps users understand WHY a domain is flagged
  const flaggedReason: FlaggedReason = useMemo(() => {
    if (domain.domainStatus !== 'flagged') return null;

    // If has dead inboxes, killed by trigger (bounces/spam)
    if (domain.deadInboxCount > 0) return 'inbox_killed';

    // If all live inboxes are disconnected (OAuth expired, needs reconnection)
    if (domain.liveInboxCount > 0 && domain.connectedInboxCount === 0) {
      return 'all_disconnected';
    }

    return null;
  }, [domain.domainStatus, domain.deadInboxCount, domain.liveInboxCount, domain.connectedInboxCount]);

  // Get badge config - use variant for flagged domains
  const badgeConfig = useMemo(() => {
    if (domain.domainStatus === 'flagged' && flaggedReason) {
      return FLAGGED_VARIANT_CONFIG[flaggedReason];
    }
    return STATUS_CONFIG[domain.domainStatus];
  }, [domain.domainStatus, flaggedReason]);

  const BadgeIcon = badgeConfig.icon;
  const config = STATUS_CONFIG[domain.domainStatus];

  // Calculate operational ratio: connected / live inboxes
  // This shows what % of your live inboxes are actually working
  const operationalRatio = domain.liveInboxCount > 0
    ? Math.round((domain.connectedInboxCount / domain.liveInboxCount) * 100)
    : 0;

  // Determine progress bar color based on operational status
  const getProgressColor = () => {
    if (operationalRatio === 0 && domain.liveInboxCount > 0) return 'bg-red-500';
    if (operationalRatio < 50) return 'bg-amber-500';
    if (operationalRatio < 100) return 'bg-yellow-500';
    return config.progressColor;
  };

  // Get rotation config if action needed
  const rotationConfig = domain.rotationRecommendation
    ? ROTATION_CONFIG[domain.rotationRecommendation]
    : null;

  // Build tooltip with error context
  const getRotationTooltip = () => {
    const parts: string[] = [];
    parts.push(`Capacity: ${domain.capacityRemainingPct?.toFixed(0) ?? '?'}%`);
    parts.push(`Connected: ${domain.connectedInboxCount}/${domain.expectedInboxCount ?? domain.liveInboxCount}`);

    if (domain.hasCompromisedInboxes) {
      parts.push('⚠️ COMPROMISED - Do not reconnect');
    }
    if (domain.inboxesWithComplaints > 0) {
      parts.push(`Spam complaints: ${domain.inboxesWithComplaints} inbox(es)`);
    }
    if (domain.inboxesWithBlocks > 0) {
      parts.push(`Hard blocks: ${domain.inboxesWithBlocks} inbox(es)`);
    }
    if (domain.recommendedAction) {
      const actionLabels: Record<string, string> = {
        rotate: 'Action: Rotate domain',
        reconnect: 'Action: Reconnect inboxes',
        watch: 'Action: Monitor closely',
        none: '',
      };
      if (actionLabels[domain.recommendedAction]) {
        parts.push(actionLabels[domain.recommendedAction]);
      }
    }
    return parts.join(' | ');
  };

  return (
    <div className="space-y-2">
      {/* Rotation Recommendation - only show when action needed */}
      {rotationConfig && (
        <div
          className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-xs font-medium border ${rotationConfig.pillClass} ${
            rotationConfig.animate ? 'animate-pulse' : ''
          }`}
          title={getRotationTooltip()}
        >
          <rotationConfig.icon className="w-3.5 h-3.5" />
          {rotationConfig.label}
        </div>
      )}

      {/* Compromised Indicator - shows WHY rotation is needed */}
      {domain.hasCompromisedInboxes && (
        <div
          className="inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-xs font-medium border bg-red-50 text-red-700 border-red-200"
          title="Domain has spam complaints or hard blocks. Rotation recommended - do not reconnect."
        >
          <ShieldAlert className="w-3.5 h-3.5" />
          Compromised
        </div>
      )}

      {/* Reconnect Candidate - show when worth saving */}
      {domain.recommendedAction === 'reconnect' && !domain.hasCompromisedInboxes && (
        <div
          className="inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-xs font-medium border bg-blue-50 text-blue-700 border-blue-200"
          title="Disconnected inboxes have clean history. Worth reconnecting."
        >
          <Plug className="w-3.5 h-3.5" />
          Reconnect
        </div>
      )}

      {/* Status Badge - shows Disconnected/Flagged/Live/Dead */}
      <div className="flex flex-col gap-1">
        <div className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-xs font-medium border ${badgeConfig.pillClass}`}>
          <BadgeIcon className="w-3.5 h-3.5" />
          {badgeConfig.label}
        </div>

        {/* Killed count - only show if there are dead inboxes */}
        {domain.deadInboxCount > 0 && (
          <div
            className="flex items-center gap-1 text-xs text-red-600"
            title="Inbox killed due to bounces or spam complaints"
          >
            <Skull className="w-3 h-3" />
            <span>{domain.deadInboxCount} inbox{domain.deadInboxCount > 1 ? 'es' : ''} killed</span>
          </div>
        )}
      </div>

      {/* Inbox Count - connected/live (operational capacity) */}
      <div className="flex items-center gap-1.5">
        <Mail className="w-3.5 h-3.5 text-gray-500" />
        <span className="text-sm font-medium text-gray-900">
          {domain.connectedInboxCount}
          <span className="text-gray-400">/{domain.liveInboxCount}</span>
        </span>
        <span className="text-xs text-gray-500">connected</span>
      </div>

      {/* Connection Status Warning - only show for partial disconnection (not when badge already says Disconnected) */}
      {domain.disconnectedInboxCount > 0 && domain.connectedInboxCount > 0 && (
        <div className="flex items-center gap-1 text-xs text-amber-600" title="Needs reconnection via HyperTide">
          <WifiOff className="w-3 h-3" />
          <span>{domain.disconnectedInboxCount} need reconnection</span>
        </div>
      )}

      {/* Disconnection Time Warning - 21-day auto-kill threshold */}
      {domain.daysDisconnected != null && domain.daysDisconnected > 0 && (
        <div
          className={`flex items-center gap-1 text-xs ${
            domain.daysDisconnected >= 18
              ? 'text-red-600 font-semibold'
              : domain.daysDisconnected >= 14
              ? 'text-amber-600 font-medium'
              : 'text-gray-500'
          }`}
          title={
            domain.daysDisconnected >= 18
              ? `URGENT: Auto-kill in ${21 - domain.daysDisconnected} days!`
              : `Disconnected ${domain.daysDisconnected} days ago. Auto-kill at 21 days.`
          }
        >
          <Clock className="w-3 h-3" />
          {domain.daysDisconnected >= 18 ? (
            <span className="animate-pulse">
              {21 - domain.daysDisconnected}d until auto-kill!
            </span>
          ) : (
            <span>Disconnected {domain.daysDisconnected}d</span>
          )}
        </div>
      )}

      {/* Progress Bar - shows operational capacity */}
      <div className="flex items-center gap-2">
        <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-300 ${getProgressColor()}`}
            style={{ width: `${Math.min(operationalRatio, 100)}%` }}
          />
        </div>
        <span className="text-xs font-medium text-gray-600 w-8">{operationalRatio}%</span>
      </div>
    </div>
  );
}
