// ============================================
// INFRASTRUCTURE WATERFALL TYPES - V2
// 6-Column Layout: Domain → Pricing → DNS → Provider → HyperTide → Status
// ============================================

// ===========================================
// DOMAIN TYPES
// ===========================================

export type TLD = 'com' | 'co' | 'info';

export type DomainStatus = 'live' | 'flagged' | 'dead';

export type DNSStatus = 'pending' | 'propagating' | 'ready' | 'mismatch' | 'failed';

export type PurchaseStatus = 'not_purchased' | 'purchased';

export type ProviderType = 'entra' | 'google';

export type HyperTideStatus = 'not_ordered' | 'ordered' | 'provisioning' | 'complete' | 'failed';

export type DomainSource = 'generated' | 'legacy' | 'external';

// ===========================================
// WATERFALL DOMAIN
// ===========================================

export interface WaterfallDomain {
  // Core
  domainId: string;
  domainName: string;
  workspaceId: string;
  tld: TLD;
  domainSource?: DomainSource; // Where the domain came from

  // Column 1: Domain
  generatedAt: string;
  legitimacyScore?: number | null;
  ownedByClient: boolean;

  // Column 2: Pricing
  porkbunPrice?: number | null;
  porkbunAvailable?: boolean | null;
  dynadotPrice?: number | null;
  dynadotAvailable?: boolean | null;
  bestPrice?: number | null;
  bestRegistrar?: 'porkbun' | 'dynadot' | null;
  priceCheckedAt?: string | null;
  isOverBudget: boolean; // >$15

  // Column 2 (continued): Purchase
  purchasedAt?: string | null;
  purchaseRegistrar?: 'porkbun' | 'dynadot' | null;
  purchasePrice?: number | null;
  purchaseStatus: PurchaseStatus;

  // Column 3: DNS
  dnsStatus: DNSStatus;
  nameserversUpdatedAt?: string | null;
  nameserverVerifiedAt?: string | null;
  currentNameservers?: string[];
  spfConfigured?: boolean;
  dkimConfigured?: boolean;
  dmarcConfigured?: boolean;
  mxConfigured?: boolean;

  // Column 4: Provider
  assignedProvider?: ProviderType | null;
  providerAssignedAt?: string | null;

  // Column 5: HyperTide
  hypertideStatus: HyperTideStatus;
  hypertideOrderJobId?: string;
  hypertideOrderedAt?: string;
  hypertideCompletedAt?: string;
  hypertideProgress?: number; // 0-100 percent

  // Column 6: Status
  domainStatus: DomainStatus;
  liveInboxCount: number;
  deadInboxCount: number;
  flaggedInboxCount?: number;
  totalInboxCount: number;
  expectedInboxCount: number; // 50 for Entra, 3 for Google
  lastInboxSyncedAt?: string | null;

  // Connection status (for live inboxes)
  connectedInboxCount: number;      // Live + Connected to EmailBison
  disconnectedInboxCount: number;   // Live but needs reconnection via HyperTide
  daysDisconnected?: number | null; // Days since oldest live inbox became disconnected (for 21-day warning)

  // Computed
  isPurchased: boolean;
  isReadyForHyperTide: boolean; // purchased + dns ready + no active order
  isDeactivated: boolean; // domainStatus === 'dead'
}

// ===========================================
// FILTER TYPES
// ===========================================

export interface WaterfallFilters {
  // Primary filter (hierarchy root)
  purchaseStatus: 'all' | 'purchased' | 'not_purchased';

  // Secondary filters
  tld: TLD | 'all';
  provider: ProviderType | 'all';
  status: DomainStatus | 'all';

  // Toggles
  showOverBudget: boolean; // Show domains >$15 (default: false)
  showDeactivated: boolean; // Show dead domains (default: false)
  showNeedsReconnection: boolean; // Show only domains where all inboxes disconnected (default: false)
}

// ===========================================
// CLIENT INFRASTRUCTURE SUMMARY
// ===========================================

export interface ProviderSummary {
  provider: ProviderType;
  packageCount: number; // Purchased packages
  domainsActual: number; // Provisioned domains (have at least 1 inbox)
  domainsHealthy: number;
  domainsFlagged: number; // At risk (warning + critical + all disconnected)
  domainsDead: number; // Deprecated (had inboxes, all died)
  domainsAwaiting: number; // Awaiting provisioning (never had inboxes)
  inboxesLive: number; // inbox_state = 'live' (not killed)
  inboxesDead: number; // inbox_state = 'dead' (killed)
  inboxesConnected: number; // Live + status = 'Connected' (actually working)
  inboxesDisconnected: number; // Live but status = 'Not connected' (needs reconnection)
  inboxesTotal: number;
  dailyCapacity: number; // Based on CONNECTED inboxes only
}

export interface ClientInfraSummary {
  clientId: string;
  clientName: string;
  packageName?: string | null; // Assigned package template name (e.g., "Starter", "Growth")
  entra: ProviderSummary;
  google: ProviderSummary;
  totalDomains: number;
  totalInboxes: number;
  totalLiveInboxes: number;
  totalConnectedInboxes: number; // Actually operational inboxes
}

// ===========================================
// API RESPONSE TYPES
// ===========================================

export interface WaterfallResponse {
  workspaceId: string;
  clientId: string;
  domains: WaterfallDomain[];
  totalDomains: number;
  summary: ClientInfraSummary;
  filters: {
    appliedFilters: WaterfallFilters;
    counts: {
      purchased: number;
      notPurchased: number;
      overBudget: number;
      deactivated: number;
      needsReconnection: number; // Domains where all live inboxes are disconnected
      byTld: Record<TLD, number>;
      byProvider: Record<ProviderType | 'unassigned', number>;
      byStatus: Record<DomainStatus | 'pending', number>;
    };
  };
}

// ===========================================
// BULK PURCHASE TYPES
// ===========================================

export interface BulkPurchasePreview {
  domains: {
    domainId: string;
    domainName: string;
    registrar: 'porkbun' | 'dynadot';
    price: number;
  }[];
  breakdown: {
    registrar: 'porkbun' | 'dynadot';
    domainCount: number;
    subtotal: number;
  }[];
  totalDomains: number;
  totalCost: number;
}

export interface BulkPurchaseRequest {
  clientId: string;
  domainIds: string[];
}

export interface BulkPurchaseResponse {
  jobId: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  domainsProcessed: number;
  totalDomains: number;
  message: string;
}

// ===========================================
// HYPERTIDE ORDER TYPES
// ===========================================

export interface HyperTideOrderPreview {
  clientId: string;
  clientName: string;
  provider: ProviderType;

  // Auto-selected domains (FIFO: oldest purchased + DNS ready)
  selectedDomains: {
    domainId: string;
    domainName: string;
    purchasedAt: string;
    dnsReadyAt: string;
  }[];

  // Order details
  orderCount: number; // Number of HyperTide orders
  domainsPerOrder: number; // 2 for Entra, 5 for Google
  inboxesPerDomain: number; // 50 for Entra, 3 for Google
  totalInboxes: number;

  // Capacity check
  currentPackages: number;
  usedPackages: number;
  availablePackages: number;
  withinLimit: boolean;

  // Cost
  monthlyCost: number; // $50 per order

  // Validation
  isValid: boolean;
  validationErrors: string[];
}

export interface HyperTideOrderRequest {
  clientId: string;
  workspaceId: string;
  provider: ProviderType;
  domainIds: string[]; // Usually auto-selected, can be overridden
  orderCount: number;
}

export interface HyperTideOrderResponse {
  jobId: string;
  totalOrders: number;
  status: 'pending' | 'executing' | 'completed' | 'failed';
  estimatedDurationSeconds: number;
  message: string;
}

// ===========================================
// SENDER NAMES (unchanged)
// ===========================================

export interface SenderName {
  id: string;
  firstName: string;
  lastName: string;
  fullName: string;
  isFounder: boolean;
}

export interface SenderNamesResponse {
  clientId: string;
  workspaceId: string;
  senderNames: SenderName[];
}

// ===========================================
// COLUMN DEFINITIONS
// ===========================================

export const WATERFALL_COLUMNS = [
  {
    id: 'domain',
    label: 'Domain',
    shortLabel: 'Domain',
    description: 'AI-generated domain with TLD badge',
    width: 220,
  },
  {
    id: 'pricing',
    label: 'Price & Purchase',
    shortLabel: 'Price',
    description: 'Registrar prices and purchase status',
    width: 180,
  },
  {
    id: 'dns',
    label: 'DNS',
    shortLabel: 'DNS',
    description: 'Nameserver configuration status',
    width: 140,
  },
  {
    id: 'hypertide',
    label: 'HyperTide',
    shortLabel: 'HyperTide',
    description: 'Inbox provisioning status',
    width: 160,
  },
  {
    id: 'provider',
    label: 'Provider',
    shortLabel: 'Provider',
    description: 'Entra or Google assignment',
    width: 120,
  },
  {
    id: 'status',
    label: 'Status',
    shortLabel: 'Status',
    description: 'Live, Flagged, or Dead',
    width: 140,
  },
] as const;

export type WaterfallColumnId = typeof WATERFALL_COLUMNS[number]['id'];

// ===========================================
// CONSTANTS
// ===========================================

export const PRICE_BUDGET_LIMIT = 15; // Dollars

export const DNSIMPLE_NAMESERVERS = [
  'ns1.dnsimple.com',
  'ns2.dnsimple-edge.net',
  'ns3.dnsimple.com',
  'ns4.dnsimple-edge.org',
] as const;

export const PROVIDER_CONFIG = {
  entra: {
    domainsPerOrder: 2,
    inboxesPerDomain: 50,
    inboxesPerOrder: 100,
    costPerOrder: 50,
  },
  google: {
    domainsPerOrder: 5,
    inboxesPerDomain: 3,
    inboxesPerOrder: 15,
    costPerOrder: 50,
  },
} as const;

// TLD configuration matching domain generator
export const ALLOWED_TLDS: TLD[] = ['com', 'co', 'info'];

export const TLD_DISPLAY = {
  com: { label: '.com', color: 'bg-blue-100 text-blue-700' },
  co: { label: '.co', color: 'bg-purple-100 text-purple-700' },
  info: { label: '.info', color: 'bg-amber-100 text-amber-700' },
} as const;
