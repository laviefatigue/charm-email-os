'use client';

/**
 * Waterfall Table - Clay.com Style
 * 6-Column Infrastructure Provisioning with smooth interactions
 * Updated: Lifecycle priority sorting (Live > Staged > Pending)
 */

import { useMemo } from 'react';
import { useWaterfallStore } from '@/lib/stores/waterfallStore';
import { WATERFALL_COLUMNS } from '@/lib/types/infrastructure';
import { Checkbox } from '@/components/ui/checkbox';
import { DomainCell } from './cells/DomainCell';
import { PricingCell } from './cells/PricingCell';
import { DNSCell } from './cells/DNSCell';
import { ProviderCell } from './cells/ProviderCell';
import { HyperTideCell } from './cells/HyperTideCell';
import { StatusCell } from './cells/StatusCell';
import type { WaterfallDomain } from '@/lib/types/infrastructure';

interface TableRowProps {
  domain: WaterfallDomain;
  isSelected: boolean;
  onToggle: () => void;
  onBuyDomain?: (domainId: string) => void;
}

function TableRow({
  domain,
  isSelected,
  onToggle,
  onBuyDomain,
}: TableRowProps) {
  // Determine row styling based on status
  const getRowClasses = () => {
    const base = 'group border-b border-gray-100 transition-all duration-150';

    if (domain.isDeactivated) {
      return `${base} bg-red-50/40 opacity-60 hover:opacity-80`;
    }
    if (isSelected) {
      return `${base} bg-indigo-50 hover:bg-indigo-100/80`;
    }
    if (domain.isOverBudget) {
      return `${base} bg-amber-50/40 hover:bg-amber-50/60`;
    }
    return `${base} hover:bg-gray-50`;
  };

  return (
    <tr className={getRowClasses()}>
      {/* Checkbox */}
      <td className="px-2 py-3 sticky left-0 bg-inherit z-10 border-r border-gray-100 w-10 min-w-10 max-w-10">
        <Checkbox
          checked={isSelected}
          onCheckedChange={onToggle}
          aria-label={`Select ${domain.domainName}`}
          className="rounded border-gray-300 data-[state=checked]:bg-indigo-600 data-[state=checked]:border-indigo-600"
        />
      </td>

      {/* Domain */}
      <td className="px-3 py-3 border-r border-gray-100">
        <DomainCell domain={domain} />
      </td>

      {/* Pricing */}
      <td className="px-3 py-3 border-r border-gray-100">
        <PricingCell
          domain={domain}
          onBuy={onBuyDomain}
          isSelected={isSelected && !domain.isPurchased}
        />
      </td>

      {/* DNS */}
      <td className="px-3 py-3 border-r border-gray-100">
        <DNSCell domain={domain} />
      </td>

      {/* HyperTide */}
      <td className="px-3 py-3 border-r border-gray-100">
        <HyperTideCell domain={domain} />
      </td>

      {/* Provider */}
      <td className="px-3 py-3 border-r border-gray-100">
        <ProviderCell domain={domain} />
      </td>

      {/* Status */}
      <td className="px-3 py-3">
        <StatusCell domain={domain} />
      </td>
    </tr>
  );
}

interface WaterfallTableProps {
  domains?: WaterfallDomain[];
  onBuyDomain?: (domainId: string) => void;
}

export function WaterfallTable({
  domains: propDomains,
  onBuyDomain,
}: WaterfallTableProps) {
  const {
    domains: storeDomains,
    selectedDomainIds,
    toggleDomainSelection,
    selectAllVisible,
    clearSelection,
    sortBy,
    sortDirection,
    setSort,
    filters,
  } = useWaterfallStore();

  // Use prop domains if provided, otherwise use store domains
  const domains = propDomains ?? storeDomains;

  const allSelected = domains.length > 0 && selectedDomainIds.size === domains.length;
  const someSelected = selectedDomainIds.size > 0 && selectedDomainIds.size < domains.length;

  // Sort domains by lifecycle priority using useMemo to ensure proper reactivity
  const sortedDomains = useMemo(() => {
    // When rotation filter is "needs_attention", preserve API sort order (rotation priority baked in)
    // The API already sorts: monitor first, then consider_rotate, then rotate_now
    if (filters.rotationStatus === 'needs_attention') {
      return domains; // Preserve API order
    }

    // Helper to get lifecycle priority (lower = higher priority, shown first)
    const getLifecyclePriority = (domain: WaterfallDomain): number => {
      // Over budget always at bottom
      if (domain.isOverBudget) return 99;
      // Deactivated/dead at bottom
      if (domain.isDeactivated) return 98;

      // Live with inboxes - show first (working infrastructure)
      if (domain.isPurchased && domain.liveInboxCount > 0) {
        // At risk domains slightly lower priority than fully healthy
        if (domain.domainStatus === 'flagged' || domain.domainStatus === 'monitoring') return 2;
        return 1; // Healthy live
      }

      // Purchased, ready for HyperTide (DNS ready, no inboxes yet)
      if (domain.isPurchased && domain.dnsStatus === 'ready' && domain.totalInboxCount === 0) {
        return 3;
      }

      // Purchased, pending DNS
      if (domain.isPurchased && domain.dnsStatus !== 'ready') {
        return 4;
      }

      // Ready to buy - has BOTH registrar prices (bestPrice only set when both available)
      if (!domain.isPurchased && domain.bestPrice != null) {
        return 5;
      }

      // Partial pricing - has ONE registrar price, waiting for the other
      const hasDynadot = domain.dynadotPrice != null;
      const hasPorkbun = domain.porkbunPrice != null;
      if (!domain.isPurchased && (hasDynadot || hasPorkbun)) {
        return 6;
      }

      // Not priced yet (domain ideas)
      return 7;
    };

    const direction = sortDirection === 'asc' ? 1 : -1;

    return [...domains].sort((a, b) => {
      // First sort by lifecycle priority
      const priorityA = getLifecyclePriority(a);
      const priorityB = getLifecyclePriority(b);
      if (priorityA !== priorityB) {
        return priorityA - priorityB;
      }

      // Within same priority, sort by selected column
      switch (sortBy) {
        case 'domain':
          return direction * a.domainName.localeCompare(b.domainName);
        case 'price': {
          const priceA = a.bestPrice ?? Infinity;
          const priceB = b.bestPrice ?? Infinity;
          return direction * (priceA - priceB);
        }
        case 'purchasedAt': {
          const dateA = a.purchasedAt ? new Date(a.purchasedAt).getTime() : 0;
          const dateB = b.purchasedAt ? new Date(b.purchasedAt).getTime() : 0;
          return direction * (dateA - dateB);
        }
        case 'tld':
          return direction * a.tld.localeCompare(b.tld);
        default:
          return direction * a.domainName.localeCompare(b.domainName);
      }
    });
  }, [domains, sortBy, sortDirection, filters.rotationStatus]);

  const finalDomains = sortedDomains;

  if (domains.length === 0) {
    return (
      <div className="flex items-center justify-center py-16">
        <div className="text-center">
          <div className="w-12 h-12 bg-gray-100 rounded-full flex items-center justify-center mx-auto mb-3">
            <svg className="w-6 h-6 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
            </svg>
          </div>
          <p className="text-gray-600 font-medium">No domains to display</p>
          <p className="text-sm text-gray-400 mt-1">
            Adjust your filters to see more domains
          </p>
        </div>
      </div>
    );
  }

  return (
    <table className="w-full" style={{ tableLayout: 'fixed' }}>
      {/* Define column widths - checkbox fixed, others equal */}
      <colgroup>
        <col style={{ width: '40px' }} />
        <col />
        <col />
        <col />
        <col />
        <col />
        <col />
      </colgroup>
      <thead className="sticky top-0 z-20">
        <tr className="bg-gray-50 border-b border-gray-200">
          {/* Checkbox Header */}
          <th className="px-2 py-3 sticky left-0 bg-gray-50 z-30 border-r border-gray-200 w-10 min-w-10 max-w-10">
            <Checkbox
              checked={allSelected}
              onCheckedChange={(checked) => {
                if (checked) {
                  selectAllVisible();
                } else {
                  clearSelection();
                }
              }}
              aria-label="Select all domains"
              className={`rounded border-gray-300 ${someSelected ? 'data-[state=checked]:bg-indigo-400' : 'data-[state=checked]:bg-indigo-600'}`}
            />
          </th>

          {/* Column Headers */}
          {WATERFALL_COLUMNS.map((column, index) => {
            const isSortable = column.id === 'domain' || column.id === 'pricing';
            const isActive = (sortBy === 'domain' && column.id === 'domain') ||
                             (sortBy === 'price' && column.id === 'pricing');
            const isLast = index === WATERFALL_COLUMNS.length - 1;

            return (
              <th
                key={column.id}
                className={`
                  px-3 py-3 text-left
                  ${!isLast ? 'border-r border-gray-200' : ''}
                  ${isSortable ? 'cursor-pointer select-none hover:bg-gray-100 transition-colors' : ''}
                `}
                onClick={() => {
                  if (isSortable) {
                    setSort(column.id === 'pricing' ? 'price' : 'domain');
                  }
                }}
              >
                <div className="flex items-center gap-2">
                  <span className="text-xs font-semibold text-gray-700 uppercase tracking-wider">
                    {column.label}
                  </span>
                  {isActive && (
                    <span className="text-indigo-600 text-sm">
                      {sortDirection === 'asc' ? '↑' : '↓'}
                    </span>
                  )}
                </div>
                <div className="text-[11px] font-normal text-gray-400 mt-0.5 leading-tight truncate">
                  {column.description}
                </div>
              </th>
            );
          })}
        </tr>
      </thead>
      <tbody>
        {finalDomains.map((domain) => (
          <TableRow
            key={domain.domainId}
            domain={domain}
            isSelected={selectedDomainIds.has(domain.domainId)}
            onToggle={() => toggleDomainSelection(domain.domainId)}
            onBuyDomain={onBuyDomain}
          />
        ))}
      </tbody>
    </table>
  );
}
