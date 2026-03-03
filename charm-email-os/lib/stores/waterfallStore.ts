/**
 * Waterfall Provisioning Store - V2
 * Manages the 6-column infrastructure provisioning waterfall view
 * with hierarchical filtering and client infrastructure summary
 */

import { create } from 'zustand';
import { api } from '@/lib/api';
import type {
  WaterfallDomain,
  WaterfallResponse,
  WaterfallFilters,
  ClientInfraSummary,
  TLD,
  ProviderType,
  BulkPurchasePreview,
  HyperTideOrderPreview,
} from '@/lib/types/infrastructure';
import { PRICE_BUDGET_LIMIT, PROVIDER_CONFIG } from '@/lib/types/infrastructure';

type RotationStatus = 'healthy' | 'monitor' | 'consider_rotate' | 'rotate_now';
type FulfillmentStatus = 'pending' | 'under_delivered' | 'fulfilled' | 'over_delivered';
type DomainStatus = 'live' | 'flagged' | 'dead';

interface FilterCounts {
  // Lifecycle stage counts
  notPurchased: number;        // Need to buy domain
  ready: number;               // Purchased + DNS ready, need to order HyperTide
  complete: number;            // Has inboxes from EmailBison (operational)
  purchased: number;           // Legacy: all purchased domains (ready + complete + in-progress)
  overBudget: number;
  deactivated: number;
  needsReconnection: number;   // Domains where all live inboxes are disconnected
  byTld: Record<TLD, number>;
  byProvider: Record<ProviderType | 'unassigned', number>;
  byStatus: Record<DomainStatus | 'pending', number>;
  byRotation: Record<RotationStatus, number>;
  byFulfillment: Record<FulfillmentStatus, number>;
}

interface WaterfallState {
  // Data
  selectedClientId: string | null;
  workspaceId: string | null;
  domains: WaterfallDomain[];
  totalDomains: number;
  infraSummary: ClientInfraSummary | null;
  filterCounts: FilterCounts | null;
  loading: boolean;
  error: string | null;

  // Filters (hierarchical)
  filters: WaterfallFilters;

  // Selection
  selectedDomainIds: Set<string>;

  // Sort
  sortBy: 'domain' | 'price' | 'purchasedAt' | 'tld';
  sortDirection: 'asc' | 'desc';

  // Actions - Client
  setSelectedClient: (clientId: string) => void;
  loadWaterfall: () => Promise<void>;
  refreshWaterfall: () => Promise<void>;

  // Actions - Filters
  setFilter: <K extends keyof WaterfallFilters>(key: K, value: WaterfallFilters[K]) => void;
  resetFilters: () => void;
  toggleShowOverBudget: () => void;
  toggleShowDeactivated: () => void;
  toggleShowNeedsReconnection: () => void;

  // Actions - Sort
  setSort: (sortBy: WaterfallState['sortBy'], direction?: 'asc' | 'desc') => void;

  // Actions - Selection
  toggleDomainSelection: (domainId: string) => void;
  selectAllVisible: () => void;
  selectDomainsForPurchase: () => void; // Select all unpurchased, under budget
  selectDomainsForHyperTide: (provider: ProviderType) => void; // FIFO selection
  clearSelection: () => void;

  // Computed getters
  getSelectedDomains: () => WaterfallDomain[];
  getDomainsReadyForPurchase: () => WaterfallDomain[];
  getDomainsReadyForHyperTide: (provider: ProviderType) => WaterfallDomain[];
  getBulkPurchasePreview: () => BulkPurchasePreview | null;
  getHyperTideOrderPreview: (provider: ProviderType) => HyperTideOrderPreview | null;

  // Actions - Reset
  reset: () => void;
}

const defaultFilters: WaterfallFilters = {
  purchaseStatus: 'all',
  tld: 'all',
  provider: 'all',
  rotationStatus: 'all',
  showOverBudget: false,
  showDeactivated: false,
  showNeedsReconnection: false,
};

const defaultFilterCounts: FilterCounts = {
  notPurchased: 0,
  ready: 0,
  complete: 0,
  purchased: 0,
  overBudget: 0,
  deactivated: 0,
  needsReconnection: 0,
  byTld: { com: 0, co: 0, info: 0 },
  byProvider: { entra: 0, google: 0, unassigned: 0 },
  byStatus: { live: 0, flagged: 0, dead: 0, pending: 0 },
  byRotation: { healthy: 0, monitor: 0, consider_rotate: 0, rotate_now: 0 },
  byFulfillment: { pending: 0, under_delivered: 0, fulfilled: 0, over_delivered: 0 },
};

export const useWaterfallStore = create<WaterfallState>((set, get) => ({
  // Initial state
  selectedClientId: null,
  workspaceId: null,
  domains: [],
  totalDomains: 0,
  infraSummary: null,
  filterCounts: null,
  loading: false,
  error: null,

  filters: { ...defaultFilters },
  selectedDomainIds: new Set(),
  sortBy: 'domain',
  sortDirection: 'asc',

  // Set selected client and load waterfall
  setSelectedClient: (clientId: string) => {
    set({
      selectedClientId: clientId,
      selectedDomainIds: new Set(),
      filters: { ...defaultFilters },
    });
    get().loadWaterfall();
  },

  // Load waterfall data from API
  loadWaterfall: async () => {
    const { selectedClientId, filters } = get();

    if (!selectedClientId) {
      set({ domains: [], totalDomains: 0, infraSummary: null, filterCounts: null });
      return;
    }

    set({ loading: true, error: null });

    try {
      const response: WaterfallResponse = await api.infrastructure.getWaterfallByClient(
        selectedClientId,
        {
          purchaseStatus: filters.purchaseStatus,
          tld: filters.tld === 'all' ? undefined : filters.tld,
          provider: filters.provider === 'all' ? undefined : filters.provider,
          rotationStatus: filters.rotationStatus === 'all' ? undefined : filters.rotationStatus,
          showOverBudget: filters.showOverBudget,
          showDeactivated: filters.showDeactivated,
          showNeedsReconnection: filters.showNeedsReconnection,
        }
      );

      set({
        workspaceId: response.workspaceId,
        domains: response.domains,
        totalDomains: response.totalDomains,
        infraSummary: response.summary,
        filterCounts: response.filters?.counts ?? defaultFilterCounts,
        loading: false,
      });
    } catch (error) {
      console.error('Failed to load waterfall:', error);
      set({
        error: error instanceof Error ? error.message : 'Failed to load waterfall data',
        loading: false,
      });
    }
  },

  // Refresh without changing filters
  refreshWaterfall: async () => {
    await get().loadWaterfall();
  },

  // Update a single filter and reload
  setFilter: (key, value) => {
    set((state) => ({
      filters: { ...state.filters, [key]: value },
    }));
    get().loadWaterfall();
  },

  // Reset all filters
  resetFilters: () => {
    set({ filters: { ...defaultFilters } });
    get().loadWaterfall();
  },

  // Toggle over-budget visibility
  toggleShowOverBudget: () => {
    set((state) => ({
      filters: { ...state.filters, showOverBudget: !state.filters.showOverBudget },
    }));
    get().loadWaterfall();
  },

  // Toggle deactivated visibility
  toggleShowDeactivated: () => {
    set((state) => ({
      filters: { ...state.filters, showDeactivated: !state.filters.showDeactivated },
    }));
    get().loadWaterfall();
  },

  // Toggle needs reconnection filter (show only domains where all inboxes disconnected)
  toggleShowNeedsReconnection: () => {
    set((state) => ({
      filters: { ...state.filters, showNeedsReconnection: !state.filters.showNeedsReconnection },
    }));
    get().loadWaterfall();
  },

  // Set sort
  setSort: (sortBy, direction) => {
    set((state) => ({
      sortBy,
      sortDirection: direction ?? (state.sortBy === sortBy && state.sortDirection === 'asc' ? 'desc' : 'asc'),
    }));
  },

  // Toggle single domain selection
  toggleDomainSelection: (domainId: string) => {
    const { selectedDomainIds } = get();
    const newSelection = new Set(selectedDomainIds);

    if (newSelection.has(domainId)) {
      newSelection.delete(domainId);
    } else {
      newSelection.add(domainId);
    }

    set({ selectedDomainIds: newSelection });
  },

  // Select all visible domains
  selectAllVisible: () => {
    const { domains } = get();
    set({ selectedDomainIds: new Set(domains.map((d) => d.domainId)) });
  },

  // Select all domains ready for purchase (unpurchased, under budget)
  selectDomainsForPurchase: () => {
    const readyDomains = get().getDomainsReadyForPurchase();
    set({ selectedDomainIds: new Set(readyDomains.map((d) => d.domainId)) });
  },

  // FIFO selection for HyperTide orders
  selectDomainsForHyperTide: (provider: ProviderType) => {
    const readyDomains = get().getDomainsReadyForHyperTide(provider);
    const config = PROVIDER_CONFIG[provider];

    // Select domains in batches of domainsPerOrder
    const batchSize = config.domainsPerOrder;
    const maxDomains = Math.floor(readyDomains.length / batchSize) * batchSize;
    const domainsToSelect = readyDomains.slice(0, maxDomains);

    set({ selectedDomainIds: new Set(domainsToSelect.map((d) => d.domainId)) });
  },

  // Clear all selections
  clearSelection: () => {
    set({ selectedDomainIds: new Set() });
  },

  // Get selected domain objects
  getSelectedDomains: () => {
    const { domains, selectedDomainIds } = get();
    return domains.filter((d) => selectedDomainIds.has(d.domainId));
  },

  // Get domains ready for purchase
  getDomainsReadyForPurchase: () => {
    const { domains } = get();
    return domains.filter(
      (d) =>
        !d.isPurchased &&
        !d.isOverBudget &&
        d.bestPrice != null &&
        d.bestPrice > 0
    );
  },

  // Get domains ready for HyperTide (FIFO sorted)
  getDomainsReadyForHyperTide: (provider: ProviderType) => {
    const { domains } = get();
    return domains
      .filter((d) => d.isReadyForHyperTide && (!d.assignedProvider || d.assignedProvider === provider))
      .sort((a, b) => {
        // Sort by purchase date (oldest first) - FIFO
        const dateA = a.purchasedAt ? new Date(a.purchasedAt).getTime() : Infinity;
        const dateB = b.purchasedAt ? new Date(b.purchasedAt).getTime() : Infinity;
        return dateA - dateB;
      });
  },

  // Generate bulk purchase preview from selected domains
  getBulkPurchasePreview: () => {
    const selected = get().getSelectedDomains();
    const purchasable = selected.filter((d) => !d.isPurchased && !d.isOverBudget && d.bestPrice);

    if (purchasable.length === 0) return null;

    const domainList = purchasable.map((d) => ({
      domainId: d.domainId,
      domainName: d.domainName,
      registrar: d.bestRegistrar!,
      price: d.bestPrice!,
    }));

    // Group by registrar
    const porkbunDomains = domainList.filter((d) => d.registrar === 'porkbun');
    const dynadotDomains = domainList.filter((d) => d.registrar === 'dynadot');

    const breakdown: BulkPurchasePreview['breakdown'] = [];

    if (porkbunDomains.length > 0) {
      breakdown.push({
        registrar: 'porkbun',
        domainCount: porkbunDomains.length,
        subtotal: porkbunDomains.reduce((sum, d) => sum + d.price, 0),
      });
    }

    if (dynadotDomains.length > 0) {
      breakdown.push({
        registrar: 'dynadot',
        domainCount: dynadotDomains.length,
        subtotal: dynadotDomains.reduce((sum, d) => sum + d.price, 0),
      });
    }

    return {
      domains: domainList,
      breakdown,
      totalDomains: domainList.length,
      totalCost: domainList.reduce((sum, d) => sum + d.price, 0),
    };
  },

  // Generate HyperTide order preview
  getHyperTideOrderPreview: (provider: ProviderType) => {
    const { selectedClientId, infraSummary } = get();
    const selected = get().getSelectedDomains();
    const readyDomains = selected.filter((d) => d.isReadyForHyperTide);

    if (!selectedClientId || readyDomains.length === 0) return null;

    const config = PROVIDER_CONFIG[provider];
    const orderCount = Math.floor(readyDomains.length / config.domainsPerOrder);

    if (orderCount === 0) return null;

    const domainsToOrder = readyDomains.slice(0, orderCount * config.domainsPerOrder);

    // Get package info from summary
    const providerSummary = infraSummary?.[provider];
    const currentPackages = providerSummary?.packageCount ?? 0;
    const usedPackages = Math.ceil((providerSummary?.domainsActual ?? 0) / config.domainsPerOrder);
    const availablePackages = currentPackages - usedPackages;

    const validationErrors: string[] = [];
    if (orderCount > availablePackages && availablePackages >= 0) {
      validationErrors.push(
        `Order exceeds package limit: ${orderCount} orders requested, ${availablePackages} available`
      );
    }

    return {
      clientId: selectedClientId,
      clientName: infraSummary?.clientName ?? 'Unknown',
      provider,
      selectedDomains: domainsToOrder.map((d) => ({
        domainId: d.domainId,
        domainName: d.domainName,
        purchasedAt: d.purchasedAt!,
        dnsReadyAt: d.nameserverVerifiedAt!,
      })),
      orderCount,
      domainsPerOrder: config.domainsPerOrder,
      inboxesPerDomain: config.inboxesPerDomain,
      totalInboxes: orderCount * config.inboxesPerOrder,
      currentPackages,
      usedPackages,
      availablePackages,
      withinLimit: orderCount <= availablePackages || availablePackages < 0,
      monthlyCost: orderCount * config.costPerOrder,
      isValid: validationErrors.length === 0,
      validationErrors,
    };
  },

  // Reset all state
  reset: () => {
    set({
      selectedClientId: null,
      workspaceId: null,
      domains: [],
      totalDomains: 0,
      infraSummary: null,
      filterCounts: null,
      loading: false,
      error: null,
      filters: { ...defaultFilters },
      selectedDomainIds: new Set(),
      sortBy: 'domain',
      sortDirection: 'asc',
    });
  },
}));
