'use client';

/**
 * Column 4: Provider Cell - Simplified
 * Shows Entra/Google provider detected from EmailBison sync
 */

import type { WaterfallDomain } from '@/lib/types/infrastructure';

interface ProviderCellProps {
  domain: WaterfallDomain;
}

export function ProviderCell({ domain }: ProviderCellProps) {
  // Not purchased or DNS not ready
  if (!domain.isPurchased || domain.dnsStatus !== 'ready') {
    return (
      <div className="flex items-center gap-2 text-gray-400">
        <div className="w-2 h-2 rounded-full bg-gray-200" />
        <span className="text-sm">Not ready</span>
      </div>
    );
  }

  // Provider assigned - simple display
  if (domain.assignedProvider) {
    const isEntra = domain.assignedProvider === 'entra';
    const dotColor = isEntra ? 'bg-blue-500' : 'bg-red-500';
    const textColor = isEntra ? 'text-blue-700' : 'text-red-700';

    return (
      <div className="flex items-center gap-2">
        <div className={`w-2 h-2 rounded-full ${dotColor}`} />
        <span className={`font-medium text-sm ${textColor}`}>
          {isEntra ? 'Entra' : 'Google'}
        </span>
      </div>
    );
  }

  // No provider assigned - simple display
  return (
    <div className="flex items-center gap-2 text-gray-400">
      <div className="w-2 h-2 rounded-full bg-gray-300" />
      <span className="text-sm">Not assigned</span>
    </div>
  );
}
