'use client';

/**
 * Infrastructure Provisioning - Clay.com Waterfall Style
 * Smooth, polished design with indigo/purple accents
 */

import { useEffect, useState } from 'react';
import { useWaterfallStore } from '@/lib/stores/waterfallStore';
import { WaterfallTable } from '@/components/infrastructure/WaterfallTable';
import { InfraFilterBar } from '@/components/infrastructure/InfraFilterBar';
import { InfraSummaryHeader } from '@/components/infrastructure/InfraSummaryHeader';
import { BulkPurchaseModal } from '@/components/infrastructure/BulkPurchaseModal';
import { HyperTideOrderModal } from '@/components/infrastructure/HyperTideOrderModal';
import { api } from '@/lib/api';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
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
import type { Client } from '@/lib/types';
import type { ProviderType } from '@/lib/types/infrastructure';

// View tabs configuration
type ViewFilter = 'all' | 'purchased' | 'pending';

export default function InfrastructurePage() {
  const [clients, setClients] = useState<Client[]>([]);
  const [loadingClients, setLoadingClients] = useState(true);
  const [activeView, setActiveView] = useState<ViewFilter>('all');

  // Modal state
  const [showPurchaseModal, setShowPurchaseModal] = useState(false);
  const [showHyperTideModal, setShowHyperTideModal] = useState(false);
  const [selectedProvider, setSelectedProvider] = useState<ProviderType>('entra');
  const [isGenerating, setIsGenerating] = useState(false);
  const [isCheckingPrices, setIsCheckingPrices] = useState(false);
  const [priceCheckResult, setPriceCheckResult] = useState<{ checked: number; available: number } | null>(null);

  const {
    selectedClientId,
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

  // Load clients on mount
  useEffect(() => {
    const loadClients = async () => {
      try {
        const data = await api.clients.list({ pageSize: 100 });
        setClients(data.items);
      } catch (err) {
        console.error('Failed to load clients:', err);
      } finally {
        setLoadingClients(false);
      }
    };

    loadClients();
  }, []);

  const selectedClient = clients.find((c) => c.id === selectedClientId);

  // Filter domains based on active view (sorting handled by WaterfallTable)
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

  // Selected domains eligible for purchase (not purchased, not over budget, has price)
  const selectedForPurchase = selectedDomains.filter(
    (d) => !d.isPurchased && !d.isOverBudget && d.bestPrice != null
  );

  // Selected domains eligible for HyperTide order (purchased, DNS ready, NOT already live)
  const selectedForHyperTide = selectedDomains.filter(
    (d) => d.isPurchased && d.dnsStatus === 'ready' && d.totalInboxCount === 0
  );

  // Handlers
  const handleBuyDomain = (domainId: string) => {
    useWaterfallStore.getState().toggleDomainSelection(domainId);
  };

  const handleVerifyDNS = async (domainId: string) => {
    console.log('Verify DNS for:', domainId);
  };

  const handleFixDNS = async (domainId: string) => {
    console.log('Fix DNS for:', domainId);
  };

  const handleBulkPurchase = async (domainIds: string[]) => {
    if (!selectedClientId) return;
    try {
      const result = await api.infrastructure.bulkPurchase(domainIds);
      console.log('Bulk purchase job created:', result);
      // Refresh after short delay to allow job to start
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
    if (!selectedClientId || !workspaceId) {
      throw new Error('Missing client or workspace');
    }
    try {
      // Note: senderNames are passed for future API support
      // Currently API reads sender names from client's onboarding_data
      const result = await api.infrastructure.createHyperTideOrder({
        clientId: selectedClientId,
        workspaceId,
        provider: request.provider,
        domainIds: request.domainIds,
        orderCount: request.orderCount,
      });
      console.log('HyperTide order created:', result, 'with sender names:', request.senderNames);
      // Refresh after short delay to allow job to start
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
    if (!selectedClientId) return;
    setIsGenerating(true);
    try {
      // Call domain generation API
      await api.domainSourcing.generateForClient(selectedClientId, {
        count: 10,
        fill_package: true,
      });
      // Switch to pending view to show new domains
      setActiveView('pending');
      // Refresh waterfall to show new domains
      await refreshWaterfall();
    } catch (err) {
      console.error('Domain generation failed:', err);
    } finally {
      setIsGenerating(false);
    }
  };

  const handleCheckPrices = async () => {
    if (!selectedClient?.workspaceId) return;
    setIsCheckingPrices(true);
    setPriceCheckResult(null);

    // Start periodic refresh while checking (every 3 seconds)
    const refreshInterval = setInterval(async () => {
      try {
        await refreshWaterfall();
      } catch (err) {
        console.error('Refresh failed:', err);
      }
    }, 3000);

    try {
      const result = await api.infrastructure.bulkPriceCheckWorkspace(selectedClient.workspaceId, 50);
      setPriceCheckResult({ checked: result.checked, available: result.available });
      // Final refresh to show all updated prices
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
      {/* Sticky Header Card */}
      <div className="sticky top-0 z-50 p-4 bg-gray-50">
        <div className="max-w-[1800px] mx-auto">
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-4">
            <div className="flex items-center justify-between mb-3">
              {/* Left: Title with icon */}
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-gradient-to-br from-indigo-500 to-purple-600 rounded-lg flex items-center justify-center shadow-sm">
                  <Server className="w-6 h-6 text-white" />
                </div>
                <div>
                  <h1 className="text-xl font-semibold text-gray-900">
                    Infrastructure Provisioning
                  </h1>
                  <p className="text-sm text-gray-500">
                    Bulk domain & inbox provisioning workflow
                  </p>
                </div>
              </div>

              {/* Right: Client selector & refresh */}
              <div className="flex items-center gap-3">
                <Select
                  value={selectedClientId ?? ''}
                  onValueChange={setSelectedClient}
                  disabled={loadingClients}
                >
                  <SelectTrigger className="w-[280px] bg-gray-50 border-gray-200 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent">
                    <SelectValue
                      placeholder={loadingClients ? 'Loading clients...' : 'Select a client'}
                    />
                  </SelectTrigger>
                  <SelectContent>
                    {clients.map((client) => (
                      <SelectItem key={client.id} value={client.id}>
                        {client.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <button
                  onClick={() => refreshWaterfall()}
                  disabled={loading || !selectedClientId}
                  className="p-2 hover:bg-gray-100 rounded-lg transition-colors disabled:opacity-50"
                >
                  <RefreshCw className={`w-5 h-5 text-gray-500 ${loading ? 'animate-spin' : ''}`} />
                </button>
              </div>
            </div>

            {/* View tabs - Only show when client is selected */}
            {selectedClientId && (
              <div className="flex gap-2">
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
            )}
          </div>
        </div>
      </div>

      {/* Main Content - Scrollable */}
      <div className="flex-1 overflow-y-auto p-4 pt-0">
        <div className="max-w-[1800px] mx-auto space-y-4">
          {!selectedClientId ? (
            /* Empty State - No Client Selected */
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-16 text-center">
              <div className="max-w-md mx-auto">
                <div className="w-20 h-20 bg-gradient-to-br from-indigo-100 to-purple-100 rounded-2xl flex items-center justify-center mx-auto mb-6">
                  <Server className="w-10 h-10 text-indigo-600" />
                </div>
                <h3 className="text-xl font-semibold text-gray-900 mb-2">
                  Select a Client to Get Started
                </h3>
                <p className="text-gray-500 leading-relaxed">
                  Choose a client from the dropdown above to view and manage their
                  domain infrastructure, purchase new domains, and provision inboxes.
                </p>
              </div>
            </div>
          ) : (
            <>
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
                      {/* Selection info */}
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

                      {/* Quick actions - contextual based on selected domains */}
                      <div className="flex items-center gap-2">
                        {/* Purchase - only if selected domains are NOT purchased */}
                        {selectedForPurchase.length > 0 && (
                          <button
                            onClick={() => setShowPurchaseModal(true)}
                            className="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 transition-colors shadow-sm flex items-center gap-2"
                          >
                            <ShoppingCart className="w-4 h-4" />
                            Purchase ({selectedForPurchase.length})
                          </button>
                        )}
                        {/* Entra/Google Orders - only if purchased + DNS ready + NOT live */}
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
                        {/* If no actions available, show info */}
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

              {/* Quick Actions Bar (when nothing selected) */}
              {selectedDomainIds.size === 0 && (
                <div className="bg-gradient-to-r from-indigo-50 to-purple-50 rounded-xl border border-indigo-100 p-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <div className="w-8 h-8 bg-indigo-100 rounded-lg flex items-center justify-center">
                        <Waves className="w-4 h-4 text-indigo-600" />
                      </div>
                      <span className="text-sm font-medium text-indigo-900">
                        Quick Actions Available
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      {/* Generate Domains Button */}
                      <button
                        onClick={handleGenerateDomains}
                        disabled={isGenerating || !selectedClientId}
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
                      {/* Check Prices Button - always show for now, displays count */}
                      <button
                        onClick={handleCheckPrices}
                        disabled={isCheckingPrices || !selectedClient?.workspaceId || unpricedCount === 0}
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
                      {/* Price check result notification */}
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
                  <div className="px-6 py-4 border-b border-gray-200 bg-gradient-to-r from-gray-50 to-white">
                    <div className="flex items-center justify-between">
                      <div>
                        <h2 className="text-lg font-semibold text-gray-900">
                          {selectedClient?.name} Domains
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

                  {/* Waterfall Table - Scrollable */}
                  <div className="overflow-auto max-h-[calc(100vh-380px)]">
                    <WaterfallTable
                      domains={filteredDomains}
                      onBuyDomain={handleBuyDomain}
                    />
                  </div>
                </div>
              )}
            </>
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
        clientId={selectedClientId ?? ''}
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
