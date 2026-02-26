'use client';

/**
 * Column 3: DNS Cell - Simplified
 * Shows DNS configuration status
 */

import type { WaterfallDomain, DNSStatus } from '@/lib/types/infrastructure';
import { CheckCircle2, Clock, AlertTriangle, XCircle, RefreshCw } from 'lucide-react';

interface DNSCellProps {
  domain: WaterfallDomain;
}

const DNS_STATUS_CONFIG: Record<
  DNSStatus,
  {
    label: string;
    icon: typeof CheckCircle2;
    dotColor: string;
    pillClass: string;
  }
> = {
  pending: {
    label: 'Pending',
    icon: Clock,
    dotColor: 'bg-gray-300',
    pillClass: 'bg-gray-50 text-gray-600 border-gray-200',
  },
  propagating: {
    label: 'Propagating',
    icon: RefreshCw,
    dotColor: 'bg-blue-500',
    pillClass: 'bg-blue-50 text-blue-700 border-blue-200',
  },
  ready: {
    label: 'Ready',
    icon: CheckCircle2,
    dotColor: 'bg-green-500',
    pillClass: 'bg-green-50 text-green-700 border-green-200',
  },
  mismatch: {
    label: 'Mismatch',
    icon: AlertTriangle,
    dotColor: 'bg-amber-500',
    pillClass: 'bg-amber-50 text-amber-700 border-amber-200',
  },
  failed: {
    label: 'Failed',
    icon: XCircle,
    dotColor: 'bg-red-500',
    pillClass: 'bg-red-50 text-red-700 border-red-200',
  },
};

export function DNSCell({ domain }: DNSCellProps) {
  // Not purchased yet - show placeholder
  if (!domain.isPurchased) {
    return (
      <div className="flex items-center gap-2 text-gray-400">
        <div className="w-2 h-2 rounded-full bg-gray-200" />
        <span className="text-sm">Awaiting purchase</span>
      </div>
    );
  }

  const config = DNS_STATUS_CONFIG[domain.dnsStatus];

  // Simplified display - just status with color
  const textColor =
    domain.dnsStatus === 'ready' ? 'text-green-700' :
    domain.dnsStatus === 'mismatch' ? 'text-amber-700' :
    domain.dnsStatus === 'failed' ? 'text-red-700' :
    domain.dnsStatus === 'propagating' ? 'text-blue-700' :
    'text-gray-700';

  return (
    <div className="flex items-center gap-2">
      <div className={`w-2 h-2 rounded-full ${config.dotColor} ${
        domain.dnsStatus === 'propagating' ? 'animate-pulse' : ''
      }`} />
      <span className={`font-medium text-sm ${textColor}`}>
        {config.label}
      </span>
    </div>
  );
}
