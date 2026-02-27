'use client';

/**
 * Infrastructure Summary Header - Clay.com Style v2
 * Shows current infrastructure totals for Entra vs Google
 *
 * Metrics:
 * - Domains: Live domains / Target (packages × domains/order)
 * - Inboxes: Live / Dead with disconnected warning
 * - Capacity: Sending volume based on emails/day/inbox
 * - Packages: Used packages (live domains ÷ domains/order)
 */

import { useWaterfallStore } from '@/lib/stores/waterfallStore';
import {
  Server,
  AlertTriangle,
  XCircle,
  Zap,
  Plus,
} from 'lucide-react';
import type { ProviderSummary, ProviderType } from '@/lib/types/infrastructure';

// Provider configuration with sending rates (must match API calculations)
const PROVIDER_METRICS = {
  entra: {
    domainsPerOrder: 2,
    inboxesPerDomain: 50,
    emailsPerDayPerInbox: 2, // Matches API: entra_connected * 2
    label: 'Microsoft Entra',
  },
  google: {
    domainsPerOrder: 5,
    inboxesPerDomain: 3,
    emailsPerDayPerInbox: 20, // Matches API: google_connected * 20
    label: 'Google Workspace',
  },
} as const;

interface ProviderCardProps {
  provider: ProviderType;
  summary: ProviderSummary;
  packageName?: string | null;
  onCreateOrder: (provider: ProviderType) => void;
}

function ProviderCard({ provider, summary, packageName, onCreateOrder }: ProviderCardProps) {
  const config = PROVIDER_METRICS[provider];
  const isEntra = provider === 'entra';

  // Calculate metrics
  const liveDomains = summary.domainsHealthy + summary.domainsFlagged;
  const deadDomains = summary.domainsDead;

  // For package calculations, use live domains only (dead don't count toward capacity)
  const orderCount = Math.ceil(liveDomains / config.domainsPerOrder);
  // Expected based on packages purchased
  const expectedFromPackages = summary.packageCount * config.domainsPerOrder;

  const liveInboxes = summary.inboxesLive;
  const deadInboxes = summary.inboxesDead;
  const connectedInboxes = summary.inboxesConnected ?? 0;
  const disconnectedInboxes = summary.inboxesDisconnected ?? 0;
  const totalInboxes = summary.inboxesTotal;

  // Packages: Orders used vs packages purchased
  const usedPackages = orderCount;
  const availablePackages = summary.packageCount;

  // Daily sending capacity based on CONNECTED inboxes only (not just live)
  const actualDailyCapacity = summary.dailyCapacity; // API calculates based on connected

  // Health calculation: % of live inboxes that are connected (operational)
  const operationalPct = liveInboxes > 0
    ? Math.round((connectedInboxes / liveInboxes) * 100)
    : 0;

  return (
    <div
      className={`flex-1 rounded-xl border p-5 transition-all hover:shadow-md ${
        isEntra
          ? 'border-blue-200 bg-gradient-to-br from-blue-50 to-indigo-50/50'
          : 'border-red-200 bg-gradient-to-br from-red-50 to-orange-50/50'
      }`}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${
            isEntra ? 'bg-blue-100' : 'bg-red-100'
          }`}>
            <Server className={`w-5 h-5 ${isEntra ? 'text-blue-600' : 'text-red-600'}`} />
          </div>
          <div>
            <div className={`text-sm font-semibold ${isEntra ? 'text-blue-900' : 'text-red-900'}`}>
              {config.label}
            </div>
            <div className="text-xs text-gray-500">
              {config.domainsPerOrder} domains/order • {config.inboxesPerDomain} inboxes/domain
            </div>
          </div>
        </div>
        <button
          onClick={() => onCreateOrder(provider)}
          className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors flex items-center gap-1.5 ${
            isEntra
              ? 'bg-blue-100 text-blue-700 hover:bg-blue-200 border border-blue-200'
              : 'bg-red-100 text-red-700 hover:bg-red-200 border border-red-200'
          }`}
        >
          <Plus className="w-4 h-4" />
          Create Order
        </button>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-4 gap-4">
        {/* 1. DOMAINS: Live / Expected from packages */}
        <div className="bg-white/60 rounded-lg p-3 border border-gray-100">
          <div className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider mb-1">
            Domains
          </div>
          <div className="flex items-baseline gap-1">
            <span className={`text-2xl font-bold ${liveDomains === 0 && deadDomains > 0 ? 'text-red-600' : 'text-gray-900'}`}>
              {liveDomains}
            </span>
            {expectedFromPackages > 0 && (
              <span className="text-sm text-gray-400">/{expectedFromPackages}</span>
            )}
          </div>
          <div className="flex items-center gap-2 mt-1.5 text-xs">
            {summary.domainsFlagged > 0 && (
              <span className="flex items-center gap-1 text-amber-600">
                <AlertTriangle className="w-3 h-3" />
                {summary.domainsFlagged} at risk
              </span>
            )}
            {summary.domainsDead > 0 && (
              <span className="flex items-center gap-1 text-red-600">
                <XCircle className="w-3 h-3" />
                {summary.domainsDead} dead
              </span>
            )}
            {summary.domainsFlagged === 0 && summary.domainsDead === 0 && liveDomains > 0 && (
              <span className="text-green-600">All healthy</span>
            )}
            {liveDomains === 0 && deadDomains === 0 && (
              <span className="text-gray-400">No domains yet</span>
            )}
          </div>
        </div>

        {/* 2. INBOXES: Connected / Live (operational capacity) */}
        <div className="bg-white/60 rounded-lg p-3 border border-gray-100">
          <div className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider mb-1">
            Inboxes
          </div>
          <div className="flex items-baseline gap-1">
            <span className={`text-2xl font-bold ${connectedInboxes === 0 && liveInboxes > 0 ? 'text-red-600' : 'text-gray-900'}`}>
              {connectedInboxes.toLocaleString()}
            </span>
            <span className="text-sm text-gray-400">/{liveInboxes.toLocaleString()}</span>
          </div>
        </div>

        {/* 3. DAILY CAPACITY: Based on emails/day/inbox */}
        <div className="bg-white/60 rounded-lg p-3 border border-gray-100">
          <div className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider mb-1">
            Daily Capacity
          </div>
          <div className="flex items-baseline gap-1">
            <span className="text-2xl font-bold text-gray-900">
              {actualDailyCapacity.toLocaleString()}
            </span>
            <span className="text-xs text-gray-400">/day</span>
          </div>
          <div className="flex items-center gap-1 mt-1.5 text-xs text-gray-500">
            <Zap className="w-3 h-3" />
            ~{Math.round(actualDailyCapacity * 30).toLocaleString()}/mo
          </div>
        </div>

        {/* 4. PACKAGES: Package name and count */}
        <div className="bg-white/60 rounded-lg p-3 border border-gray-100">
          <div className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider mb-1">
            Packages
          </div>
          <div className="flex items-baseline gap-1">
            <span className="text-2xl font-bold text-gray-900">
              {usedPackages}
            </span>
            <span className="text-sm text-gray-400">/{availablePackages}</span>
          </div>
          <div className="text-xs mt-1.5">
            {packageName ? (
              <span className="text-gray-600 font-medium">
                {packageName}
              </span>
            ) : (
              <span className="text-gray-400">
                {availablePackages - usedPackages} available
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Health Bar - shows operational capacity (connected/live) */}
      {liveInboxes > 0 && (
        <div className="mt-4 pt-4 border-t border-gray-200/50">
          <div className="flex items-center justify-between text-xs mb-2">
            <span className="text-gray-500 font-medium">Operational Capacity</span>
            <span
              className={`font-semibold ${
                operationalPct >= 80
                  ? 'text-green-600'
                  : operationalPct >= 50
                  ? 'text-amber-600'
                  : 'text-red-600'
              }`}
            >
              {operationalPct}% operational
            </span>
          </div>
          <div className="h-2 bg-gray-200 rounded-full overflow-hidden flex">
            <div
              className="bg-green-500 transition-all duration-300"
              style={{ width: `${operationalPct}%` }}
            />
            <div
              className="bg-amber-500 transition-all duration-300"
              style={{ width: `${liveInboxes > 0 ? ((disconnectedInboxes / liveInboxes) * 100) : 0}%` }}
            />
          </div>
        </div>
      )}
    </div>
  );
}

interface InfraSummaryHeaderProps {
  onCreateOrder: (provider: ProviderType) => void;
}

export function InfraSummaryHeader({ onCreateOrder }: InfraSummaryHeaderProps) {
  const { infraSummary } = useWaterfallStore();

  if (!infraSummary) {
    return null;
  }

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-4">
      {/* Title */}
      <div className="flex items-center gap-3 mb-5">
        <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center shadow-sm">
          <Server className="w-5 h-5 text-white" />
        </div>
        <div>
          <h2 className="text-lg font-semibold text-gray-900">
            Current Infrastructure
          </h2>
          <p className="text-sm text-gray-500">
            {infraSummary.clientName} • {infraSummary.totalDomains} domains •{' '}
            {infraSummary.totalLiveInboxes.toLocaleString()} live inboxes
          </p>
        </div>
      </div>

      {/* Provider Cards */}
      <div className="flex gap-4">
        <ProviderCard
          provider="entra"
          summary={infraSummary.entra}
          packageName={infraSummary.packageName}
          onCreateOrder={onCreateOrder}
        />
        <ProviderCard
          provider="google"
          summary={infraSummary.google}
          packageName={infraSummary.packageName}
          onCreateOrder={onCreateOrder}
        />
      </div>
    </div>
  );
}
