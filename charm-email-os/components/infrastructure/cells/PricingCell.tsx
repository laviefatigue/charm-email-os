'use client';

/**
 * Column 2: Pricing Cell - Clay.com Style
 * Shows registrar prices, best price indicator, buy button, or purchased status
 */

import { useState } from 'react';
import type { WaterfallDomain } from '@/lib/types/infrastructure';
import { PRICE_BUDGET_LIMIT } from '@/lib/types/infrastructure';
import { Check, ShoppingCart, AlertTriangle, Clock, RefreshCw, Loader2 } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';

interface PricingCellProps {
  domain: WaterfallDomain;
  onBuy?: (domainId: string) => void;
  isSelected?: boolean;
}

export function PricingCell({ domain, onBuy, isSelected }: PricingCellProps) {
  const [checking, setChecking] = useState(false);

  // Already purchased (or legacy domain with inboxes)
  if (domain.isPurchased) {
    // Check if this is a legacy domain (externally purchased, has inboxes)
    const isLegacy = domain.domainSource === 'legacy' && !domain.purchasedAt;

    const purchaseDate = domain.purchasedAt
      ? (() => {
          try {
            return formatDistanceToNow(new Date(domain.purchasedAt), { addSuffix: true });
          } catch {
            return null;
          }
        })()
      : null;

    return (
      <div className="space-y-2">
        {/* Status with filled dot - purple for legacy, green for purchased */}
        <div className="flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full ${isLegacy ? 'bg-purple-500' : 'bg-green-500'}`} />
          <span className={`font-medium text-sm ${isLegacy ? 'text-purple-700' : 'text-green-700'}`}>
            {isLegacy ? 'External' : 'Purchased'}
          </span>
        </div>

        {/* For legacy domains, show "Pre-existing" instead of price */}
        {isLegacy ? (
          <div className="text-xs text-gray-500">
            Pre-existing domain
          </div>
        ) : domain.purchasePrice ? (
          <div className="text-xs text-gray-600">
            <span className="font-medium">${domain.purchasePrice.toFixed(2)}</span>
            <span className="text-gray-400"> via </span>
            <span className="capitalize">{domain.purchaseRegistrar}</span>
          </div>
        ) : null}

        {/* Timestamp - only for non-legacy */}
        {!isLegacy && purchaseDate && (
          <div className="flex items-center gap-1 text-xs text-gray-400">
            <Clock className="w-3 h-3" />
            {purchaseDate}
          </div>
        )}
      </div>
    );
  }

  // Not purchased - show pricing
  const hasPricing = domain.porkbunPrice != null || domain.dynadotPrice != null;
  const isOverBudget = domain.isOverBudget;

  if (!hasPricing) {
    // Check if domain was recently generated (within 5 minutes) - prices may still be loading
    const isRecentlyGenerated = domain.generatedAt &&
      (Date.now() - new Date(domain.generatedAt).getTime()) < 5 * 60 * 1000;
    const isAwaitingPrice = !domain.priceCheckedAt && isRecentlyGenerated;

    // Show loading state if auto-pricing is likely running
    if (isAwaitingPrice) {
      return (
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <Loader2 className="w-4 h-4 animate-spin text-indigo-400" />
            <span className="text-sm text-indigo-500">Checking price...</span>
          </div>
        </div>
      );
    }

    return (
      <div className="space-y-2 group/cell">
        {/* Empty state */}
        <div className="flex items-center gap-2 text-gray-400">
          <div className="w-2 h-2 rounded-full bg-gray-300" />
          <span className="text-sm">Not priced</span>
        </div>

        {/* Check price button (hover) */}
        <button
          disabled={checking}
          className="
            w-full px-3 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium
            hover:bg-indigo-700 transition-all shadow-sm
            opacity-0 group-hover/cell:opacity-100
            disabled:opacity-50
          "
        >
          {checking ? (
            <Loader2 className="w-4 h-4 animate-spin mx-auto" />
          ) : (
            'Check Price'
          )}
        </button>
      </div>
    );
  }

  // Check if we have partial pricing (one registrar but not both)
  const hasDynadot = domain.dynadotPrice != null;
  const hasPorkbun = domain.porkbunPrice != null;
  const hasBothPrices = hasDynadot && hasPorkbun;
  const hasAnyPrice = hasDynadot || hasPorkbun;

  return (
    <div className="space-y-2 group/cell">
      {/* Price comparison - show Dynadot first (loads faster) */}
      <div className="space-y-1.5">
        {/* Dynadot - shows first */}
        {hasDynadot ? (
          <div className="flex items-center justify-between text-xs">
            <span className="text-gray-500 font-medium">Dynadot</span>
            <span className={`font-semibold flex items-center gap-1 ${
              domain.bestRegistrar === 'dynadot' && !isOverBudget
                ? 'text-green-600'
                : isOverBudget
                ? 'text-red-500'
                : 'text-gray-700'
            }`}>
              ${domain.dynadotPrice!.toFixed(2)}
              {hasBothPrices && domain.bestRegistrar === 'dynadot' && !isOverBudget && (
                <Check className="w-3.5 h-3.5" />
              )}
            </span>
          </div>
        ) : hasAnyPrice ? (
          <div className="flex items-center justify-between text-xs">
            <span className="text-gray-400 font-medium">Dynadot</span>
            <span className="text-gray-400 flex items-center gap-1">
              <Loader2 className="w-3 h-3 animate-spin" />
              <span>checking...</span>
            </span>
          </div>
        ) : null}

        {/* Porkbun - may load slower due to rate limits */}
        {hasPorkbun ? (
          <div className="flex items-center justify-between text-xs">
            <span className="text-gray-500 font-medium">Porkbun</span>
            <span className={`font-semibold flex items-center gap-1 ${
              domain.bestRegistrar === 'porkbun' && !isOverBudget
                ? 'text-green-600'
                : isOverBudget
                ? 'text-red-500'
                : 'text-gray-700'
            }`}>
              ${domain.porkbunPrice!.toFixed(2)}
              {hasBothPrices && domain.bestRegistrar === 'porkbun' && !isOverBudget && (
                <Check className="w-3.5 h-3.5" />
              )}
            </span>
          </div>
        ) : hasDynadot ? (
          <div className="flex items-center justify-between text-xs">
            <span className="text-gray-400 font-medium">Porkbun</span>
            <span className="text-gray-400 flex items-center gap-1">
              <Loader2 className="w-3 h-3 animate-spin" />
              <span>checking...</span>
            </span>
          </div>
        ) : null}
      </div>

      {/* Over Budget Warning */}
      {isOverBudget && (
        <div className="inline-flex items-center gap-1.5 px-2 py-1 bg-red-50 text-red-600 rounded-md text-xs font-medium border border-red-200">
          <AlertTriangle className="w-3 h-3" />
          Over ${PRICE_BUDGET_LIMIT}
        </div>
      )}

      {/* Buy Button - Only show when BOTH prices available (to determine best) */}
      {!isOverBudget && hasBothPrices && domain.bestPrice != null && (
        <button
          onClick={() => onBuy?.(domain.domainId)}
          className={`
            w-full px-3 py-2 rounded-lg text-sm font-medium transition-all shadow-sm
            flex items-center justify-center gap-1.5
            ${isSelected
              ? 'bg-indigo-600 text-white hover:bg-indigo-700'
              : 'bg-white text-gray-700 border border-gray-200 hover:bg-gray-50 hover:border-gray-300'
            }
          `}
        >
          <ShoppingCart className="w-3.5 h-3.5" />
          {isSelected ? 'Selected' : `Buy $${domain.bestPrice.toFixed(2)}`}
        </button>
      )}

      {/* Partial pricing indicator - waiting for other registrar */}
      {hasAnyPrice && !hasBothPrices && !isOverBudget && (
        <div className="text-[11px] text-amber-600 flex items-center gap-1">
          <Clock className="w-3 h-3" />
          Waiting for {!hasPorkbun ? 'Porkbun' : 'Dynadot'} price...
        </div>
      )}

      {/* Price check timestamp */}
      {domain.priceCheckedAt && hasBothPrices && (
        <div className="text-[11px] text-gray-400">
          Checked {(() => {
            try {
              return formatDistanceToNow(new Date(domain.priceCheckedAt), { addSuffix: true });
            } catch {
              return 'recently';
            }
          })()}
        </div>
      )}
    </div>
  );
}
