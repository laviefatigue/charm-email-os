'use client';

/**
 * Column 4: HyperTide Cell - Simplified Single Indicator
 * Shows inbox provisioning order status with light blue "Ready" → dark blue "Processing" flow
 */

import { useEffect, useState } from 'react';
import type { WaterfallDomain } from '@/lib/types/infrastructure';
import {
  Loader2,
  CheckCircle2,
  XCircle,
  Waves,
} from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';
import { useWaterfallStore } from '@/lib/stores/waterfallStore';

interface HyperTideCellProps {
  domain: WaterfallDomain;
}

// Color constants for HyperTide states
const COLORS = {
  notReady: {
    dot: 'bg-gray-200',
    text: 'text-gray-400',
  },
  ready: {
    dot: 'bg-sky-400',
    text: 'text-sky-700',
    badge: 'bg-sky-50 text-sky-700 border-sky-200',
  },
  processing: {
    dot: 'bg-blue-600',
    text: 'text-blue-700',
    badge: 'bg-blue-50 text-blue-700 border-blue-200',
  },
  complete: {
    dot: 'bg-green-500',
    text: 'text-green-700',
    badge: 'bg-green-50 text-green-700 border-green-200',
  },
  failed: {
    dot: 'bg-red-500',
    text: 'text-red-700',
    badge: 'bg-red-50 text-red-700 border-red-200',
  },
};

export function HyperTideCell({ domain }: HyperTideCellProps) {
  // Not ready for HyperTide
  if (!domain.isReadyForHyperTide && domain.hypertideStatus === 'not_ordered') {
    return (
      <div className="flex items-center gap-2">
        <div className={`w-2 h-2 rounded-full ${COLORS.notReady.dot}`} />
        <span className={`text-sm ${COLORS.notReady.text}`}>Not ready</span>
      </div>
    );
  }

  // Handle different HyperTide statuses
  switch (domain.hypertideStatus) {
    case 'not_ordered':
      return <ReadyState domain={domain} />;
    case 'ordered':
    case 'provisioning':
      return <ProcessingState domain={domain} />;
    case 'complete':
      return <CompleteState domain={domain} />;
    case 'failed':
      return <FailedState domain={domain} />;
    default:
      return null;
  }
}

// Ready to order state - LIGHT BLUE
function ReadyState({ domain }: { domain: WaterfallDomain }) {
  return (
    <div className="space-y-1.5">
      {/* Single indicator */}
      <div className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-xs font-medium border ${COLORS.ready.badge}`}>
        <div className={`w-2 h-2 rounded-full ${COLORS.ready.dot}`} />
        <span>Ready</span>
      </div>
    </div>
  );
}

// Processing state - DARK BLUE with pulse and polling
function ProcessingState({ domain }: { domain: WaterfallDomain }) {
  const { refreshWaterfall } = useWaterfallStore();
  const [isPolling, setIsPolling] = useState(false);
  const isProvisioning = domain.hypertideStatus === 'provisioning';

  // Poll for status updates every 30 seconds
  useEffect(() => {
    if (domain.hypertideStatus !== 'ordered' && domain.hypertideStatus !== 'provisioning') {
      return;
    }

    const pollStatus = async () => {
      setIsPolling(true);
      try {
        // Trigger a waterfall refresh to check for status updates
        await refreshWaterfall();
      } catch (err) {
        console.error('Status poll failed:', err);
      } finally {
        setIsPolling(false);
      }
    };

    // Poll every 30 seconds
    const interval = setInterval(pollStatus, 30000);
    return () => clearInterval(interval);
  }, [domain.hypertideStatus, refreshWaterfall]);

  return (
    <div className="space-y-1.5">
      {/* Single indicator with pulse */}
      <div className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-xs font-medium border ${COLORS.processing.badge}`}>
        <div className={`w-2 h-2 rounded-full ${COLORS.processing.dot} animate-pulse`} />
        <Loader2 className="w-3 h-3 animate-spin" />
        <span>{isProvisioning ? 'Provisioning' : 'Processing'}</span>
      </div>

      {/* Timestamp */}
      {domain.hypertideOrderedAt && (
        <div className="text-[11px] text-gray-400">
          {(() => {
            try {
              return formatDistanceToNow(new Date(domain.hypertideOrderedAt), { addSuffix: true });
            } catch {
              return 'Recently';
            }
          })()}
        </div>
      )}
    </div>
  );
}

// Complete state - GREEN
function CompleteState({ domain }: { domain: WaterfallDomain }) {
  return (
    <div className="space-y-1.5">
      {/* Single indicator */}
      <div className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-xs font-medium border ${COLORS.complete.badge}`}>
        <CheckCircle2 className="w-3.5 h-3.5" />
        <span>Complete</span>
      </div>

      {/* Timestamp */}
      {domain.hypertideCompletedAt && (
        <div className="text-[11px] text-gray-400">
          {(() => {
            try {
              return formatDistanceToNow(new Date(domain.hypertideCompletedAt), { addSuffix: true });
            } catch {
              return 'Recently';
            }
          })()}
        </div>
      )}
    </div>
  );
}

// Failed state - RED
function FailedState({ domain }: { domain: WaterfallDomain }) {
  return (
    <div className="space-y-1.5">
      {/* Single indicator */}
      <div className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-xs font-medium border ${COLORS.failed.badge}`}>
        <XCircle className="w-3.5 h-3.5" />
        <span>Failed</span>
      </div>

      {/* Retry button */}
      <button className="w-full px-2 py-1 bg-red-50 text-red-700 rounded text-xs font-medium hover:bg-red-100 transition-colors border border-red-200">
        Retry
      </button>
    </div>
  );
}
