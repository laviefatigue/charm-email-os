'use client';

/**
 * Infrastructure Provisioning - Client-Based Route
 * Gets clientId from route params instead of dropdown selector
 */

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { useWaterfallStore } from '@/lib/stores/waterfallStore';
import { useClientStore } from '@/lib/stores';
import { TabNavigation } from '@/components/layout';
import { WaterfallTable } from '@/components/infrastructure/WaterfallTable';
import { InfraFilterBar } from '@/components/infrastructure/InfraFilterBar';
import { InfraSummaryHeader } from '@/components/infrastructure/InfraSummaryHeader';
import { BulkPurchaseModal } from '@/components/infrastructure/BulkPurchaseModal';
import { HyperTideOrderModal } from '@/components/infrastructure/HyperTideOrderModal';
import { api } from '@/lib/api';
import { Button } from '@/components/ui/button';
import {
  RefreshCw,
  Server,
  ShoppingCart,
  Waves,
  X,
  Loader2,
  Plus,
  DollarSign,
} from 'lucide-react';
import type { ProviderType } from '@/lib/types/infrastructure';

// View tabs configuration
type ViewFilter = 'all' | 'purchased' | 'pending';

export default function ClientInfrastructurePage() {
  const params = useParams();
  const clientId = params.clientId as string;

  const [activeView, setActiveView] = useState<ViewFilter>('all');

  // Modal state
  const [showPurchaseModal, setShowPurchaseModal] = useState(false);
  const [showHyperTideModal, setShowHyperTideModal] = useState(false);
  const [selectedProvider, setSelectedProvider] = useState<ProviderType>('entra');
  const [isGenerating, setIsGenerating] = useState(false);
  const [isCheckingPrices, setIsCheckingPrices] = useState(false);
  const [priceCheckResult, setPriceCheckResult] = useState<{ checked: number; available: number } | null>(null);

  // Client store
  const { getClient, fetchClients } = useClientStore();
  const client = getClient(clientId);

  const {
    domains,
    totalDomains,
    loading,
    error,
    selectedDomainIds,
    setSelectedClient,
    refreshWaterfall,
    clearSelection,
    selectDomainsForPurchase,
    getDomainsReadyForPurchase,
    getDomainsReadyForHyperTide,
  } = useWaterfallStore();

  // Load client and waterfall data on mount
  useEffect(() => {
    fetchClients();
  }, [fetchClients]);

  useEffect(() => {
    if (clientId) {
      setSelectedClient(clientId);
    }
  }, [clientId, setSelectedClient]);

  // Filter domains based on active view
  const filteredDomains = domains.filter((d) => {
    switch (activeView) {
      case 'purchased':
        return d.isPurchased;
      case 'pending':
        return !d.isPurchased;
      default:
        return true;
    }
  });

  // Computed counts
  const purchasedCount = domains.filter((d) => d.isPurchased).length;
  const pendingCount = domains.filter((d) => !d.isPurchased).length;
  const liveCount = domains.filter((d) => d.domainStatus === 'live').length;
  const readyForPurchase = getDomainsReadyForPurchase().length;
  const readyForEntra = getDomainsReadyForHyperTide('entra').length;
  const readyForGoogle = getDomainsReadyForHyperTide('google').length;
  const unpricedCount = domains.filter((d) => !d.isPurchased && d.bestPrice == null).length;

  // Get selected domains for contextual actions
  const selectedDomains = domains.filter((d) => selectedDomainIds.has(d.domainId));
  const selectedForPurchase = selectedDomains.filter(
    (d) => !d.isPurchased && !d.isOverBudget && d.bestPrice != null
  );
  const selectedForHyperTide = selectedDomains.filter(
    (d) => d.isPurchased && d.dnsStatus === 'ready' && d.totalInboxCount === 0
  );

  // Handlers
  const handleBuyDomain = (domainId: string) => {
    useWaterfallStore.getState().toggleDomainSelection(domainId);
  };

  const handleBulkPurchase = async (domainIds: string[]) => {
    if (!clientId) return;
    try {
      const result = await api.infrastructure.bulkPurchase(clientId, domainIds);
      console.log('Bulk purchase job created:', result);
      setTimeout(() => refreshWaterfall(), 1000);
    } catch (err) {
      console.error('Bulk purchase failed:', err);
      throw err;
    }
  };

  const handleHyperTideOrder = async (request: {
    domainIds: string[];
    provider: ProviderType;
    orderCount: number;
    senderNames: { firstName: string; lastName: string }[];
  }) => {
    const workspaceId = useWaterfallStore.getState().workspaceId;
    if (!clientId || !workspaceId) {
      throw new Error('Missing client or workspace');
    }
    try {
      // Note: senderNames are passed for future API support
      // Currently API reads sender names from client's onboarding_data
      const result = await api.infrastructure.createHyperTideOrder({
        clientId,
        workspaceId,
        provider: request.provider,
        domainIds: request.domainIds,
        orderCount: request.orderCount,
      });
      console.log('HyperTide order created:', result, 'with sender names:', request.senderNames);
      setTimeout(() => refreshWaterfall(), 1000);
    } catch (err) {
      console.error('HyperTide order failed:', err);
      throw err;
    }
  };

  const handleCreateEntraOrder = () => {
    setSelectedProvider('entra');
    setShowHyperTideModal(true);
  };

  const handleCreateGoogleOrder = () => {
    setSelectedProvider('google');
    setShowHyperTideModal(true);
  };

  const handleGenerateDomains = async () => {
    if (!clientId) return;
    setIsGenerating(true);
    try {
      await api.domainSourcing.generateForClient(clientId, {
        count: 10,
        fill_package: true,
      });
      setActiveView('pending');
      await refreshWaterfall();
    } catch (err) {
      console.error('Domain generation failed:', err);
    } finally {
      setIsGenerating(false);
    }
  };

  const handleCheckPrices = async () => {
    if (!client?.workspaceId) return;
    setIsCheckingPrices(true);
    setPriceCheckResult(null);

    const refreshInterval = setInterval(async () => {
      try {
        await refreshWaterfall();
      } catch (err) {
        console.error('Refresh failed:', err);
      }
    }, 3000);

    try {
      const result = await api.infrastructure.bulkPriceCheckWorkspace(client.workspaceId, 50);
      setPriceCheckResult({ checked: result.checked, available: result.available });
      await refreshWaterfall();
    } catch (err) {
      console.error('Price check failed:', err);
    } finally {
      clearInterval(refreshInterval);
      setIsCheckingPrices(false);
    }
  };

  return (
    <div className="flex flex-col h-screen bg-gray-50 overflow-hidden">
      {/* Sticky Header */}
      <div className="sticky top-0 z-50 bg-gray-50">
        <div className="max-w-[1800px] mx-auto px-4 pt-4">
          {/* Tab Navigation - shared with profile (includes Back to Clients) */}
          <TabNavigation clientId={clientId} />
        </div>
      </div>

      {/* Main Content - Scrollable */}
      <div className="flex-1 overflow-y-auto p-4 pt-0">
        <div className="max-w-[1800px] mx-auto space-y-4">
          {/* Infrastructure Summary */}
          <InfraSummaryHeader
            onCreateOrder={(provider) => {
              setSelectedProvider(provider);
              setShowHyperTideModal(true);
            }}
          />

          {/* Filter Bar */}
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-4">
            <InfraFilterBar />
          </div>

          {/* Selection Actions Bar - Floating */}
          {selectedDomainIds.size > 0 && (
            <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50">
              <div className="bg-white rounded-xl shadow-xl border border-gray-200 p-4 min-w-[600px]">
                <div className="flex items-center justify-between gap-6">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 bg-indigo-100 rounded-full flex items-center justify-center">
                      <span className="text-indigo-700 font-bold text-sm">
                        {selectedDomainIds.size}
                      </span>
                    </div>
                    <div>
                      <div className="text-sm font-semibold text-gray-900">
                        {selectedDomainIds.size} domain{selectedDomainIds.size !== 1 ? 's' : ''} selected
                      </div>
                      <button
                        onClick={clearSelection}
                        className="text-xs text-gray-500 hover:text-gray-700"
                      >
                        Clear selection
                      </button>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    {selectedForPurchase.length > 0 && (
                      <button
                        onClick={() => setShowPurchaseModal(true)}
                        className="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 transition-colors shadow-sm flex items-center gap-2"
                      >
                        <ShoppingCart className="w-4 h-4" />
                        Purchase ({selectedForPurchase.length})
                      </button>
                    )}
                    {selectedForHyperTide.length > 0 && (
                      <>
                        <button
                          onClick={handleCreateEntraOrder}
                          className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors shadow-sm flex items-center gap-2"
                        >
                          <Waves className="w-4 h-4" />
                          Entra Order
                        </button>
                        <button
                          onClick={handleCreateGoogleOrder}
                          className="px-4 py-2 bg-red-600 text-white rounded-lg text-sm font-medium hover:bg-red-700 transition-colors shadow-sm flex items-center gap-2"
                        >
                          <Waves className="w-4 h-4" />
                          Google Order
                        </button>
                      </>
                    )}
                    {selectedForPurchase.length === 0 && selectedForHyperTide.length === 0 && (
                      <span className="text-sm text-gray-500 px-3">
                        No actions available for selected domains
                      </span>
                    )}
                    <button
                      onClick={clearSelection}
                      className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
                    >
                      <X className="w-5 h-5 text-gray-500" />
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Quick Actions Bar with View Tabs */}
          {selectedDomainIds.size === 0 && (
            <div className="bg-linear-to-r from-indigo-50 to-purple-50 rounded-xl border border-indigo-100 p-4">
              <div className="flex items-center justify-between">
                {/* Left: View Tabs */}
                <div className="flex items-center gap-2">
                  <ViewTab
                    label="All"
                    count={totalDomains}
                    active={activeView === 'all'}
                    onClick={() => setActiveView('all')}
                  />
                  <ViewTab
                    label="Purchased"
                    count={purchasedCount}
                    active={activeView === 'purchased'}
                    onClick={() => setActiveView('purchased')}
                  />
                  <ViewTab
                    label="Pending"
                    count={pendingCount}
                    active={activeView === 'pending'}
                    onClick={() => setActiveView('pending')}
                  />
                </div>
                {/* Right: Action Buttons */}
                <div className="flex items-center gap-2">
                  <button
                    onClick={handleGenerateDomains}
                    disabled={isGenerating}
                    className="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 transition-colors shadow-sm flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {isGenerating ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin" />
                        <span>Generating & Pricing...</span>
                      </>
                    ) : (
                      <>
                        <Plus className="w-4 h-4" />
                        <span>Generate Domains</span>
                      </>
                    )}
                  </button>
                  <button
                    onClick={handleCheckPrices}
                    disabled={isCheckingPrices || !client?.workspaceId || unpricedCount === 0}
                    className="px-4 py-2 bg-emerald-600 text-white rounded-lg text-sm font-medium hover:bg-emerald-700 transition-colors shadow-sm flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {isCheckingPrices ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin" />
                        <span>Checking Prices...</span>
                      </>
                    ) : (
                      <>
                        <DollarSign className="w-4 h-4" />
                        <span>{unpricedCount > 0 ? `Check ${unpricedCount} Prices` : 'All Priced'}</span>
                      </>
                    )}
                  </button>
                  {priceCheckResult && (
                    <span className="text-sm text-emerald-600 font-medium">
                      ✓ {priceCheckResult.checked} checked, {priceCheckResult.available} available
                    </span>
                  )}
                  {readyForPurchase > 0 && (
                    <button
                      onClick={selectDomainsForPurchase}
                      className="px-4 py-2 bg-white text-indigo-700 rounded-lg text-sm font-medium hover:bg-indigo-50 transition-colors border border-indigo-200 flex items-center gap-2"
                    >
                      <ShoppingCart className="w-4 h-4" />
                      Select {readyForPurchase} for Purchase
                    </button>
                  )}
                  {readyForEntra >= 2 && (
                    <button
                      onClick={handleCreateEntraOrder}
                      className="px-4 py-2 bg-white text-blue-700 rounded-lg text-sm font-medium hover:bg-blue-50 transition-colors border border-blue-200 flex items-center gap-2"
                    >
                      <Waves className="w-4 h-4" />
                      {Math.floor(readyForEntra / 2)} Entra Order{Math.floor(readyForEntra / 2) !== 1 ? 's' : ''}
                    </button>
                  )}
                  {readyForGoogle >= 5 && (
                    <button
                      onClick={handleCreateGoogleOrder}
                      className="px-4 py-2 bg-white text-red-700 rounded-lg text-sm font-medium hover:bg-red-50 transition-colors border border-red-200 flex items-center gap-2"
                    >
                      <Waves className="w-4 h-4" />
                      {Math.floor(readyForGoogle / 5)} Google Order{Math.floor(readyForGoogle / 5) !== 1 ? 's' : ''}
                    </button>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Main Table Card */}
          {loading && domains.length === 0 ? (
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-16 text-center">
              <div className="w-16 h-16 bg-indigo-100 rounded-full flex items-center justify-center mx-auto mb-4">
                <Loader2 className="w-8 h-8 text-indigo-600 animate-spin" />
              </div>
              <p className="text-gray-600 font-medium">Loading infrastructure data...</p>
              <p className="text-sm text-gray-400 mt-1">This may take a moment</p>
            </div>
          ) : error ? (
            <div className="bg-red-50 border border-red-200 rounded-xl p-8 text-center">
              <p className="text-red-700 font-semibold mb-2">Error loading data</p>
              <p className="text-red-600 text-sm mb-4">{error}</p>
              <Button
                onClick={refreshWaterfall}
                className="bg-red-600 hover:bg-red-700"
              >
                Try Again
              </Button>
            </div>
          ) : filteredDomains.length === 0 ? (
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-16 text-center">
              <div className="max-w-md mx-auto">
                <div className="w-16 h-16 bg-gray-100 rounded-full flex items-center justify-center mx-auto mb-4">
                  <Server className="w-8 h-8 text-gray-400" />
                </div>
                <h3 className="text-lg font-semibold text-gray-900 mb-2">No Domains Found</h3>
                <p className="text-gray-500">
                  {activeView === 'all'
                    ? 'This client has no domains. Generate new domains to get started.'
                    : `No ${activeView} domains found. Try switching to a different view.`}
                </p>
              </div>
            </div>
          ) : (
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
              {/* Table Header */}
              <div className="px-6 py-4 border-b border-gray-200 bg-linear-to-r from-gray-50 to-white">
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-lg font-semibold text-gray-900">
                      {client?.name} Domains
                    </h2>
                    <div className="flex items-center gap-3 text-sm text-gray-500 mt-1">
                      <span className="flex items-center gap-1">
                        <div className="w-2 h-2 rounded-full bg-gray-400" />
                        {totalDomains} total
                      </span>
                      <span className="flex items-center gap-1">
                        <div className="w-2 h-2 rounded-full bg-emerald-500" />
                        {purchasedCount} purchased
                      </span>
                      <span className="flex items-center gap-1">
                        <div className="w-2 h-2 rounded-full bg-green-500" />
                        {liveCount} live
                      </span>
                    </div>
                  </div>
                  <button
                    onClick={() => refreshWaterfall()}
                    disabled={loading}
                    className="px-3 py-1.5 text-sm font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors flex items-center gap-2 disabled:opacity-50"
                  >
                    <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                    Refresh
                  </button>
                </div>
              </div>

              {/* Waterfall Table */}
              <div className="overflow-auto max-h-[calc(100vh-380px)]">
                <WaterfallTable
                  domains={filteredDomains}
                  onBuyDomain={handleBuyDomain}
                />
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Modals */}
      <BulkPurchaseModal
        open={showPurchaseModal}
        onOpenChange={setShowPurchaseModal}
        onConfirm={handleBulkPurchase}
      />

      <HyperTideOrderModal
        open={showHyperTideModal}
        onOpenChange={setShowHyperTideModal}
        provider={selectedProvider}
        clientId={clientId}
        onConfirm={handleHyperTideOrder}
      />
    </div>
  );
}

// View Tab Component
function ViewTab({
  label,
  count,
  active,
  onClick,
}: {
  label: string;
  count: number;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`
        px-4 py-2 rounded-lg text-sm font-medium transition-all
        ${active
          ? 'bg-indigo-50 text-indigo-700 shadow-sm'
          : 'text-gray-600 hover:bg-gray-100'
        }
      `}
    >
      {label}
      <span
        className={`ml-2 px-2 py-0.5 rounded-full text-xs ${
          active ? 'bg-indigo-100 text-indigo-700' : 'bg-gray-100 text-gray-600'
        }`}
      >
        {count}
      </span>
    </button>
  );
}
