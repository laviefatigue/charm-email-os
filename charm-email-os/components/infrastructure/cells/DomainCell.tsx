'use client';

/**
 * Column 1: Domain Cell - Clay.com Style
 * Shows domain name with status dot, badges, and legitimacy score
 */

import type { WaterfallDomain } from '@/lib/types/infrastructure';
import { TLD_DISPLAY } from '@/lib/types/infrastructure';
import { Crown, ExternalLink, Clock } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';

interface DomainCellProps {
  domain: WaterfallDomain;
}

export function DomainCell({ domain }: DomainCellProps) {
  // Extract domain parts for display
  const nameParts = domain.domainName.split('.');
  const tld = nameParts.pop() as keyof typeof TLD_DISPLAY;
  const domainBase = nameParts.join('.');

  // Determine status dot color based on domain state
  const getStatusDotColor = () => {
    if (domain.domainStatus === 'live') return 'bg-green-500';
    if (domain.domainStatus === 'flagged') return 'bg-amber-500';
    if (domain.domainStatus === 'dead') return 'bg-red-500';
    if (domain.isPurchased) return 'bg-blue-500';
    return 'bg-gray-300';
  };

  // Check if this is a legacy/external domain
  const isLegacy = domain.domainSource === 'legacy' || domain.domainSource === 'external';

  // Get relative time
  const relativeTime = (() => {
    try {
      return formatDistanceToNow(new Date(domain.generatedAt), { addSuffix: true });
    } catch {
      return null;
    }
  })();

  return (
    <div className="space-y-2">
      {/* Domain name with status dot */}
      <div className="flex items-center gap-2">
        <div className={`w-2 h-2 rounded-full ${getStatusDotColor()} flex-shrink-0 transition-colors`} />
        <span
          className="font-medium text-sm text-gray-900 truncate"
          title={domain.domainName}
        >
          {domainBase}
        </span>
        {/* TLD Badge */}
        <span className={`
          px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wide flex-shrink-0
          ${TLD_DISPLAY[tld]?.color ?? 'bg-gray-100 text-gray-600 border border-gray-200'}
        `}>
          .{tld}
        </span>
      </div>

      {/* Status pills */}
      <div className="flex gap-1.5 flex-wrap">
        {/* Owned badge */}
        {domain.ownedByClient && (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-amber-50 text-amber-700 rounded-md text-xs font-medium border border-amber-200">
            <Crown className="w-3 h-3" />
            Owned
          </span>
        )}

        {/* Legacy/External domain badge */}
        {isLegacy && (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-purple-50 text-purple-700 rounded-md text-xs font-medium border border-purple-200">
            <ExternalLink className="w-3 h-3" />
            Legacy
          </span>
        )}

        {/* Deployed badge */}
        {domain.isPurchased && domain.hypertideStatus === 'complete' && (
          <span className="px-2 py-0.5 bg-blue-50 text-blue-700 rounded-md text-xs font-medium border border-blue-200">
            Deployed
          </span>
        )}
      </div>

      {/* Legitimacy score bar (if available) */}
      {domain.legitimacyScore !== undefined && domain.legitimacyScore !== null && (
        <div className="flex items-center gap-2">
          <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden max-w-[80px]">
            <div
              className={`h-full rounded-full transition-all duration-300 ${
                domain.legitimacyScore >= 0.8
                  ? 'bg-green-500'
                  : domain.legitimacyScore >= 0.6
                  ? 'bg-amber-500'
                  : 'bg-red-500'
              }`}
              style={{ width: `${domain.legitimacyScore * 100}%` }}
            />
          </div>
          <span className={`text-xs font-medium ${
            domain.legitimacyScore >= 0.8
              ? 'text-green-600'
              : domain.legitimacyScore >= 0.6
              ? 'text-amber-600'
              : 'text-red-600'
          }`}>
            {Math.round(domain.legitimacyScore * 100)}%
          </span>
        </div>
      )}

      {/* Relative timestamp */}
      {relativeTime && (
        <div className="flex items-center gap-1 text-xs text-gray-400">
          <Clock className="w-3 h-3" />
          {relativeTime}
        </div>
      )}
    </div>
  );
}
