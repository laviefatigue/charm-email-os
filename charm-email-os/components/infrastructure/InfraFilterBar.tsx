'use client';

/**
 * Infrastructure Filter Bar - Clay.com Style
 * Hierarchical filtering with smooth interactions
 */

import { useWaterfallStore } from '@/lib/stores/waterfallStore';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { RefreshCw, X, RotateCcw } from 'lucide-react';
import { ALLOWED_TLDS, TLD_DISPLAY, PRICE_BUDGET_LIMIT } from '@/lib/types/infrastructure';
import type { TLD, ProviderType, DomainStatus } from '@/lib/types/infrastructure';

export function InfraFilterBar() {
  const {
    filters,
    filterCounts,
    loading,
    setFilter,
    resetFilters,
    toggleShowOverBudget,
    refreshWaterfall,
  } = useWaterfallStore();

  const hasActiveFilters =
    filters.purchaseStatus !== 'all' ||
    filters.tld !== 'all' ||
    filters.provider !== 'all' ||
    filters.status !== 'all' ||
    filters.showOverBudget;

  return (
    <div className="space-y-4">
      {/* Main Filter Row */}
      <div className="flex items-end gap-4 flex-wrap">
        {/* Purchase Status */}
        <div className="min-w-[160px]">
          <label className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2 block">
            Purchase Status
          </label>
          <Select
            value={filters.purchaseStatus}
            onValueChange={(v) => setFilter('purchaseStatus', v as 'all' | 'purchased' | 'not_purchased')}
          >
            <SelectTrigger className="bg-gray-50 border-gray-200 rounded-lg focus:ring-2 focus:ring-indigo-500">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">
                <span className="flex items-center justify-between w-full">
                  All Domains
                  {filterCounts && (
                    <span className="ml-2 text-gray-400 text-xs">
                      {filterCounts.purchased + filterCounts.notPurchased}
                    </span>
                  )}
                </span>
              </SelectItem>
              <SelectItem value="purchased">
                <span className="flex items-center justify-between w-full">
                  Purchased
                  {filterCounts && (
                    <span className="ml-2 text-gray-400 text-xs">{filterCounts.purchased}</span>
                  )}
                </span>
              </SelectItem>
              <SelectItem value="not_purchased">
                <span className="flex items-center justify-between w-full">
                  Not Purchased
                  {filterCounts && (
                    <span className="ml-2 text-gray-400 text-xs">{filterCounts.notPurchased}</span>
                  )}
                </span>
              </SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* TLD Filter */}
        <div className="min-w-[120px]">
          <label className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2 block">
            TLD
          </label>
          <Select
            value={filters.tld}
            onValueChange={(v) => setFilter('tld', v as TLD | 'all')}
          >
            <SelectTrigger className="bg-gray-50 border-gray-200 rounded-lg focus:ring-2 focus:ring-indigo-500">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All TLDs</SelectItem>
              {ALLOWED_TLDS.map((tld) => (
                <SelectItem key={tld} value={tld}>
                  <span className="flex items-center gap-2">
                    <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${TLD_DISPLAY[tld].color}`}>
                      {TLD_DISPLAY[tld].label}
                    </span>
                    {filterCounts && (
                      <span className="text-gray-400 text-xs">{filterCounts.byTld[tld]}</span>
                    )}
                  </span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Provider Filter */}
        <div className="min-w-[130px]">
          <label className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2 block">
            Provider
          </label>
          <Select
            value={filters.provider}
            onValueChange={(v) => setFilter('provider', v as ProviderType | 'all')}
          >
            <SelectTrigger className="bg-gray-50 border-gray-200 rounded-lg focus:ring-2 focus:ring-indigo-500">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Providers</SelectItem>
              <SelectItem value="entra">
                <span className="flex items-center gap-2">
                  <span className="px-1.5 py-0.5 bg-blue-100 text-blue-700 rounded text-[10px] font-semibold">
                    Entra
                  </span>
                  {filterCounts && (
                    <span className="text-gray-400 text-xs">{filterCounts.byProvider.entra}</span>
                  )}
                </span>
              </SelectItem>
              <SelectItem value="google">
                <span className="flex items-center gap-2">
                  <span className="px-1.5 py-0.5 bg-red-100 text-red-700 rounded text-[10px] font-semibold">
                    Google
                  </span>
                  {filterCounts && (
                    <span className="text-gray-400 text-xs">{filterCounts.byProvider.google}</span>
                  )}
                </span>
              </SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* Status Filter */}
        <div className="min-w-[130px]">
          <label className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2 block">
            Status
          </label>
          <Select
            value={filters.status}
            onValueChange={(v) => setFilter('status', v as DomainStatus | 'all')}
          >
            <SelectTrigger className="bg-gray-50 border-gray-200 rounded-lg focus:ring-2 focus:ring-indigo-500">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Status</SelectItem>
              <SelectItem value="live">
                <span className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-green-500" />
                  Live
                  {filterCounts && (
                    <span className="text-gray-400 text-xs">{filterCounts.byStatus.live}</span>
                  )}
                </span>
              </SelectItem>
              <SelectItem value="flagged">
                <span className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-amber-500" />
                  Flagged
                  {filterCounts && (
                    <span className="text-gray-400 text-xs">{filterCounts.byStatus.flagged}</span>
                  )}
                </span>
              </SelectItem>
              <SelectItem value="dead">
                <span className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-red-500" />
                  Dead
                  {filterCounts && (
                    <span className="text-gray-400 text-xs">{filterCounts.byStatus.dead}</span>
                  )}
                </span>
              </SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* Toggles */}
        <div className="flex items-center gap-6 border-l border-gray-200 pl-4">
          {/* Show Over Budget Toggle */}
          <div className="flex items-center gap-2">
            <Switch
              id="show-over-budget"
              checked={filters.showOverBudget}
              onCheckedChange={toggleShowOverBudget}
              className="data-[state=checked]:bg-indigo-600"
            />
            <Label htmlFor="show-over-budget" className="text-sm text-gray-600 cursor-pointer">
              &gt;${PRICE_BUDGET_LIMIT}
              {filterCounts && filterCounts.overBudget > 0 && (
                <span className="ml-1 text-gray-400 text-xs">({filterCounts.overBudget})</span>
              )}
            </Label>
          </div>

        </div>

        {/* Actions */}
        <div className="flex items-center gap-2 ml-auto">
          {hasActiveFilters && (
            <button
              onClick={resetFilters}
              className="px-3 py-2 text-sm font-medium text-gray-600 hover:bg-gray-100 rounded-lg transition-colors flex items-center gap-1.5"
            >
              <RotateCcw className="w-4 h-4" />
              Reset
            </button>
          )}
          <button
            onClick={refreshWaterfall}
            disabled={loading}
            className="px-3 py-2 text-sm font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors flex items-center gap-1.5 disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Active Filters Pills */}
      {hasActiveFilters && (
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs text-gray-500 font-medium">Active:</span>

          {filters.purchaseStatus !== 'all' && (
            <FilterPill
              label={filters.purchaseStatus === 'purchased' ? 'Purchased' : 'Not Purchased'}
              onRemove={() => setFilter('purchaseStatus', 'all')}
            />
          )}

          {filters.tld !== 'all' && (
            <FilterPill
              label={TLD_DISPLAY[filters.tld].label}
              className={TLD_DISPLAY[filters.tld].color}
              onRemove={() => setFilter('tld', 'all')}
            />
          )}

          {filters.provider !== 'all' && (
            <FilterPill
              label={filters.provider === 'entra' ? 'Entra' : 'Google'}
              className={filters.provider === 'entra' ? 'bg-blue-100 text-blue-700' : 'bg-red-100 text-red-700'}
              onRemove={() => setFilter('provider', 'all')}
            />
          )}

          {filters.status !== 'all' && (
            <FilterPill
              label={filters.status.charAt(0).toUpperCase() + filters.status.slice(1)}
              dot={
                filters.status === 'live'
                  ? 'bg-green-500'
                  : filters.status === 'flagged'
                  ? 'bg-amber-500'
                  : 'bg-red-500'
              }
              onRemove={() => setFilter('status', 'all')}
            />
          )}

          {filters.showOverBudget && (
            <FilterPill
              label={`>${PRICE_BUDGET_LIMIT}`}
              className="bg-amber-50 text-amber-700"
              onRemove={toggleShowOverBudget}
            />
          )}
        </div>
      )}
    </div>
  );
}

// Filter pill component
function FilterPill({
  label,
  className = '',
  dot,
  onRemove,
}: {
  label: string;
  className?: string;
  dot?: string;
  onRemove: () => void;
}) {
  return (
    <span
      className={`
        inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-xs font-medium
        bg-gray-100 text-gray-700 ${className}
      `}
    >
      {dot && <span className={`w-2 h-2 rounded-full ${dot}`} />}
      {label}
      <button
        onClick={onRemove}
        className="ml-0.5 hover:bg-black/10 rounded p-0.5 transition-colors"
      >
        <X className="w-3 h-3" />
      </button>
    </span>
  );
}
