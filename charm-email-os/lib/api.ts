/**
 * Charm Email OS API Service Layer
 * Connects to FastAPI backend which reads from OwnRBL PostgreSQL
 */

import type {
  Client,
  Workspace,
  Domain,
  Inbox,
  Campaign,
  Lead,
  OnboardingData,
  PaginatedResponse,
  HealthOverview,
  Alert,
  PackageTemplate,
  Subscription,
  SubscriptionWithUsage,
  SubscriptionChange,
  BaseName,
  SenderNameVariation,
  VariationPattern,
  SenderNamesForProvisioningResponse,
  ExecutePurchaseV2Request,
  ExecutePurchaseV2Summary,
  OrderGroup,
  InfrastructureType,
  SmartOrderPreview,
  SmartOrderRequest,
  SmartOrderResponse,
  InventoryHealth,
  CampaignDocument,
  ClientDocumentsResponse,
  UnifiedCycleData,
  UnifiedCycleResponse,
  CycleStrategyConfig,
  CycleVariable,
  CycleRegenerationRequest,
  CycleRegenerationResponse,
} from './types';

import type {
  WaterfallResponse,
  HyperTideOrderRequest,
  HyperTideOrderResponse,
  SenderName,
  SenderNamesResponse,
} from './types/infrastructure';

// API base URL - use environment variable or default to deployed API
const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://ccssgc4gowsog04wck400o0w.31.97.142.123.sslip.io';

// ===== API UTILITIES =====

class APIError extends Error {
  constructor(
    public status: number,
    public statusText: string,
    public detail?: string
  ) {
    super(detail || `API Error: ${status} ${statusText}`);
    this.name = 'APIError';
  }
}

async function fetchApi<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE}${endpoint}`;

  try {
    const response = await fetch(url, {
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers,
      },
      ...options,
    });

    if (!response.ok) {
      let detail: string | undefined;
      try {
        const errorData = await response.json();
        // Handle FastAPI validation errors (detail is array) vs regular errors (detail is string)
        if (Array.isArray(errorData.detail)) {
          // Extract error messages from validation error array
          detail = errorData.detail
            .map((err: { msg?: string; message?: string }) => err.msg || err.message || 'Validation error')
            .join('; ');
        } else if (typeof errorData.detail === 'string') {
          detail = errorData.detail;
        } else if (errorData.detail) {
          detail = JSON.stringify(errorData.detail);
        } else if (errorData.message) {
          detail = errorData.message;
        }
      } catch {
        // Ignore JSON parse error
      }
      throw new APIError(response.status, response.statusText, detail);
    }

    return response.json();
  } catch (error) {
    if (error instanceof APIError) {
      throw error;
    }
    // Network error or other issue
    throw new APIError(0, 'Network Error', `Failed to connect to API: ${error}`);
  }
}

// Helper to convert snake_case to camelCase
function toCamelCase<T>(obj: Record<string, unknown>): T {
  if (Array.isArray(obj)) {
    return obj.map((item) =>
      typeof item === 'object' && item !== null ? toCamelCase(item as Record<string, unknown>) : item
    ) as unknown as T;
  }

  if (typeof obj !== 'object' || obj === null) {
    return obj as T;
  }

  const result: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(obj)) {
    // Convert snake_case to camelCase:
    // 1. _a → A (uppercase letters after underscore)
    // 2. _7 → 7 (remove underscore before digits, e.g., hard_bounces_7d → hardBounces7d)
    const camelKey = key
      .replace(/_([a-z])/g, (_, letter) => letter.toUpperCase())
      .replace(/_(\d)/g, '$1');
    result[camelKey] =
      typeof value === 'object' && value !== null
        ? toCamelCase(value as Record<string, unknown>)
        : value;
  }

  // Add backward-compatible aliases for Domain and Inbox types
  // API returns domain_name/email_address, but frontend expects domain/email
  if ('domainName' in result && !('domain' in result)) {
    result.domain = result.domainName;
  }
  if ('emailAddress' in result && !('email' in result)) {
    result.email = result.emailAddress;
  }

  return result as T;
}

// Helper to convert camelCase to snake_case for API requests
function toSnakeCase(obj: Record<string, unknown>): Record<string, unknown> {
  if (Array.isArray(obj)) {
    return obj.map((item) =>
      typeof item === 'object' && item !== null ? toSnakeCase(item as Record<string, unknown>) : item
    ) as unknown as Record<string, unknown>;
  }

  if (typeof obj !== 'object' || obj === null) {
    return obj;
  }

  const result: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(obj)) {
    const snakeKey = key.replace(/[A-Z]/g, (letter) => `_${letter.toLowerCase()}`);
    result[snakeKey] =
      typeof value === 'object' && value !== null
        ? toSnakeCase(value as Record<string, unknown>)
        : value;
  }
  return result;
}

// ===== WORKSPACE API =====

export const workspaceApi = {
  /**
   * List all OwnRBL workspaces
   */
  async list(params?: { page?: number; pageSize?: number; search?: string }) {
    const searchParams = new URLSearchParams();
    if (params?.page) searchParams.set('page', params.page.toString());
    if (params?.pageSize) searchParams.set('page_size', params.pageSize.toString());
    if (params?.search) searchParams.set('search', params.search);

    const query = searchParams.toString();
    const response = await fetchApi<{
      items: Record<string, unknown>[];
      total: number;
      page: number;
      page_size: number;
    }>(`/api/workspaces${query ? `?${query}` : ''}`);

    return {
      items: response.items.map((item) => toCamelCase<Workspace>(item)),
      total: response.total,
      page: response.page,
      pageSize: response.page_size,
    } as PaginatedResponse<Workspace>;
  },

  /**
   * Get compact workspace list for dropdowns
   */
  async listSummary() {
    const response = await fetchApi<Record<string, unknown>[]>('/api/workspaces/summary');
    return response.map((item) => toCamelCase<Workspace>(item));
  },

  /**
   * Get a single workspace by ID
   */
  async get(id: string) {
    const response = await fetchApi<Record<string, unknown>>(`/api/workspaces/${id}`);
    return toCamelCase<Workspace>(response);
  },

  /**
   * Get workspace statistics
   */
  async getStats(id: string) {
    return fetchApi<{
      workspace_id: string;
      inboxes: { total_inboxes: number; live_inboxes: number; dead_inboxes: number };
      domains: { total_domains: number; clean_domains: number };
      campaigns: { total_campaigns: number; active_campaigns: number };
    }>(`/api/workspaces/${id}/stats`);
  },
};

// ===== CLIENT API =====

export const clientApi = {
  /**
   * List all clients
   */
  async list(params?: {
    page?: number;
    pageSize?: number;
    search?: string;
    onboardingComplete?: boolean;
  }) {
    const searchParams = new URLSearchParams();
    if (params?.page) searchParams.set('page', params.page.toString());
    if (params?.pageSize) searchParams.set('page_size', params.pageSize.toString());
    if (params?.search) searchParams.set('search', params.search);
    if (params?.onboardingComplete !== undefined) {
      searchParams.set('onboarding_complete', params.onboardingComplete.toString());
    }

    const query = searchParams.toString();
    const response = await fetchApi<{
      items: Record<string, unknown>[];
      total: number;
      page: number;
      page_size: number;
    }>(`/api/clients${query ? `?${query}` : ''}`);

    return {
      items: response.items.map((item) => toCamelCase<Client>(item)),
      total: response.total,
      page: response.page,
      pageSize: response.page_size,
    } as PaginatedResponse<Client>;
  },

  /**
   * Get a single client by ID
   */
  async get(id: string) {
    const response = await fetchApi<Record<string, unknown>>(`/api/clients/${id}`);
    return toCamelCase<Client>(response);
  },

  /**
   * Create a new client
   */
  async create(data: {
    name: string;
    workspaceId?: string;
    logoUrl?: string;
    onboardingData?: { primaryDomain?: string };
  }) {
    const response = await fetchApi<Record<string, unknown>>('/api/clients', {
      method: 'POST',
      body: JSON.stringify(toSnakeCase(data as Record<string, unknown>)),
    });
    return toCamelCase<Client>(response);
  },

  /**
   * Update a client
   */
  async update(
    id: string,
    data: Partial<{
      name: string;
      workspaceId: string;
      logoUrl: string;
      onboardingComplete: boolean;
      onboardingData: OnboardingData;
      // Profile fields
      contactName: string;
      contactEmail: string;
      website: string;
      industry: string;
      domainPattern: string;
      // Workspace sync control
      syncEnabled: boolean;
    }>
  ) {
    const response = await fetchApi<Record<string, unknown>>(`/api/clients/${id}`, {
      method: 'PUT',
      body: JSON.stringify(toSnakeCase(data as Record<string, unknown>)),
    });
    return toCamelCase<Client>(response);
  },

  /**
   * Delete a client
   */
  async delete(id: string) {
    return fetchApi<{ message: string }>(`/api/clients/${id}`, {
      method: 'DELETE',
    });
  },

  /**
   * Link a client to an OwnRBL workspace
   */
  async linkWorkspace(clientId: string, workspaceId: string) {
    const response = await fetchApi<Record<string, unknown>>(
      `/api/clients/${clientId}/link-workspace`,
      {
        method: 'POST',
        body: JSON.stringify({ workspace_id: workspaceId }),
      }
    );
    return toCamelCase<Client>(response);
  },

  /**
   * Complete client onboarding
   */
  async completeOnboarding(id: string, data: OnboardingData) {
    const response = await fetchApi<Record<string, unknown>>(`/api/clients/${id}/onboard`, {
      method: 'POST',
      body: JSON.stringify({ onboarding_data: toSnakeCase(data as unknown as Record<string, unknown>) }),
    });
    return toCamelCase<Client>(response);
  },

  /**
   * Generate sender names for a client
   * Generates names based on personas, custom names, or random generation
   */
  async generateSenderNames(
    clientId: string,
    options?: {
      count?: number;
      usePersonas?: boolean;
      customNames?: Array<{
        firstName: string;
        lastName: string;
        emailPrefix: string;
      }>;
    }
  ) {
    const response = await fetchApi<{
      names: Array<{
        firstName: string;
        lastName: string;
        emailPrefix: string;
        source: 'persona' | 'custom' | 'generated';
      }>;
      total_count: number;
      from_personas: number;
      from_custom: number;
      from_generated: number;
    }>(`/api/clients/${clientId}/generate-sender-names`, {
      method: 'POST',
      body: JSON.stringify({
        count: options?.count ?? 10,
        use_personas: options?.usePersonas ?? true,
        custom_names: options?.customNames?.map(n => ({
          first_name: n.firstName,
          last_name: n.lastName,
          email_prefix: n.emailPrefix,
        })),
      }),
    });
    return {
      names: response.names,
      totalCount: response.total_count,
      fromPersonas: response.from_personas,
      fromCustom: response.from_custom,
      fromGenerated: response.from_generated,
    };
  },

  /**
   * Get pre-generated sender names for a client
   */
  async getSenderNames(clientId: string) {
    return fetchApi<{
      names: Array<{
        firstName: string;
        lastName: string;
        emailPrefix: string;
        source: 'persona' | 'custom' | 'generated';
      }>;
      count: number;
      preferences: {
        usePersonas: boolean;
        nameCount: number;
        customNames?: Array<{
          firstName: string;
          lastName: string;
          emailPrefix: string;
        }>;
      } | null;
    }>(`/api/clients/${clientId}/sender-names`);
  },

  // ===== NAME VARIATION ENDPOINTS (Phase 6A.5) =====

  /**
   * Get available name variation patterns
   * Returns list of patterns with descriptions and examples
   */
  async getNamePatterns() {
    return fetchApi<{
      patterns: VariationPattern[];
      default_patterns: string[];
    }>('/api/clients/name-patterns');
  },

  /**
   * Generate email prefix variations from base names
   * Base names are the real identities (1-2 names like "Chris Booth")
   * Variations are different email prefix formats generated from those names
   */
  async generateNameVariations(
    clientId: string,
    baseNames: BaseName[],
    patterns?: string[],
    count: number = 10
  ): Promise<{
    variations: SenderNameVariation[];
    count: number;
    patternsUsed: string[];
    baseNames: BaseName[];
  }> {
    const response = await fetchApi<{
      variations: Array<{
        firstName: string;
        lastName: string;
        emailPrefix: string;
        baseName: string;
        pattern: string;
        isFounder?: boolean;
      }>;
      count: number;
      patterns_used: string[];
      base_names: Array<{
        firstName: string;
        lastName: string;
        isFounder?: boolean;
      }>;
    }>(`/api/clients/${clientId}/generate-name-variations`, {
      method: 'POST',
      body: JSON.stringify({
        base_names: baseNames.map(bn => ({
          first_name: bn.firstName,
          last_name: bn.lastName,
          is_founder: bn.isFounder ?? false,
        })),
        patterns: patterns ?? undefined,
        count,
      }),
    });

    return {
      variations: response.variations.map(v => ({
        firstName: v.firstName,
        lastName: v.lastName,
        emailPrefix: v.emailPrefix,
        baseName: v.baseName,
        pattern: v.pattern,
        isFounder: v.isFounder,
      })),
      count: response.count,
      patternsUsed: response.patterns_used,
      baseNames: response.base_names.map(bn => ({
        firstName: bn.firstName,
        lastName: bn.lastName,
        isFounder: bn.isFounder,
      })),
    };
  },

  /**
   * Save sender names (base names + variations) to client profile
   * Stores in onboarding_data JSONB for reuse in Hypertide purchase wizard
   */
  async saveSenderNames(
    clientId: string,
    baseNames: BaseName[],
    variations: SenderNameVariation[],
    patterns: string[]
  ): Promise<Client> {
    const response = await fetchApi<Record<string, unknown>>(
      `/api/clients/${clientId}/sender-names`,
      {
        method: 'PUT',
        body: JSON.stringify({
          base_names: baseNames.map(bn => ({
            first_name: bn.firstName,
            last_name: bn.lastName,
            is_founder: bn.isFounder ?? false,
          })),
          variations: variations.map(v => ({
            first_name: v.firstName,
            last_name: v.lastName,
            email_prefix: v.emailPrefix,
            base_name: v.baseName,
            pattern: v.pattern,
            is_founder: v.isFounder ?? false,
          })),
          patterns,
        }),
      }
    );
    return toCamelCase<Client>(response);
  },

  /**
   * Get the full sender name configuration for a client
   * Returns base names, patterns, and generated variations
   */
  async getSenderNameConfig(clientId: string): Promise<{
    baseNames: BaseName[];
    patterns: string[];
    variations: SenderNameVariation[];
    hasConfig: boolean;
    availablePatterns: VariationPattern[];
  }> {
    const response = await fetchApi<{
      baseNames: Array<{
        firstName: string;
        lastName: string;
        isFounder?: boolean;
      }>;
      patterns: string[];
      variations: Array<{
        firstName: string;
        lastName: string;
        emailPrefix: string;
        source?: string;
      }>;
      hasConfig: boolean;
      availablePatterns: VariationPattern[];
    }>(`/api/clients/${clientId}/sender-name-config`);

    return {
      baseNames: response.baseNames.map(bn => ({
        firstName: bn.firstName,
        lastName: bn.lastName,
        isFounder: bn.isFounder,
      })),
      patterns: response.patterns,
      variations: response.variations.map(v => ({
        firstName: v.firstName,
        lastName: v.lastName,
        emailPrefix: v.emailPrefix,
        baseName: '', // Not stored in preGeneratedSenderNames
        pattern: '', // Not stored
        isFounder: v.source === 'founder',
      })),
      hasConfig: response.hasConfig,
      availablePatterns: response.availablePatterns,
    };
  },

  /**
   * Set sender name (simplified) - auto-generates all prefixes
   * Just provide first/last name and provider, prefixes are auto-generated
   */
  async setSenderName(
    clientId: string,
    firstName: string,
    lastName: string,
    provider: 'entra' | 'google' = 'entra'
  ): Promise<{
    success: boolean;
    baseName: BaseName;
    prefixCount: number;
    prefixes: string[];
    provider: string;
    patterns: string[];
  }> {
    return fetchApi(`/api/clients/${clientId}/set-sender-name`, {
      method: 'POST',
      body: JSON.stringify({
        firstName,
        lastName,
        isFounder: true,
        provider,
      }),
    });
  },

  /**
   * Add a sender name (appends to existing names)
   * First name added becomes Primary, subsequent are secondary
   */
  async addSenderName(
    clientId: string,
    firstName: string,
    lastName: string,
    provider: 'entra' | 'google' = 'entra'
  ): Promise<{
    success: boolean;
    totalNames: number;
    newName: BaseName;
    prefixes: string[];
  }> {
    return fetchApi(`/api/clients/${clientId}/add-sender-name`, {
      method: 'POST',
      body: JSON.stringify({
        firstName,
        lastName,
        provider,
      }),
    });
  },

  /**
   * Delete a sender name by index
   * If primary (index 0) is deleted, next name becomes primary
   */
  async deleteSenderName(
    clientId: string,
    nameIndex: number
  ): Promise<{
    success: boolean;
    removedName: BaseName;
    remainingNames: number;
  }> {
    return fetchApi(`/api/clients/${clientId}/sender-names/${nameIndex}`, {
      method: 'DELETE',
    });
  },
};

// ===== DOMAIN API =====

export const domainApi = {
  /**
   * List domains
   */
  async list(params?: {
    workspaceId?: string;
    clientId?: string;
    status?: string;
    page?: number;
    pageSize?: number;
  }) {
    const searchParams = new URLSearchParams();
    if (params?.workspaceId) searchParams.set('workspace_id', params.workspaceId);
    if (params?.clientId) searchParams.set('client_id', params.clientId);
    if (params?.status) searchParams.set('status', params.status);
    if (params?.page) searchParams.set('page', params.page.toString());
    if (params?.pageSize) searchParams.set('page_size', params.pageSize.toString());

    const query = searchParams.toString();
    const response = await fetchApi<{
      items: Record<string, unknown>[];
      total: number;
      page: number;
      page_size: number;
    }>(`/api/domains${query ? `?${query}` : ''}`);

    return {
      items: response.items.map((item) => toCamelCase<Domain>(item)),
      total: response.total,
      page: response.page,
      pageSize: response.page_size,
    } as PaginatedResponse<Domain>;
  },

  /**
   * Get a single domain by ID
   */
  async get(id: string) {
    const response = await fetchApi<Record<string, unknown>>(`/api/domains/${id}`);
    return toCamelCase<Domain>(response);
  },

  /**
   * Get domain health details
   */
  async getHealth(id: string) {
    return fetchApi<Record<string, unknown>>(`/api/domains/${id}/health`);
  },

  /**
   * Get inboxes for a domain
   */
  async getInboxes(id: string, params?: { page?: number; pageSize?: number }) {
    const searchParams = new URLSearchParams();
    if (params?.page) searchParams.set('page', params.page.toString());
    if (params?.pageSize) searchParams.set('page_size', params.pageSize.toString());

    const query = searchParams.toString();
    const response = await fetchApi<{
      items: Record<string, unknown>[];
      total: number;
      page: number;
      page_size: number;
    }>(`/api/domains/${id}/inboxes${query ? `?${query}` : ''}`);

    return {
      items: response.items.map((item) => toCamelCase<Inbox>(item)),
      total: response.total,
      page: response.page,
      pageSize: response.page_size,
    };
  },

  /**
   * Approve a pending domain
   */
  async approve(id: string) {
    const response = await fetchApi<Record<string, unknown>>(`/api/domains/${id}/approve`, {
      method: 'POST',
    });
    return toCamelCase<Domain>(response);
  },

  /**
   * Generate domains from onboarding data
   */
  async generate(clientId: string, primaryDomain: string, count = 1) {
    return fetchApi<{ message: string; domain?: Record<string, unknown> }>('/api/domains/generate', {
      method: 'POST',
      body: JSON.stringify({
        client_id: clientId,
        primary_domain: primaryDomain,
        count,
      }),
    });
  },
};

// ===== DOMAIN SOURCING API =====

export interface GenerateForClientRequest {
  count?: number;
  ai_provider?: string;
  ai_model?: string;
  preferred_tlds?: { tld: string; priority: number; max_price: number }[];
  fill_package?: boolean;  // If true, auto-calculate count to fill package capacity
}

export interface GeneratedDomainResult {
  id: string;
  domainName: string;
  baseName: string;
  tld: string;
  rationale: string;
  legitimacyScore: number;
}

export interface GenerateForClientResponse {
  clientId: string;
  clientName: string;
  industry: string;
  generatedDomains: GeneratedDomainResult[];
  filteredCount: number;
  totalCandidates: number;
  providerUsed: string;
  modelUsed: string;
  generatedAt: string;
  message?: string;
  packageTarget?: number;
  existingCount?: number;
}

// Domain Approval Types
export interface DomainCandidate {
  id: string;
  domainName: string;
  baseName: string;
  tld: string;
  rationale: string;
  legitimacyScore: number;
  approvalStatus: 'pending' | 'approved' | 'denied';
  createdAt?: string;
  reviewedAt?: string;
}

export interface PendingCandidatesResponse {
  clientId: string;
  candidates: DomainCandidate[];
  totalPending: number;
}

export interface DomainApprovalResult {
  domainId?: string;
  domainName?: string;
  status?: 'approved' | 'denied' | 'removed' | 'available';
  message: string;
  success?: boolean;
}

export interface ApprovedDomainsResponse {
  clientId: string;
  approvedDomains: DomainCandidate[];
  total: number;
}

export interface CanGenerateResponse {
  clientId: string;
  clientName: string;
  canGenerate: boolean;
  generationMode: 'onboarding' | 'pattern_fallback' | 'none';
  hasOnboarding: boolean;
  existingDomainCount: number;
  domainPattern: string | null;
  message: string;
}

export interface GenerationJobResponse {
  jobId: string | null;  // null if skipped (package capacity reached)
  clientId: string;
  clientName: string;
  count: number;
  status: string;  // 'pending', 'processing', 'completed', 'failed', 'skipped'
  createdAt: string | null;
  message: string;
  packageTarget?: number;
  existingCount?: number;
}

export interface GenerationJobStatus {
  jobId: string;
  clientId: string;
  clientName: string;
  count: number;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  errorMessage?: string;
  createdAt?: string;
  startedAt?: string;
  completedAt?: string;
}

export interface ClientJobsResponse {
  clientId: string;
  jobs: GenerationJobStatus[];
  total: number;
}

// Provider Price Info
export interface ProviderPriceInfo {
  available: boolean;
  price: string | null;
  renewalPrice: string | null;
  error: string | null;
}

// Inline Action Types
export interface CheckPriceResponse {
  domainId: string;
  domainName: string;
  available: boolean;
  price: string | null;
  renewalPrice: string | null;
  isPromotional: boolean;
  error: string | null;
  // Dual provider pricing
  porkbun: ProviderPriceInfo | null;
  dynadot: ProviderPriceInfo | null;
  bestProvider: string | null; // "porkbun" or "dynadot"
}

export interface PurchaseSingleResponse {
  domainId: string;
  domainName: string;
  success: boolean;
  orderId: string | null;
  price: string | null;
  error: string | null;
}

// Domain Purchase Job Types (Hypertide Worker)
export interface CreateDomainPurchaseJobRequest {
  domainIds: string[];
  registrar: 'dynadot' | 'porkbun';
}

export interface DomainPurchaseJobResponse {
  jobId: string;
  clientId: string;
  domainCount: number;
  registrar: string;
  status: string;
  createdAt: string;
  message: string;
}

export interface DomainPurchaseJobResult {
  domainId: string;
  domainName: string;
  success: boolean;
  price?: string;
  orderId?: string;
  error?: string;
}

export interface DomainPurchaseJobStatus {
  jobId: string;
  clientId: string;
  status: 'pending' | 'processing' | 'completed' | 'failed' | 'partial';
  registrar: string;
  totalDomains: number;
  successfulCount: number;
  failedCount: number;
  totalCost?: string;
  currentDomain?: string;
  results?: DomainPurchaseJobResult[];
  errors?: string[];
  errorMessage?: string;
  createdAt: string;
  startedAt?: string;
  completedAt?: string;
}

export interface ClientDomainPurchaseJobsResponse {
  clientId: string;
  jobs: DomainPurchaseJobStatus[];
  total: number;
}

export const domainSourcingApi = {
  /**
   * Generate unique domain suggestions for a client using their onboarding data.
   * Automatically filters out duplicates and saves unique domains to DB.
   * Falls back to simple pattern-based generation if HyperTide module unavailable.
   */
  async generateForClient(clientId: string, options?: GenerateForClientRequest): Promise<GenerateForClientResponse> {
    try {
      const response = await fetchApi<Record<string, unknown>>(`/api/domain-sourcing/generate-for-client/${clientId}`, {
        method: 'POST',
        body: JSON.stringify({
          count: options?.count ?? 10,
          ai_provider: options?.ai_provider ?? 'openai',
          ai_model: options?.ai_model ?? 'gpt-4',
          preferred_tlds: options?.preferred_tlds ?? [
            { tld: 'com', priority: 1, max_price: 12.0 },
            { tld: 'io', priority: 2, max_price: 35.0 },
            { tld: 'co', priority: 3, max_price: 25.0 },
          ],
        }),
      });
      return toCamelCase<GenerateForClientResponse>(response);
    } catch (error) {
      // Fallback to simple generation if HyperTide module unavailable (503 error)
      console.warn('HyperTide module unavailable, using simple generation fallback');
      return this.generateSimple(clientId, options?.count ?? 10);
    }
  },

  /**
   * Simple pattern-based domain generation (no HyperTide required).
   * Used as fallback when full AI generation is unavailable.
   */
  async generateSimple(clientId: string, count: number = 10): Promise<GenerateForClientResponse> {
    const response = await fetchApi<{
      generated: Array<{ id: string; domain_name: string; legitimacy_score: number }>;
      message: string;
    }>('/api/infrastructure/generate-domains/simple', {
      method: 'POST',
      body: JSON.stringify({ client_id: clientId, count }),
    });

    // Transform to match GenerateForClientResponse format
    return {
      clientId,
      clientName: '',
      industry: '',
      generatedDomains: response.generated.map(d => {
        const parts = d.domain_name.split('.');
        const tld = parts.length > 1 ? parts.pop()! : '';
        const baseName = parts.join('.');
        return {
          id: d.id,
          domainName: d.domain_name,
          baseName,
          tld,
          legitimacyScore: d.legitimacy_score,
          rationale: 'Pattern-based generation',
        };
      }),
      filteredCount: 0,
      totalCandidates: response.generated.length,
      providerUsed: 'pattern',
      modelUsed: 'simple',
      generatedAt: new Date().toISOString(),
      message: response.message,
    };
  },

  /**
   * Get list of configured registrars for domain search/purchase
   */
  async getRegistrars() {
    return fetchApi<{ registrars: string[]; message: string }>('/api/domain-sourcing/registrars');
  },

  /**
   * Get pending domain candidates for approval.
   * Returns up to `count` domains that haven't been approved or denied.
   * Will generate more if not enough pending candidates exist.
   */
  async getPendingCandidates(clientId: string, count: number = 10): Promise<PendingCandidatesResponse> {
    const response = await fetchApi<Record<string, unknown>>(
      `/api/domain-sourcing/pending-candidates/${clientId}?count=${count}`
    );
    return toCamelCase<PendingCandidatesResponse>(response);
  },

  // =============================================================================
  // DEPRECATED: Approve/Deny workflow removed in simplified domain workflow
  // Domains now go directly from 'available' (generated) to 'purchased'
  // =============================================================================

  /**
   * @deprecated Use getAvailableDomains instead. Approval step removed.
   */
  async approveDomain(domainId: string): Promise<DomainApprovalResult> {
    console.warn('approveDomain is deprecated - domains are now automatically available after generation');
    // Return success without doing anything - domains are already available
    return { success: true, message: 'Domain is already available (approval step removed)' } as DomainApprovalResult;
  },

  /**
   * @deprecated Use removeDomain instead. Domains can be removed if not wanted.
   */
  async denyDomain(domainId: string): Promise<DomainApprovalResult> {
    console.warn('denyDomain is deprecated - use removeDomain instead');
    return this.removeDomain(domainId);
  },

  /**
   * @deprecated No longer needed - domains stay available until purchased or removed.
   */
  async unapproveDomain(domainId: string): Promise<DomainApprovalResult> {
    console.warn('unapproveDomain is deprecated - domains are now always available until purchased');
    return { success: true, message: 'No action needed (approval workflow removed)' } as DomainApprovalResult;
  },

  /**
   * Remove a domain candidate permanently.
   * Use this when you don't want to see a domain suggestion anymore.
   * Cannot remove purchased/active domains.
   */
  async removeDomain(domainId: string): Promise<DomainApprovalResult> {
    const response = await fetchApi<Record<string, unknown>>(
      `/api/domain-sourcing/remove/${domainId}`,
      { method: 'DELETE' }
    );
    return toCamelCase<DomainApprovalResult>(response);
  },

  /**
   * Get all available domain candidates for a client with pricing data.
   * These domains are generated and ready to select for purchase.
   */
  async getAvailableDomains(clientId: string): Promise<ApprovedDomainsResponse> {
    const response = await fetchApi<Record<string, unknown>>(
      `/api/domain-sourcing/available/${clientId}`
    );
    return toCamelCase<ApprovedDomainsResponse>(response);
  },

  /**
   * @deprecated Use getAvailableDomains instead.
   */
  async getApprovedDomains(clientId: string): Promise<ApprovedDomainsResponse> {
    console.warn('getApprovedDomains is deprecated - use getAvailableDomains instead');
    return this.getAvailableDomains(clientId);
  },

  /**
   * Check if domain generation is available for a client.
   * Returns whether generation is possible and which mode would be used.
   */
  async canGenerate(clientId: string): Promise<CanGenerateResponse> {
    const response = await fetchApi<Record<string, unknown>>(
      `/api/domain-sourcing/can-generate/${clientId}`
    );
    return toCamelCase<CanGenerateResponse>(response);
  },

  /**
   * Create a domain generation job for the Claude Code worker.
   * The job will be picked up by the background worker and processed.
   */
  async createGenerationJob(clientId: string, count: number = 10, fillPackage: boolean = true): Promise<GenerationJobResponse> {
    const response = await fetchApi<Record<string, unknown>>(
      `/api/domain-sourcing/jobs/create/${clientId}?count=${count}&fill_package=${fillPackage}`,
      { method: 'POST' }
    );
    return toCamelCase<GenerationJobResponse>(response);
  },

  /**
   * Get the status of a domain generation job.
   */
  async getJobStatus(jobId: string): Promise<GenerationJobStatus> {
    const response = await fetchApi<Record<string, unknown>>(
      `/api/domain-sourcing/jobs/status/${jobId}`
    );
    return toCamelCase<GenerationJobStatus>(response);
  },

  /**
   * Get recent generation jobs for a client.
   */
  async getClientJobs(clientId: string, limit: number = 10): Promise<ClientJobsResponse> {
    const response = await fetchApi<Record<string, unknown>>(
      `/api/domain-sourcing/jobs/client/${clientId}?limit=${limit}`
    );
    return toCamelCase<ClientJobsResponse>(response);
  },

  /**
   * Check price for a single domain (inline action).
   * Caches the price in the database for display in the table.
   */
  async checkPrice(domainId: string): Promise<CheckPriceResponse> {
    const response = await fetchApi<Record<string, unknown>>(
      `/api/domain-sourcing/check-price/${domainId}`,
      { method: 'POST' }
    );
    return toCamelCase<CheckPriceResponse>(response);
  },

  /**
   * Purchase a single approved domain (inline action).
   * Returns 402 if insufficient balance.
   */
  async purchaseSingle(domainId: string): Promise<PurchaseSingleResponse> {
    const response = await fetchApi<Record<string, unknown>>(
      `/api/domain-sourcing/purchase/${domainId}`,
      { method: 'POST' }
    );
    return toCamelCase<PurchaseSingleResponse>(response);
  },

  /**
   * Bulk check prices for multiple domains from both registrars.
   * Stores results in price history and updates cached prices.
   */
  async checkPricesBulk(params: { clientId?: string; domainIds?: string[] }): Promise<{
    results: Array<{
      domainId: string;
      domainName: string;
      porkbunAvailable?: boolean;
      porkbunPrice?: string;
      dynadotAvailable?: boolean;
      dynadotPrice?: string;
      bestPrice?: string;
      bestProvider?: string;
      error?: string;
    }>;
    checkedCount: number;
    availableCount: number;
    errorCount: number;
  }> {
    const response = await fetchApi<Record<string, unknown>>(
      '/api/domain-sourcing/check-prices-bulk',
      {
        method: 'POST',
        body: JSON.stringify({
          client_id: params.clientId,
          domain_ids: params.domainIds,
        }),
      }
    );
    return toCamelCase(response);
  },

  /**
   * Get price history for a domain.
   */
  async getPriceHistory(domainId: string, limit = 30): Promise<{
    domainId: string;
    history: Array<{
      porkbunPrice?: string;
      porkbunAvailable?: boolean;
      dynadotPrice?: string;
      dynadotAvailable?: boolean;
      bestPrice?: string;
      bestProvider?: string;
      checkedAt?: string;
    }>;
    count: number;
  }> {
    const response = await fetchApi<Record<string, unknown>>(
      `/api/domain-sourcing/price-history/${domainId}?limit=${limit}`
    );
    return toCamelCase(response);
  },

  // ===== DOMAIN PURCHASE JOBS (Hypertide Worker) =====

  /**
   * Create a domain purchase job for the Hypertide worker.
   * The job will be picked up by the background worker and processed.
   */
  async createDomainPurchaseJob(
    clientId: string,
    request: CreateDomainPurchaseJobRequest
  ): Promise<DomainPurchaseJobResponse> {
    const response = await fetchApi<Record<string, unknown>>(
      `/api/domain-sourcing/purchase-jobs/create/${clientId}`,
      {
        method: 'POST',
        body: JSON.stringify({
          domain_ids: request.domainIds,
          registrar: request.registrar,
        }),
      }
    );
    return toCamelCase<DomainPurchaseJobResponse>(response);
  },

  /**
   * Get the status of a domain purchase job.
   * Poll this endpoint to track job progress.
   */
  async getDomainPurchaseJobStatus(jobId: string): Promise<DomainPurchaseJobStatus> {
    const response = await fetchApi<Record<string, unknown>>(
      `/api/domain-sourcing/purchase-jobs/${jobId}/status`
    );
    return toCamelCase<DomainPurchaseJobStatus>(response);
  },

  /**
   * Get recent domain purchase jobs for a client.
   */
  async getClientDomainPurchaseJobs(
    clientId: string,
    limit: number = 10
  ): Promise<ClientDomainPurchaseJobsResponse> {
    const response = await fetchApi<Record<string, unknown>>(
      `/api/domain-sourcing/purchase-jobs/client/${clientId}?limit=${limit}`
    );
    return toCamelCase<ClientDomainPurchaseJobsResponse>(response);
  },
};

// ===== INBOX API =====

export const inboxApi = {
  /**
   * List inboxes
   */
  async list(params?: {
    workspaceId?: string;
    clientId?: string;
    domainId?: string;
    status?: string;
    inboxState?: string;
    page?: number;
    pageSize?: number;
  }) {
    const searchParams = new URLSearchParams();
    if (params?.workspaceId) searchParams.set('workspace_id', params.workspaceId);
    if (params?.clientId) searchParams.set('client_id', params.clientId);
    if (params?.domainId) searchParams.set('domain_id', params.domainId);
    if (params?.status) searchParams.set('status', params.status);
    if (params?.inboxState) searchParams.set('inbox_state', params.inboxState);
    if (params?.page) searchParams.set('page', params.page.toString());
    if (params?.pageSize) searchParams.set('page_size', params.pageSize.toString());

    const query = searchParams.toString();
    const response = await fetchApi<{
      items: Record<string, unknown>[];
      total: number;
      page: number;
      page_size: number;
      healthy_count: number;
      warning_count: number;
      critical_count: number;
      dead_count: number;
    }>(`/api/inboxes${query ? `?${query}` : ''}`);

    return {
      items: response.items.map((item) => toCamelCase<Inbox>(item)),
      total: response.total,
      page: response.page,
      pageSize: response.page_size,
      healthyCounts: {
        healthy: response.healthy_count,
        warning: response.warning_count,
        critical: response.critical_count,
        dead: response.dead_count,
      },
    };
  },

  /**
   * Get a single inbox by ID
   */
  async get(id: string) {
    const response = await fetchApi<Record<string, unknown>>(`/api/inboxes/${id}`);
    return toCamelCase<Inbox>(response);
  },

  /**
   * Get inbox health details
   */
  async getHealth(id: string) {
    return fetchApi<Record<string, unknown>>(`/api/inboxes/${id}/health`);
  },

  /**
   * Kill an inbox manually
   */
  async kill(id: string, reason: string, killTrigger = 'manual') {
    return fetchApi<{ message: string; kill_trigger: string }>(`/api/inboxes/${id}/kill`, {
      method: 'POST',
      body: JSON.stringify({ reason, kill_trigger: killTrigger }),
    });
  },

  /**
   * Approve a pending inbox
   */
  async approve(id: string) {
    const response = await fetchApi<Record<string, unknown>>(`/api/inboxes/${id}/approve`, {
      method: 'POST',
    });
    return toCamelCase<Inbox>(response);
  },

  /**
   * Generate inboxes from onboarding data
   */
  async generate(clientId: string, domainId: string, firstNames: string[], count = 1) {
    return fetchApi<{ message: string; inboxes: Record<string, unknown>[] }>('/api/inboxes/generate', {
      method: 'POST',
      body: JSON.stringify({
        client_id: clientId,
        domain_id: domainId,
        first_names: firstNames,
        count,
      }),
    });
  },
};

// ===== CAMPAIGN API =====

export const campaignApi = {
  /**
   * List campaigns
   */
  async list(params?: {
    workspaceId?: string;
    clientId?: string;
    status?: string;
    page?: number;
    pageSize?: number;
  }) {
    const searchParams = new URLSearchParams();
    if (params?.workspaceId) searchParams.set('workspace_id', params.workspaceId);
    if (params?.clientId) searchParams.set('client_id', params.clientId);
    if (params?.status) searchParams.set('status', params.status);
    if (params?.page) searchParams.set('page', params.page.toString());
    if (params?.pageSize) searchParams.set('page_size', params.pageSize.toString());

    const query = searchParams.toString();
    const response = await fetchApi<{
      items: Record<string, unknown>[];
      total: number;
      page: number;
      page_size: number;
      active_count: number;
      paused_count: number;
      completed_count: number;
    }>(`/api/campaigns${query ? `?${query}` : ''}`);

    return {
      items: response.items.map((item) => toCamelCase<Campaign>(item)),
      total: response.total,
      page: response.page,
      pageSize: response.page_size,
      statusCounts: {
        active: response.active_count,
        paused: response.paused_count,
        completed: response.completed_count,
      },
    };
  },

  /**
   * Get a single campaign by ID
   */
  async get(id: string) {
    const response = await fetchApi<Record<string, unknown>>(`/api/campaigns/${id}`);
    return toCamelCase<Campaign>(response);
  },

  /**
   * Get campaign metrics
   */
  async getMetrics(id: string) {
    return fetchApi<Record<string, unknown>>(`/api/campaigns/${id}/metrics`);
  },

  /**
   * Create a new campaign
   */
  async create(data: {
    workspaceId: string;
    campaignName: string;
    industry?: string;
    segment?: string;
    angle?: string;
    ideaId?: string;
  }) {
    const response = await fetchApi<Record<string, unknown>>('/api/campaigns', {
      method: 'POST',
      body: JSON.stringify(toSnakeCase(data)),
    });
    return toCamelCase<Campaign>(response);
  },

  /**
   * Run a campaign
   */
  async run(id: string) {
    const response = await fetchApi<Record<string, unknown>>(`/api/campaigns/${id}/run`, {
      method: 'POST',
    });
    return toCamelCase<Campaign>(response);
  },

  /**
   * Pause a campaign
   */
  async pause(id: string) {
    const response = await fetchApi<Record<string, unknown>>(`/api/campaigns/${id}/pause`, {
      method: 'POST',
    });
    return toCamelCase<Campaign>(response);
  },

  /**
   * Get campaign events
   */
  async getEvents(
    id: string,
    params?: { eventType?: string; page?: number; pageSize?: number }
  ) {
    const searchParams = new URLSearchParams();
    if (params?.eventType) searchParams.set('event_type', params.eventType);
    if (params?.page) searchParams.set('page', params.page.toString());
    if (params?.pageSize) searchParams.set('page_size', params.pageSize.toString());

    const query = searchParams.toString();
    return fetchApi<{
      items: Record<string, unknown>[];
      total: number;
      page: number;
      page_size: number;
    }>(`/api/campaigns/${id}/events${query ? `?${query}` : ''}`);
  },
};

// ===== LEAD API =====

export const leadApi = {
  /**
   * List leads
   */
  async list(params?: {
    campaignId?: string;
    status?: string;
    search?: string;
    page?: number;
    pageSize?: number;
  }) {
    const searchParams = new URLSearchParams();
    if (params?.campaignId) searchParams.set('campaign_id', params.campaignId);
    if (params?.status) searchParams.set('status', params.status);
    if (params?.search) searchParams.set('search', params.search);
    if (params?.page) searchParams.set('page', params.page.toString());
    if (params?.pageSize) searchParams.set('page_size', params.pageSize.toString());

    const query = searchParams.toString();
    const response = await fetchApi<{
      items: Record<string, unknown>[];
      total: number;
      page: number;
      page_size: number;
      queued_count: number;
      contacted_count: number;
      replied_count: number;
      bounced_count: number;
      unsubscribed_count: number;
    }>(`/api/leads${query ? `?${query}` : ''}`);

    return {
      items: response.items.map((item) => toCamelCase<Lead>(item)),
      total: response.total,
      page: response.page,
      pageSize: response.page_size,
      statusCounts: {
        queued: response.queued_count,
        contacted: response.contacted_count,
        replied: response.replied_count,
        bounced: response.bounced_count,
        unsubscribed: response.unsubscribed_count,
      },
    };
  },

  /**
   * Get a single lead by ID
   */
  async get(id: string) {
    const response = await fetchApi<Record<string, unknown>>(`/api/leads/${id}`);
    return toCamelCase<Lead>(response);
  },

  /**
   * Create a single lead
   */
  async create(data: {
    campaignId: string;
    email: string;
    firstName?: string;
    lastName?: string;
    company?: string;
    title?: string;
    source?: string;
  }) {
    const response = await fetchApi<Record<string, unknown>>('/api/leads', {
      method: 'POST',
      body: JSON.stringify(toSnakeCase(data)),
    });
    return toCamelCase<Lead>(response);
  },

  /**
   * Bulk create leads
   */
  async bulkCreate(
    campaignId: string,
    leads: Array<{
      email: string;
      firstName?: string;
      lastName?: string;
      company?: string;
      title?: string;
    }>,
    source = 'csv_upload'
  ) {
    return fetchApi<{
      total_uploaded: number;
      successful: number;
      failed: number;
      duplicates_skipped: number;
      errors?: Array<{ email: string; error: string }>;
    }>('/api/leads/bulk', {
      method: 'POST',
      body: JSON.stringify({
        campaign_id: campaignId,
        leads,
        source,
      }),
    });
  },

  /**
   * Update a lead
   */
  async update(
    id: string,
    data: Partial<{
      firstName: string;
      lastName: string;
      company: string;
      title: string;
      status: string;
      notes: string;
    }>
  ) {
    const response = await fetchApi<Record<string, unknown>>(`/api/leads/${id}`, {
      method: 'PUT',
      body: JSON.stringify(toSnakeCase(data)),
    });
    return toCamelCase<Lead>(response);
  },

  /**
   * Update lead status
   */
  async updateStatus(id: string, status: string, contactedAt?: Date) {
    const response = await fetchApi<Record<string, unknown>>(`/api/leads/${id}/status`, {
      method: 'PUT',
      body: JSON.stringify({
        status,
        contacted_at: contactedAt?.toISOString(),
      }),
    });
    return toCamelCase<Lead>(response);
  },

  /**
   * Delete a lead
   */
  async delete(id: string) {
    return fetchApi<{ message: string }>(`/api/leads/${id}`, {
      method: 'DELETE',
    });
  },

  /**
   * Get leads for a campaign
   */
  async getByCampaign(campaignId: string, params?: { status?: string; page?: number; pageSize?: number }) {
    const searchParams = new URLSearchParams();
    if (params?.status) searchParams.set('status', params.status);
    if (params?.page) searchParams.set('page', params.page.toString());
    if (params?.pageSize) searchParams.set('page_size', params.pageSize.toString());

    const query = searchParams.toString();
    const response = await fetchApi<{
      items: Record<string, unknown>[];
      total: number;
      page: number;
      page_size: number;
      queued_count: number;
      contacted_count: number;
      replied_count: number;
      bounced_count: number;
      unsubscribed_count: number;
    }>(`/api/leads/campaign/${campaignId}${query ? `?${query}` : ''}`);

    return {
      items: response.items.map((item) => toCamelCase<Lead>(item)),
      total: response.total,
      page: response.page,
      pageSize: response.page_size,
      statusCounts: {
        queued: response.queued_count,
        contacted: response.contacted_count,
        replied: response.replied_count,
        bounced: response.bounced_count,
        unsubscribed: response.unsubscribed_count,
      },
    };
  },
};

// ===== ONBOARDING API =====

export interface ClientSegment {
  id?: string;
  segmentName: string;
  revenuePercentage: number;
  uniqueCharacteristics?: string;
  painPoints?: string;
  buyingTriggers?: string;
}

export interface ClientPersona {
  id?: string;
  jobTitle: string;
  primarySegment?: string;
  seniorityLevel?: string;
  painBeforeBuying?: string;
  ahaMoment?: string;
  objections?: string;
}

export interface OnboardingSubmission {
  id: string;
  clientId?: string;

  // Section 1: Foundation
  companyName: string;
  website?: string;
  contactName?: string;
  contactEmail?: string;
  employeeCount?: string;
  fundingStage?: string;
  hqLocation?: string;

  // Section 2: Offering
  coreProduct?: string;
  targetCustomer?: string;
  acv?: string;
  salesCycleLength?: string;

  // Section 3: Market Signals
  signals: string[];

  // Section 4: Audience
  jobTitles: string[];
  segments: ClientSegment[];
  personas: ClientPersona[];

  // Section 5: Process
  outboundTools: string[];
  crm?: string;

  // Section 6: Messaging
  customerVoice?: string;
  roiResults?: string;
  toneStyle?: string;

  // Section 7: Goals
  primaryGtmObjective?: string;
  successMetrics: string[];
  successDefinition?: string;

  // Metadata
  submissionStatus: string;
  submittedAt?: string;
  createdAt: string;
  updatedAt?: string;
}

export interface OnboardingSubmissionList {
  clientId: string;
  submissions: OnboardingSubmission[];
  total: number;
}

export interface ContactNamesResponse {
  clientId: string;
  contactNames: string[];
  jobTitles: string[];
}

export const onboardingApi = {
  /**
   * Get all onboarding submissions for a client
   */
  async getSubmissions(clientId: string): Promise<OnboardingSubmissionList> {
    const response = await fetchApi<Record<string, unknown>>(
      `/api/onboarding/clients/${clientId}/submissions`
    );
    return toCamelCase<OnboardingSubmissionList>(response);
  },

  /**
   * Get a single onboarding submission by ID
   */
  async getSubmission(submissionId: string): Promise<OnboardingSubmission> {
    const response = await fetchApi<Record<string, unknown>>(
      `/api/onboarding/submissions/${submissionId}`
    );
    return toCamelCase<OnboardingSubmission>(response);
  },

  /**
   * Update an onboarding submission
   */
  async updateSubmission(
    submissionId: string,
    data: Partial<Omit<OnboardingSubmission, 'id' | 'clientId' | 'createdAt' | 'updatedAt' | 'segments' | 'personas'>>
  ): Promise<OnboardingSubmission> {
    const response = await fetchApi<Record<string, unknown>>(
      `/api/onboarding/submissions/${submissionId}`,
      {
        method: 'PUT',
        body: JSON.stringify(toSnakeCase(data)),
      }
    );
    return toCamelCase<OnboardingSubmission>(response);
  },

  /**
   * Get contact names for a client (for inbox generation)
   */
  async getContactNames(clientId: string): Promise<ContactNamesResponse> {
    const response = await fetchApi<Record<string, unknown>>(
      `/api/onboarding/clients/${clientId}/contact-names`
    );
    return toCamelCase<ContactNamesResponse>(response);
  },
};

// ===== STRATEGY API =====

export interface StrategyJob {
  jobId: string;
  clientId: string;
  clientName?: string;
  submissionId?: string;
  status: 'pending' | 'processing' | 'review' | 'completed' | 'failed';
  generationRound: number;
  errorMessage?: string;
  createdAt: string;
  startedAt?: string;
  completedAt?: string;
}

export interface StrategySuggestion {
  id: string;
  jobId: string;
  clientId: string;
  strategyId?: string;
  variantNumber: number;
  subjectLine: string;
  emailBody: string;
  editedSubjectLine?: string;
  editedEmailBody?: string;
  score?: number;
  rationale?: string;
  usedVariables?: string[];
  missingVariables?: string[];
  campaignType?: string;
  status: 'pending' | 'approved' | 'denied' | 'revision_requested';
  humanComment?: string;
  reviewedBy?: string;
  reviewedAt?: string;
  pushedToEmailbison?: boolean;
  pushedAt?: string;
  originalSuggestionId?: string;
  generationRound: number;
  createdAt: string;
}

export interface Strategy {
  id: string;
  clientId: string;
  name: string;
  description?: string;
  status: 'draft' | 'active' | 'paused' | 'completed';
  submissionId?: string;
  submissionCreatedAt?: string;
  emailbisonCampaignId?: string;
  suggestionCount?: number;
  createdAt: string;
  updatedAt: string;
}

export interface StrategyJobCreate {
  submissionId?: string;
}

export interface StrategyJobResponse {
  jobId: string;
  clientId: string;
  clientName: string;
  submissionId?: string;
  status: string;
  generationRound: number;
  createdAt: string;
  message: string;
}

export interface GenerationPhase {
  id: string;
  type: 'scaffold' | 'campaign_copy';
  number: number | null;
  campaignDocumentId: string | null;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  errorMessage?: string;
  startedAt?: string;
  completedAt?: string;
}

export interface JobPhasesResponse {
  jobId: string;
  clientId: string;
  clientName: string;
  jobStatus: string;
  jobType: string;
  cycleId?: string;
  errorMessage?: string;
  createdAt?: string;
  startedAt?: string;
  completedAt?: string;
  phases: GenerationPhase[];
  progress: {
    totalPhases: number;
    completedPhases: number;
    failedPhases: number;
    processingPhases: number;
    percent: number;
    estimatedRemainingSeconds: number;
  };
}

export interface ClientSuggestionsResponse {
  clientId: string;
  suggestions: StrategySuggestion[];
  pendingCount: number;
  approvedCount: number;
  deniedCount: number;
  revisionCount: number;
  total: number;
}

export interface SuggestionReviewRequest {
  action: 'approve' | 'deny' | 'revision_requested';
  comment?: string;
  reviewer?: string;
}

export interface RevisionRequest {
  revisionId: string;
  jobId: string;
  clientId: string;
  variantId: string;
  instruction: string;
  status: string;
  message?: string;
  // Fields from GET endpoint
  subjectLine?: string;
  processed?: boolean;
  createdAt?: string;
}

export interface ClientRevisionsResponse {
  clientId: string;
  revisions: RevisionRequest[];
  total: number;
}

// ===== SEQUENCE TYPES (4-Email Campaigns) =====

export interface SequenceEmail {
  position: 1 | 2 | 3 | 4;
  waitDays: number;
  subjectLine: string | null;  // null for threaded emails
  emailBody: string;
  editedSubjectLine?: string;
  editedEmailBody?: string;
  threadReply: boolean;
  strategy?: string;  // custom_signal, creative_ideas, etc.
  valueProp?: 'save_time' | 'save_money' | 'make_money' | null;
  wordCount?: number;
}

// ===== CAMPAIGN BATCH & CYCLE TYPES =====

// Campaign angle types for the 4-campaign batch generation
export type CampaignAngle = 'custom_signal' | 'persona_pain' | 'case_study' | 'risk_efficiency';
export type OpenerPattern = 'status_pressure' | 'efficiency_leverage' | 'risk_based' | 'binary' | 'redirect';

// Strategy considerations - maps onboarding inputs to campaign targeting
export interface CampaignMapping {
  campaignIndex: number;
  campaignId?: string;
  angle: CampaignAngle;
  targetPersona?: string;
  targetSegment?: string;
  reasoning: string;
  influencedBy: string[];  // e.g., ['target_customer', 'job_titles', 'segments']
}

export interface StrategyConsiderations {
  inputsUsed: string[];  // Onboarding fields used: ['target_customer', 'job_titles', 'roi_results']
  campaignMappings: CampaignMapping[];
}

// Campaign cycles for tracking progressive scaling (4 → 8 → 12 → 16 → 20 → 24)
export interface CampaignCycle {
  id: string;
  clientId: string;
  strategyId?: string;
  cycleNumber: number;  // 1, 2, 3, 4, 5, 6...
  cycleName?: string;  // e.g., "Pre-Launch", "Cycle 1", "Infra Refresh"
  startDate?: string;
  endDate?: string;
  durationDays: number;
  targetCampaigns: number;  // Target number of campaigns for this cycle
  actualCampaigns: number;
  status: 'draft' | 'planned' | 'active' | 'completed';
  notes?: string;
  createdAt: string;
  updatedAt: string;
}

// Performance metrics synced from EmailBison
export interface CampaignPerformanceMetrics {
  emailsSent: number;
  opens: number;
  openRate: number;
  replies: number;
  replyRate: number;
  bounces: number;
  bounceRate: number;
  unsubscribes: number;
  lastSyncedAt?: string;
}

export interface CampaignSequence {
  id: string;
  jobId: string;
  clientId: string;
  strategyId?: string;
  campaignName: string;  // Email 1 subject
  campaignType?: 'custom_signal' | 'creative_ideas' | 'whole_offer' | 'fallback';
  status: 'pending' | 'approved' | 'denied' | 'revision_requested' | 'spintax_pending' | 'spintaxed' | 'sent';
  score?: number;
  valuePropRotation?: ('save_time' | 'save_money' | 'make_money')[];
  emails: SequenceEmail[];
  spintaxedEmails?: SequenceEmail[];  // Populated after spintax processing
  usedVariables?: string[];
  missingVariables?: string[];
  rationale?: string;
  totalWordCount?: number;
  humanComment?: string;
  reviewedBy?: string;
  reviewedAt?: string;
  pushedToEmailbison?: boolean;
  pushedAt?: string;
  generationRound: number;
  createdAt: string;

  // Batch generation differentiation
  campaignAngle?: CampaignAngle;  // custom_signal, persona_pain, case_study, risk_efficiency
  targetPersona?: string;  // Which persona this campaign targets
  targetSegment?: string;  // Which segment this campaign targets
  openerPattern?: OpenerPattern;  // Which Poke the Bear pattern was used

  // Versioning and lineage (campaigns evolve across cycles)
  cycleId?: string;  // Which cycle this campaign belongs to
  campaignVersion?: number;  // v1, v2, v3... (increments on regeneration)
  lineageId?: string;  // Groups campaigns that evolve from each other
  previousVersionId?: string;  // Links to previous version of this campaign

  // Performance tracking from EmailBison
  emailbisonCampaignId?: string;
  performanceMetrics?: CampaignPerformanceMetrics;
  lastPerformanceSync?: string;

  // Strategy considerations (populated from job)
  strategyConsiderations?: StrategyConsiderations;
}

export interface ClientSequencesResponse {
  clientId: string;
  sequences: CampaignSequence[];
  pendingCount: number;
  approvedCount: number;
  deniedCount: number;
  revisionCount: number;
  total: number;
}

export interface SequenceReviewRequest {
  action: 'approve' | 'deny';
  comment?: string;
  reviewer?: string;
}

export interface SequenceEmailEditRequest {
  subjectLine?: string;  // Only for position 1 and 3
  emailBody: string;
}

export interface SequenceRevisionRequest {
  emailPosition: number;  // 1-4 for specific email, 0 for whole sequence
  instruction: string;
  scope: 'single' | 'subsequent' | 'all';
}

export const strategyApi = {
  // ===== STRATEGY MANAGEMENT =====

  /**
   * Create a new strategy for a client
   */
  async createStrategy(clientId: string, name: string, description?: string): Promise<Strategy> {
    const response = await fetchApi<Record<string, unknown>>(
      `/api/strategy/strategies/${clientId}`,
      {
        method: 'POST',
        body: JSON.stringify({ name, description }),
      }
    );
    return toCamelCase<Strategy>(response);
  },

  /**
   * Get all strategies for a client
   */
  async getStrategies(clientId: string): Promise<{ clientId: string; strategies: Strategy[]; total: number }> {
    const response = await fetchApi<Record<string, unknown>>(
      `/api/strategy/strategies/${clientId}`
    );
    return toCamelCase<{ clientId: string; strategies: Strategy[]; total: number }>(response);
  },

  /**
   * Update a strategy
   */
  async updateStrategy(
    strategyId: string,
    data: { name?: string; description?: string; status?: string }
  ): Promise<Strategy> {
    const response = await fetchApi<Record<string, unknown>>(
      `/api/strategy/strategies/${strategyId}`,
      {
        method: 'PUT',
        body: JSON.stringify(toSnakeCase(data)),
      }
    );
    return toCamelCase<Strategy>(response);
  },

  /**
   * Delete a strategy
   */
  async deleteStrategy(strategyId: string): Promise<{ message: string }> {
    return fetchApi<{ message: string }>(
      `/api/strategy/strategies/${strategyId}`,
      { method: 'DELETE' }
    );
  },

  // ===== GENERATION JOBS =====

  /**
   * Create a new strategy generation job for Claude Code worker
   */
  async createJob(clientId: string, submissionId?: string, strategyId?: string): Promise<StrategyJobResponse> {
    const body: Record<string, string> = {};
    if (submissionId) body.submission_id = submissionId;
    if (strategyId) body.strategy_id = strategyId;
    const response = await fetchApi<Record<string, unknown>>(
      `/api/strategy/jobs/${clientId}`,
      {
        method: 'POST',
        body: JSON.stringify(body),
      }
    );
    return toCamelCase<StrategyJobResponse>(response);
  },

  /**
   * Get the status of a strategy generation job
   */
  async getJobStatus(jobId: string): Promise<StrategyJob> {
    const response = await fetchApi<Record<string, unknown>>(
      `/api/strategy/jobs/${jobId}/status`
    );
    return toCamelCase<StrategyJob>(response);
  },

  /**
   * Get detailed phase status for a phased generation job
   */
  async getJobPhases(jobId: string): Promise<JobPhasesResponse> {
    const response = await fetchApi<Record<string, unknown>>(
      `/api/strategy/jobs/${jobId}/phases`
    );
    return toCamelCase<JobPhasesResponse>(response);
  },

  /**
   * Get recent strategy generation jobs for a client
   */
  async getClientJobs(clientId: string, limit: number = 10): Promise<{ clientId: string; jobs: StrategyJob[]; total: number }> {
    const response = await fetchApi<Record<string, unknown>>(
      `/api/strategy/jobs/client/${clientId}?limit=${limit}`
    );
    return toCamelCase<{ clientId: string; jobs: StrategyJob[]; total: number }>(response);
  },

  /**
   * Get strategy suggestions for a client
   */
  async getSuggestions(
    clientId: string,
    params?: {
      status?: string;
      limit?: number;
      strategyId?: string;
      sortBy?: 'score' | 'created_at' | 'status';
      sortOrder?: 'asc' | 'desc';
    }
  ): Promise<ClientSuggestionsResponse> {
    const searchParams = new URLSearchParams();
    if (params?.status) searchParams.set('status', params.status);
    if (params?.limit) searchParams.set('limit', params.limit.toString());
    if (params?.strategyId) searchParams.set('strategy_id', params.strategyId);
    if (params?.sortBy) searchParams.set('sort_by', params.sortBy);
    if (params?.sortOrder) searchParams.set('sort_order', params.sortOrder);

    const query = searchParams.toString();
    const response = await fetchApi<Record<string, unknown>>(
      `/api/strategy/suggestions/${clientId}${query ? `?${query}` : ''}`
    );
    return toCamelCase<ClientSuggestionsResponse>(response);
  },

  /**
   * Edit a suggestion's content (subject line and/or email body)
   */
  async editSuggestion(
    suggestionId: string,
    data: { subjectLine: string; emailBody: string }
  ): Promise<StrategySuggestion> {
    const response = await fetchApi<Record<string, unknown>>(
      `/api/strategy/suggestions/${suggestionId}/edit`,
      {
        method: 'PUT',
        body: JSON.stringify(toSnakeCase(data)),
      }
    );
    return toCamelCase<StrategySuggestion>(response);
  },

  /**
   * Push an approved suggestion to EmailBison via Prefect flow
   */
  async pushToEmailBison(suggestionId: string): Promise<{ flowRunId: string; status: string }> {
    const response = await fetchApi<Record<string, unknown>>(
      `/api/strategy/suggestions/${suggestionId}/push-to-emailbison`,
      { method: 'POST' }
    );
    return toCamelCase<{ flowRunId: string; status: string }>(response);
  },

  /**
   * Get suggestions for a specific job
   */
  async getJobSuggestions(jobId: string): Promise<{ jobId: string; suggestions: StrategySuggestion[]; total: number }> {
    const response = await fetchApi<Record<string, unknown>>(
      `/api/strategy/suggestions/job/${jobId}`
    );
    return toCamelCase<{ jobId: string; suggestions: StrategySuggestion[]; total: number }>(response);
  },

  /**
   * Review a strategy suggestion - approve, deny, or request revision
   */
  async reviewSuggestion(
    suggestionId: string,
    request: SuggestionReviewRequest
  ): Promise<{ suggestionId: string; subjectLine: string; status: string; message: string }> {
    const response = await fetchApi<Record<string, unknown>>(
      `/api/strategy/suggestions/${suggestionId}/review`,
      {
        method: 'POST',
        body: JSON.stringify(toSnakeCase(request as unknown as Record<string, unknown>)),
      }
    );
    return toCamelCase<{ suggestionId: string; subjectLine: string; status: string; message: string }>(response);
  },

  /**
   * Request a revision for a suggestion with specific instructions
   */
  async requestRevision(
    suggestionId: string,
    instruction: string
  ): Promise<RevisionRequest> {
    const response = await fetchApi<Record<string, unknown>>(
      `/api/strategy/suggestions/${suggestionId}/revision`,
      {
        method: 'POST',
        body: JSON.stringify({ instruction }),
      }
    );
    return toCamelCase<RevisionRequest>(response);
  },

  /**
   * Get revision requests for a client
   */
  async getClientRevisions(
    clientId: string,
    processed?: boolean
  ): Promise<ClientRevisionsResponse> {
    const searchParams = new URLSearchParams();
    if (processed !== undefined) searchParams.set('processed', processed.toString());

    const query = searchParams.toString();
    const response = await fetchApi<Record<string, unknown>>(
      `/api/strategy/revisions/${clientId}${query ? `?${query}` : ''}`
    );
    return toCamelCase<ClientRevisionsResponse>(response);
  },

  // ===== SEQUENCE ENDPOINTS (4-Email Campaigns) =====

  /**
   * Get all 4-email campaign sequences for a client
   */
  async getSequences(
    clientId: string,
    params?: {
      status?: string;
      strategyId?: string;
      sort?: 'score' | 'created_at' | 'status';
      order?: 'asc' | 'desc';
      limit?: number;
    }
  ): Promise<ClientSequencesResponse> {
    const searchParams = new URLSearchParams();
    if (params?.status) searchParams.set('status', params.status);
    if (params?.strategyId) searchParams.set('strategy_id', params.strategyId);
    if (params?.sort) searchParams.set('sort', params.sort);
    if (params?.order) searchParams.set('order', params.order);
    if (params?.limit) searchParams.set('limit', params.limit.toString());

    const query = searchParams.toString();
    const response = await fetchApi<Record<string, unknown>>(
      `/api/strategy/sequences/${clientId}${query ? `?${query}` : ''}`
    );
    return toCamelCase<ClientSequencesResponse>(response);
  },

  /**
   * Get a single sequence by ID
   */
  async getSequence(clientId: string, sequenceId: string): Promise<CampaignSequence> {
    const response = await fetchApi<Record<string, unknown>>(
      `/api/strategy/sequences/${clientId}/${sequenceId}`
    );
    return toCamelCase<CampaignSequence>(response);
  },

  /**
   * Review a sequence - approve or deny
   */
  async reviewSequence(
    sequenceId: string,
    request: SequenceReviewRequest
  ): Promise<{ sequenceId: string; campaignName: string; status: string; message: string }> {
    const response = await fetchApi<Record<string, unknown>>(
      `/api/strategy/sequences/${sequenceId}`,
      {
        method: 'PATCH',
        body: JSON.stringify(toSnakeCase(request as unknown as Record<string, unknown>)),
      }
    );
    return toCamelCase<{ sequenceId: string; campaignName: string; status: string; message: string }>(response);
  },

  /**
   * Edit a specific email within a sequence
   */
  async editSequenceEmail(
    sequenceId: string,
    position: number,
    data: SequenceEmailEditRequest
  ): Promise<{ sequenceId: string; position: number; message: string }> {
    const response = await fetchApi<Record<string, unknown>>(
      `/api/strategy/sequences/${sequenceId}/emails/${position}`,
      {
        method: 'PATCH',
        body: JSON.stringify(toSnakeCase(data as unknown as Record<string, unknown>)),
      }
    );
    return toCamelCase<{ sequenceId: string; position: number; message: string }>(response);
  },

  /**
   * Request revision for a specific email or entire sequence
   */
  async requestSequenceRevision(
    sequenceId: string,
    request: SequenceRevisionRequest
  ): Promise<{
    revisionId: string;
    jobId: string;
    sequenceId: string;
    emailPosition: number;
    scope: string;
    status: string;
    message: string;
  }> {
    const response = await fetchApi<Record<string, unknown>>(
      `/api/strategy/sequences/${sequenceId}/revision`,
      {
        method: 'POST',
        body: JSON.stringify(toSnakeCase(request as unknown as Record<string, unknown>)),
      }
    );
    return toCamelCase<{
      revisionId: string;
      jobId: string;
      sequenceId: string;
      emailPosition: number;
      scope: string;
      status: string;
      message: string;
    }>(response);
  },

  /**
   * Create a spintax processing job for an approved sequence
   */
  async createSpintaxJob(sequenceId: string): Promise<{
    jobId: string;
    sequenceId: string;
    clientId: string;
    status: string;
    createdAt: string;
  }> {
    const response = await fetchApi<Record<string, unknown>>(
      `/api/strategy/sequences/${sequenceId}/spintax`,
      { method: 'POST' }
    );
    return toCamelCase<{
      jobId: string;
      sequenceId: string;
      clientId: string;
      status: string;
      createdAt: string;
    }>(response);
  },

  /**
   * Get spintax job status for polling
   */
  async getSpintaxJobStatus(jobId: string): Promise<{
    jobId: string;
    sequenceId: string;
    clientId: string;
    status: string;
    errorMessage?: string;
    createdAt: string;
    startedAt?: string;
    completedAt?: string;
  }> {
    const response = await fetchApi<Record<string, unknown>>(
      `/api/strategy/spintax-jobs/${jobId}/status`
    );
    return toCamelCase<{
      jobId: string;
      sequenceId: string;
      clientId: string;
      status: string;
      errorMessage?: string;
      createdAt: string;
      startedAt?: string;
      completedAt?: string;
    }>(response);
  },

  /**
   * Push a spintaxed sequence to EmailBison
   */
  async pushSequenceToEmailBison(sequenceId: string): Promise<{
    sequenceId: string;
    clientId: string;
    emailbisonCampaignId: string;
    campaignName: string;
    emailsPushed: number;
    stepsCompleted: string[];
    status: string;
    message: string;
  }> {
    const response = await fetchApi<Record<string, unknown>>(
      `/api/strategy/sequences/${sequenceId}/push-to-emailbison`,
      { method: 'POST' }
    );
    return toCamelCase<{
      sequenceId: string;
      clientId: string;
      emailbisonCampaignId: string;
      campaignName: string;
      emailsPushed: number;
      stepsCompleted: string[];
      status: string;
      message: string;
    }>(response);
  },

  // ===== CAMPAIGN CYCLES =====

  /**
   * Get all cycles for a client, optionally filtered by strategy
   */
  async getCycles(clientId: string, strategyId?: string): Promise<{ cycles: CampaignCycle[]; total: number }> {
    const query = strategyId ? `?strategy_id=${strategyId}` : '';
    const response = await fetchApi<Record<string, unknown>>(
      `/api/strategy/cycles/${clientId}${query}`
    );
    return toCamelCase<{ cycles: CampaignCycle[]; total: number }>(response);
  },

  /**
   * Get a specific cycle by ID
   */
  async getCycle(cycleId: string): Promise<CampaignCycle> {
    const response = await fetchApi<Record<string, unknown>>(
      `/api/strategy/cycles/detail/${cycleId}`
    );
    return toCamelCase<CampaignCycle>(response);
  },

  /**
   * Create a new cycle for a client
   */
  async createCycle(
    clientId: string,
    data: {
      cycleName?: string;
      strategyId?: string;
      cycleNumber: number;
      targetCampaigns: number;
      durationDays?: number;
      startDate?: string;
      notes?: string;
    }
  ): Promise<CampaignCycle> {
    const response = await fetchApi<Record<string, unknown>>(
      `/api/strategy/cycles/${clientId}`,
      {
        method: 'POST',
        body: JSON.stringify(toSnakeCase(data)),
      }
    );
    return toCamelCase<CampaignCycle>(response);
  },

  /**
   * Update a cycle
   */
  async updateCycle(
    cycleId: string,
    data: Partial<{
      cycleName: string;
      status: 'planned' | 'active' | 'completed';
      targetCampaigns: number;
      startDate: string;
      endDate: string;
      notes: string;
    }>
  ): Promise<CampaignCycle> {
    const response = await fetchApi<Record<string, unknown>>(
      `/api/strategy/cycles/detail/${cycleId}`,
      {
        method: 'PUT',
        body: JSON.stringify(toSnakeCase(data)),
      }
    );
    return toCamelCase<CampaignCycle>(response);
  },

  /**
   * Delete a cycle
   */
  async deleteCycle(cycleId: string): Promise<{ message: string }> {
    return fetchApi<{ message: string }>(
      `/api/strategy/cycles/detail/${cycleId}`,
      { method: 'DELETE' }
    );
  },

  /**
   * Get campaigns for a specific cycle
   */
  async getCampaignsForCycle(cycleId: string): Promise<{ campaigns: CampaignSequence[]; total: number }> {
    const response = await fetchApi<Record<string, unknown>>(
      `/api/strategy/cycles/${cycleId}/campaigns`
    );
    return toCamelCase<{ campaigns: CampaignSequence[]; total: number }>(response);
  },

  /**
   * Generate campaigns for an existing cycle
   * Use this when a cycle exists but needs its campaigns generated/populated
   */
  async generateCycleCampaigns(
    cycleId: string,
    submissionId?: string
  ): Promise<{
    jobId: string;
    clientId: string;
    cycleId: string;
    status: string;
    message: string;
  }> {
    const body: Record<string, string> = {};
    if (submissionId) body.submission_id = submissionId;
    const response = await fetchApi<Record<string, unknown>>(
      `/api/strategy/cycles/${cycleId}/generate`,
      {
        method: 'POST',
        body: JSON.stringify(body),
      }
    );
    return toCamelCase<{
      jobId: string;
      clientId: string;
      cycleId: string;
      status: string;
      message: string;
    }>(response);
  },
};

// ===== HEALTH API =====

export const healthApi = {
  /**
   * Get health overview for a client
   */
  async getOverview(clientId: string) {
    const response = await fetchApi<Record<string, unknown>>(`/api/health/overview/${clientId}`);
    return toCamelCase<HealthOverview>(response);
  },

  /**
   * Get full health dashboard
   */
  async getDashboard(clientId: string) {
    return fetchApi<Record<string, unknown>>(`/api/health/dashboard/${clientId}`);
  },

  /**
   * Get kill trigger statistics
   */
  async getKillStats(workspaceId: string) {
    return fetchApi<Record<string, unknown>>(`/api/health/kill-stats/${workspaceId}`);
  },

  /**
   * Get active alerts
   */
  async getAlerts(params?: {
    clientId?: string;
    workspaceId?: string;
    severity?: string;
    limit?: number;
  }) {
    const searchParams = new URLSearchParams();
    if (params?.clientId) searchParams.set('client_id', params.clientId);
    if (params?.workspaceId) searchParams.set('workspace_id', params.workspaceId);
    if (params?.severity) searchParams.set('severity', params.severity);
    if (params?.limit) searchParams.set('limit', params.limit.toString());

    const query = searchParams.toString();
    const response = await fetchApi<{
      items: Record<string, unknown>[];
      total: number;
      critical_count: number;
      warning_count: number;
    }>(`/api/health/alerts${query ? `?${query}` : ''}`);

    return {
      items: response.items.map((item) => toCamelCase<Alert>(item)),
      total: response.total,
      criticalCount: response.critical_count,
      warningCount: response.warning_count,
    };
  },

  /**
   * Get full dashboard data for all health containers in a single call
   */
  async getFullDashboard(clientId: string) {
    const response = await fetchApi<Record<string, unknown>>(`/api/health/full-dashboard/${clientId}`);
    return toCamelCase<{
      overallSummary: {
        clientId: string;
        healthScore: number;
        status: string;
        statusMessage: string;
        totalDomains: number;
        liveDomains: number;
        flaggedDomains: number;
        deadDomains: number;
        totalInboxes: number;
        liveInboxes: number;
        deadInboxes: number;
        warmingInboxes: number;
        pendingKillTriggers: number;
        activeAlerts: number;
        lastRefresh: string;
      };
      killTriggers: Array<{
        id: string;
        inboxId: string;
        inboxEmail: string;
        domainId: string | null;
        domainName: string | null;
        type: string;
        severity: string;
        value: number;
        threshold: number;
        detectedAt: string;
        actionTaken: string | null;
        resolvedAt: string | null;
        retestAt: string | null;
      }>;
      backupCapacity: {
        primary: { tier: string; label: string; count: number; targetCount: number; percentage: number; status: string };
        hotBackup: { tier: string; label: string; count: number; targetCount: number; percentage: number; status: string };
        warmingPipeline: { tier: string; label: string; count: number; targetCount: number; percentage: number; status: string };
        totalCapacity: number;
        activeCapacity: number;
        backupRatio: number;
        overallStatus: string;
      } | null;
      domainGrid: Array<{
        domainId: string;
        domain: string;
        state: string;
        phase: string;
        overallHealthScore: number;
        totalInboxes: number;
        liveInboxes: number;
        deadInboxes: number;
        warmingInboxes: number;
        ageInDays: number;
        daysUntilRotation: number;
        infrastructureType: string | null;
        gmailReputation: string | null;
        microsoftReputation: string | null;
        lastInboxPlacement: number | null;
        lastSpamPlacement: number | null;
        createdAt: string;
        lastHealthCheck: string | null;
      }>;
      campaignAttribution: Array<{
        campaignId: string;
        campaignName: string;
        state: string;
        inboxesKilled7d: number;
        domainsAffected: number;
        totalSent: number;
        bounceCount: number;
        bounceRate: number;
        complaintCount: number;
        complaintRate: number;
        riskLevel: string;
      }>;
      contaminationSources: Array<{
        id: string;
        listName: string;
        campaignId: string;
        campaignName: string;
        totalLeads: number;
        bouncedLeads: number;
        bounceRate: number;
        sourceType: string;
        sourceProvider: string | null;
        importedAt: string;
        status: string;
        inboxesAffected: number;
        domainsAffected: number;
      }>;
      espSummaries: Array<{
        provider: string;
        reputation: string;
        reputationTrend: string;
        inboxPlacementRate: number;
        spamPlacementRate: number;
        promotionsPlacementRate: number | null;
        spfPassing: boolean;
        dkimPassing: boolean;
        dmarcPassing: boolean;
        userReportedSpamRate: number | null;
        ipReputation: string | null;
        complaintRate: number | null;
        trapHits: number | null;
        filterResult: string | null;
        lastUpdated: string;
      }>;
    }>(response);
  },

  /**
   * Get real-time inventory health from EmailBison + RBL data
   */
  async getInventoryHealth(clientId: string): Promise<InventoryHealth> {
    const response = await fetchApi<Record<string, unknown>>(`/api/health/inventory/${clientId}`);
    return toCamelCase<InventoryHealth>(response);
  },

  /**
   * Get EmailBison sending capacity data
   */
  async getEmailBisonCapacity(clientId: string, forceSync = false): Promise<{
    liveInboxes: number;
    totalInboxes: number;
    dailySendLimit: number;
    warmingInboxes: number;
    deadInboxes: number;
    warmupDistribution: {
      range_0_25: number;
      range_25_50: number;
      range_50_75: number;
      range_75_100: number;
    };
    lastSynced: string;
  }> {
    const response = await fetchApi<Record<string, unknown>>(
      `/api/health/emailbison-capacity/${clientId}${forceSync ? '?force_sync=true' : ''}`
    );
    return toCamelCase<{
      liveInboxes: number;
      totalInboxes: number;
      dailySendLimit: number;
      warmingInboxes: number;
      deadInboxes: number;
      warmupDistribution: {
        range_0_25: number;
        range_25_50: number;
        range_50_75: number;
        range_75_100: number;
      };
      lastSynced: string;
    }>(response);
  },

  /**
   * Get infrastructure health from LOCAL DATABASE only (no EmailBison API calls).
   * Data is refreshed by the sync worker.
   */
  async getInfrastructureHealth(clientId: string): Promise<{
    clientId: string;
    totalInboxes: number;
    liveInboxes: number;
    deadInboxes: number;
    avgHealthScore: number;
    providers: Array<{
      name: string;
      count: number;
      liveCount: number;
      deadCount: number;
      avgHealthScore: number;
    }>;
    healthDistribution: {
      healthy: number;
      good: number;
      warning: number;
      critical: number;
      total: number;
    };
    totalDomains: number;
    liveDomains: number;
    deadDomains: number;
    cleanDomains: number;
    flaggedDomains: number;
    lastSync: string | null;
    syncSource: string;
  }> {
    const response = await fetchApi<Record<string, unknown>>(
      `/api/health/infrastructure/${clientId}`
    );
    return toCamelCase<{
      clientId: string;
      totalInboxes: number;
      liveInboxes: number;
      deadInboxes: number;
      avgHealthScore: number;
      providers: Array<{
        name: string;
        count: number;
        liveCount: number;
        deadCount: number;
        avgHealthScore: number;
      }>;
      healthDistribution: {
        healthy: number;
        good: number;
        warning: number;
        critical: number;
        total: number;
      };
      totalDomains: number;
      liveDomains: number;
      deadDomains: number;
      cleanDomains: number;
      flaggedDomains: number;
      lastSync: string | null;
      syncSource: string;
    }>(response);
  },

  /**
   * Get kill velocity data for trend chart (weekly deaths over 5 weeks)
   */
  async getKillVelocity(clientId: string): Promise<{
    weekly: Array<{ week: string; deaths: number }>;
    totalDeaths7d: number;
    totalDeaths30d: number;
    churnRate7d: number;
    trend: 'up' | 'down' | 'stable';
  }> {
    const response = await fetchApi<Record<string, unknown>>(
      `/api/health/kill-velocity/${clientId}`
    );
    return toCamelCase<{
      weekly: Array<{ week: string; deaths: number }>;
      totalDeaths7d: number;
      totalDeaths30d: number;
      churnRate7d: number;
      trend: 'up' | 'down' | 'stable';
    }>(response);
  },

  /**
   * Get kill trigger breakdown showing WHY inboxes died
   */
  async getKillBreakdown(clientId: string): Promise<{
    reputation: { count: number; triggers: string[]; percentage: number };
    listQuality: { count: number; triggers: string[]; percentage: number };
    prematureDeployment: { count: number; triggers: string[]; percentage: number };
    other: { count: number; triggers: string[]; percentage: number };
    byProvider: { gmail: number; microsoft: number };
    totalKilled: number;
    raw: Array<{ trigger: string; count: number; gmailCount: number; microsoftCount: number }>;
  }> {
    const response = await fetchApi<Record<string, unknown>>(
      `/api/health/kill-breakdown/${clientId}`
    );
    return toCamelCase<{
      reputation: { count: number; triggers: string[]; percentage: number };
      listQuality: { count: number; triggers: string[]; percentage: number };
      prematureDeployment: { count: number; triggers: string[]; percentage: number };
      other: { count: number; triggers: string[]; percentage: number };
      byProvider: { gmail: number; microsoft: number };
      totalKilled: number;
      raw: Array<{ trigger: string; count: number; gmailCount: number; microsoftCount: number }>;
    }>(response);
  },

  /**
   * Get daily volume history for sending capacity chart
   */
  async getDailyVolumeHistory(
    clientId: string,
    params?: { days?: number; workspaceId?: string }
  ): Promise<{
    clientId: string;
    workspaceId: string | null;
    startDate: string;
    endDate: string;
    daysRequested: number;
    daysReturned: number;
    snapshots: Array<{
      date: string;
      emailsSent: number;
      emailsDelivered: number;
      emailsBounced: number;
      dailyCapacityAvailable: number;
      liveInboxes: number;
      incubatingInboxes: number;
      deadInboxes: number;
      capacityUtilizationPct: number | null;
      killsThatDay: number;
    }>;
    killEvents: Array<{
      date: string;
      inboxesKilled: number;
      killReasons: string;
    }>;
    totalEmailsSent: number;
    avgDailyCapacity: number;
    avgUtilizationPct: number;
    totalKills: number;
  }> {
    const searchParams = new URLSearchParams();
    if (params?.days) searchParams.set('days', params.days.toString());
    if (params?.workspaceId) searchParams.set('workspace_id', params.workspaceId);

    const query = searchParams.toString();
    const response = await fetchApi<Record<string, unknown>>(
      `/api/health/daily-volume/${clientId}${query ? `?${query}` : ''}`
    );
    return toCamelCase<{
      clientId: string;
      workspaceId: string | null;
      startDate: string;
      endDate: string;
      daysRequested: number;
      daysReturned: number;
      snapshots: Array<{
        date: string;
        emailsSent: number;
        emailsDelivered: number;
        emailsBounced: number;
        dailyCapacityAvailable: number;
        liveInboxes: number;
        incubatingInboxes: number;
        deadInboxes: number;
        capacityUtilizationPct: number | null;
        killsThatDay: number;
      }>;
      killEvents: Array<{
        date: string;
        inboxesKilled: number;
        killReasons: string;
      }>;
      totalEmailsSent: number;
      avgDailyCapacity: number;
      avgUtilizationPct: number;
      totalKills: number;
    }>(response);
  },
};

// ===== INVENTORY API =====

import type {
  InventoryOverview,
  InventoryInbox,
  InventoryInboxListResponse,
  AutoKillConfig,
  KillAndReplaceResponse,
  InventoryAuditEvent,
} from './types/inventory';

export const inventoryApi = {
  /**
   * Get inventory overview with pool/lifecycle distribution
   */
  async getOverview(clientId: string): Promise<InventoryOverview> {
    const response = await fetchApi<Record<string, unknown>>(`/api/inventory/overview/${clientId}`);
    return toCamelCase<InventoryOverview>(response);
  },

  /**
   * Get inboxes with inventory status
   */
  async getInboxes(
    clientId: string,
    params?: {
      poolStatus?: string;
      lifecycleStatus?: string;
      limit?: number;
      offset?: number;
    }
  ): Promise<InventoryInboxListResponse> {
    const searchParams = new URLSearchParams();
    if (params?.poolStatus) searchParams.set('pool_status', params.poolStatus);
    if (params?.lifecycleStatus) searchParams.set('lifecycle_status', params.lifecycleStatus);
    if (params?.limit) searchParams.set('limit', params.limit.toString());
    if (params?.offset) searchParams.set('offset', params.offset.toString());

    const query = searchParams.toString();
    const response = await fetchApi<Record<string, unknown>>(
      `/api/inventory/inboxes/${clientId}${query ? `?${query}` : ''}`
    );
    return toCamelCase<InventoryInboxListResponse>(response);
  },

  /**
   * Get auto-kill configuration
   */
  async getAutoKillConfig(clientId: string): Promise<AutoKillConfig> {
    const response = await fetchApi<Record<string, unknown>>(`/api/inventory/auto-kill/config/${clientId}`);
    return toCamelCase<AutoKillConfig>(response);
  },

  /**
   * Set auto-kill configuration
   */
  async setAutoKillConfig(clientId: string, config: AutoKillConfig): Promise<{ success: boolean; message: string }> {
    const response = await fetchApi<Record<string, unknown>>(`/api/inventory/auto-kill/config/${clientId}`, {
      method: 'POST',
      body: JSON.stringify({
        enabled: config.enabled,
        cooldown_hours: config.cooldownHours,
        auto_replace: config.autoReplace,
        notify_on_kill: config.notifyOnKill,
      }),
    });
    return toCamelCase<{ success: boolean; message: string }>(response);
  },

  /**
   * Kill an inbox and optionally replace in campaigns
   */
  async killAndReplace(
    inboxId: string,
    killReason: string,
    autoReplace = true
  ): Promise<KillAndReplaceResponse> {
    const response = await fetchApi<Record<string, unknown>>('/api/inventory/kill-and-replace', {
      method: 'POST',
      body: JSON.stringify({
        inbox_id: inboxId,
        kill_reason: killReason,
        auto_replace: autoReplace,
      }),
    });
    return toCamelCase<KillAndReplaceResponse>(response);
  },

  /**
   * Process all pending auto-kills
   */
  async processAutoKills(clientId: string): Promise<{ processed: number; message: string }> {
    const response = await fetchApi<Record<string, unknown>>(`/api/inventory/process-auto-kills/${clientId}`, {
      method: 'POST',
    });
    return toCamelCase<{ processed: number; message: string }>(response);
  },

  /**
   * Get inventory audit log
   */
  async getAuditLog(
    clientId: string,
    params?: {
      eventType?: string;
      limit?: number;
      offset?: number;
    }
  ): Promise<{ items: InventoryAuditEvent[]; total: number }> {
    const searchParams = new URLSearchParams();
    if (params?.eventType) searchParams.set('event_type', params.eventType);
    if (params?.limit) searchParams.set('limit', params.limit.toString());
    if (params?.offset) searchParams.set('offset', params.offset.toString());

    const query = searchParams.toString();
    const response = await fetchApi<Record<string, unknown>>(
      `/api/inventory/audit-log/${clientId}${query ? `?${query}` : ''}`
    );
    return toCamelCase<{ items: InventoryAuditEvent[]; total: number }>(response);
  },
};

// ===== SUBSCRIPTION API =====

export const subscriptionApi = {
  /**
   * List available package templates
   */
  async listTemplates(activeOnly = true): Promise<PackageTemplate[]> {
    const response = await fetchApi<Record<string, unknown>[]>(
      `/api/subscriptions/templates?active_only=${activeOnly}`
    );
    return response.map((item) => toCamelCase<PackageTemplate>(item));
  },

  /**
   * Get a specific package template
   */
  async getTemplate(templateId: string): Promise<PackageTemplate> {
    const response = await fetchApi<Record<string, unknown>>(
      `/api/subscriptions/templates/${templateId}`
    );
    return toCamelCase<PackageTemplate>(response);
  },

  /**
   * Get subscription for a client with usage statistics
   */
  async getClientSubscription(clientId: string): Promise<SubscriptionWithUsage | null> {
    try {
      const response = await fetchApi<Record<string, unknown> | null>(
        `/api/subscriptions/client/${clientId}`
      );
      if (!response) return null;
      return toCamelCase<SubscriptionWithUsage>(response);
    } catch (error) {
      if (error instanceof APIError && error.status === 404) {
        return null;
      }
      throw error;
    }
  },

  /**
   * Create a subscription for a client
   */
  async createSubscription(
    clientId: string,
    data: {
      packageTemplateId?: string;
      entraPackages?: number;
      googlePackages?: number;
      spareRatio?: number;
      notes?: string;
    }
  ): Promise<Subscription> {
    const response = await fetchApi<Record<string, unknown>>(
      `/api/subscriptions/client/${clientId}`,
      {
        method: 'POST',
        body: JSON.stringify({
          client_id: clientId,
          ...toSnakeCase(data),
        }),
      }
    );
    return toCamelCase<Subscription>(response);
  },

  /**
   * Update a client's subscription
   */
  async updateSubscription(
    clientId: string,
    data: {
      entraPackages?: number;
      googlePackages?: number;
      spareRatio?: number;
      notes?: string;
      status?: 'active' | 'paused' | 'cancelled';
      changeReason?: string;
      changedBy?: string;
    }
  ): Promise<Subscription> {
    const response = await fetchApi<Record<string, unknown>>(
      `/api/subscriptions/client/${clientId}`,
      {
        method: 'PUT',
        body: JSON.stringify(toSnakeCase(data)),
      }
    );
    return toCamelCase<Subscription>(response);
  },

  /**
   * Apply a package template to a client's subscription
   */
  async applyTemplate(
    clientId: string,
    templateId: string,
    changeReason?: string,
    changedBy?: string
  ): Promise<Subscription> {
    const response = await fetchApi<Record<string, unknown>>(
      `/api/subscriptions/client/${clientId}/apply-template`,
      {
        method: 'POST',
        body: JSON.stringify({
          package_template_id: templateId,
          change_reason: changeReason,
          changed_by: changedBy,
        }),
      }
    );
    return toCamelCase<Subscription>(response);
  },

  /**
   * Get subscription change history for a client
   */
  async getSubscriptionHistory(clientId: string, limit = 20): Promise<SubscriptionChange[]> {
    const response = await fetchApi<Record<string, unknown>[]>(
      `/api/subscriptions/client/${clientId}/history?limit=${limit}`
    );
    return response.map((item) => toCamelCase<SubscriptionChange>(item));
  },

  /**
   * Backfill Starter package subscriptions for all clients without one
   */
  async backfillStarterPackages(): Promise<{
    message: string;
    templateUsed: string;
    createdCount: number;
    createdSubscriptions: Array<{ clientId: string; clientName: string }>;
  }> {
    const response = await fetchApi<Record<string, unknown>>(
      '/api/subscriptions/backfill/starter-package',
      { method: 'POST' }
    );
    return toCamelCase<{
      message: string;
      templateUsed: string;
      createdCount: number;
      createdSubscriptions: Array<{ clientId: string; clientName: string }>;
    }>(response);
  },
};

// ===== INBOX PROVISIONING API (V2) =====

export const inboxProvisioningApi = {
  /**
   * Get sender names formatted for inbox provisioning.
   * Returns names with full prefix lists and Hypertide constraint metadata.
   */
  async getSenderNamesForProvisioning(clientId: string): Promise<SenderNamesForProvisioningResponse> {
    const response = await fetchApi<Record<string, unknown>>(
      `/api/clients/${clientId}/sender-names-for-provisioning`
    );
    return toCamelCase<SenderNamesForProvisioningResponse>(response);
  },

  /**
   * Preview a V2 purchase without executing.
   * Validates order groups and returns breakdown of what would be purchased.
   */
  async previewPurchase(request: ExecutePurchaseV2Request): Promise<ExecutePurchaseV2Summary> {
    const response = await fetchApi<Record<string, unknown>>(
      '/api/inbox-purchasing/execute-v2/preview',
      {
        method: 'POST',
        body: JSON.stringify({
          client_id: request.clientId,
          client_name: request.clientName,
          forwarding_domain: request.forwardingDomain,
          order_groups: request.orderGroups.map((g: OrderGroup) => ({
            order_type: g.orderType,
            domain_ids: g.domainIds,
            domain_names: g.domainNames,
            sender_name_id: g.senderNameId,
          })),
          override_age_check: request.overrideAgeCheck ?? false,
          bison_username: request.bisonUsername,
          bison_password: request.bisonPassword,
          bison_workspace: request.bisonWorkspace,
          bison_url: request.bisonUrl,
          use_saved_payment: request.useSavedPayment ?? true,
        }),
      }
    );
    return toCamelCase<ExecutePurchaseV2Summary>(response);
  },

  /**
   * Execute inbox purchase with domain grouping (V2).
   * Enforces Hypertide's fixed domain requirements and converts prefixes to InboxConfigs.
   */
  async executePurchase(request: ExecutePurchaseV2Request): Promise<{
    jobId: string;
    clientId: string;
    status: string;
    message: string;
    estimatedDurationSeconds: number;
  }> {
    const response = await fetchApi<Record<string, unknown>>(
      '/api/inbox-purchasing/execute-v2',
      {
        method: 'POST',
        body: JSON.stringify({
          client_id: request.clientId,
          client_name: request.clientName,
          forwarding_domain: request.forwardingDomain,
          order_groups: request.orderGroups.map((g: OrderGroup) => ({
            order_type: g.orderType,
            domain_ids: g.domainIds,
            domain_names: g.domainNames,
            sender_name_id: g.senderNameId,
          })),
          override_age_check: request.overrideAgeCheck ?? false,
          bison_username: request.bisonUsername,
          bison_password: request.bisonPassword,
          bison_workspace: request.bisonWorkspace,
          bison_url: request.bisonUrl,
          use_saved_payment: request.useSavedPayment ?? true,
        }),
      }
    );
    return toCamelCase<{
      jobId: string;
      clientId: string;
      status: string;
      message: string;
      estimatedDurationSeconds: number;
    }>(response);
  },

  /**
   * Get status of a purchase job (works for both V1 and V2).
   */
  async getJobStatus(jobId: string): Promise<{
    jobId: string;
    clientId: string;
    status: string;
    currentStep?: string;
    ordersCompleted: number;
    ordersTotal: number;
    totalInboxes: number;
    startedAt?: string;
    completedAt?: string;
    errors: string[];
    errorType?: string;
    checkoutUrl?: string;
  }> {
    const response = await fetchApi<Record<string, unknown>>(
      `/api/inbox-purchasing/status/${jobId}`
    );
    return toCamelCase<{
      jobId: string;
      clientId: string;
      status: string;
      currentStep?: string;
      ordersCompleted: number;
      ordersTotal: number;
      totalInboxes: number;
      startedAt?: string;
      completedAt?: string;
      errors: string[];
      errorType?: string;
      checkoutUrl?: string;
    }>(response);
  },

  /**
   * List purchase jobs, optionally filtered by client or status.
   */
  async listJobs(params?: { clientId?: string; status?: string }): Promise<{
    jobs: Array<{
      jobId: string;
      clientId: string;
      status: string;
      currentStep?: string;
      startedAt?: string;
      completedAt?: string;
    }>;
    total: number;
  }> {
    const searchParams = new URLSearchParams();
    if (params?.clientId) searchParams.set('client_id', params.clientId);
    if (params?.status) searchParams.set('status', params.status);

    const query = searchParams.toString();
    const response = await fetchApi<Record<string, unknown>>(
      `/api/inbox-purchasing/jobs${query ? `?${query}` : ''}`
    );
    return toCamelCase<{
      jobs: Array<{
        jobId: string;
        clientId: string;
        status: string;
        currentStep?: string;
        startedAt?: string;
        completedAt?: string;
      }>;
      total: number;
    }>(response);
  },

  // ===== SMART ORDER METHODS (One-Click Provisioning) =====

  /**
   * Preview a smart order - auto-configures everything from database.
   * Returns all data needed for the confirmation modal.
   * @param customPurchase - If true, bypasses package validation (only checks domain count)
   */
  async getSmartOrderPreview(
    clientId: string,
    domainIds: string[],
    providerType: 'entra' | 'google' = 'entra',
    customPurchase: boolean = false
  ): Promise<SmartOrderPreview> {
    const response = await fetchApi<Record<string, unknown>>(
      `/api/inbox-purchasing/smart-order/preview?client_id=${clientId}&domain_ids=${domainIds.join(',')}&provider_type=${providerType}&custom_purchase=${customPurchase}`
    );
    return toCamelCase<SmartOrderPreview>(response);
  },

  /**
   * Execute a smart order - one-click provisioning.
   * Auto-configures everything from database and executes Hypertide purchase.
   * @param customPurchase - If true, bypasses package validation (only checks domain count)
   */
  async executeSmartOrder(request: SmartOrderRequest): Promise<SmartOrderResponse> {
    const response = await fetchApi<Record<string, unknown>>(
      '/api/inbox-purchasing/smart-order',
      {
        method: 'POST',
        body: JSON.stringify({
          client_id: request.clientId,
          domain_ids: request.domainIds,
          provider_type: request.providerType ?? 'entra',
          override_age_check: request.overrideAgeCheck ?? false,
          custom_purchase: request.customPurchase ?? false,
        }),
      }
    );
    return toCamelCase<SmartOrderResponse>(response);
  },

  /**
   * Retry a failed purchase job.
   * Creates a new job with the same parameters and marks the old job as superseded.
   */
  async retryJob(jobId: string): Promise<SmartOrderResponse> {
    const response = await fetchApi<Record<string, unknown>>(
      `/api/inbox-purchasing/jobs/${jobId}/retry`,
      { method: 'POST' }
    );
    return toCamelCase<SmartOrderResponse>(response);
  },

  /**
   * Cancel a purchase job and unlock its domains.
   * Cannot cancel jobs that are currently executing.
   */
  async cancelJob(jobId: string): Promise<{ message: string; jobId: string }> {
    return fetchApi<{ message: string; jobId: string }>(
      `/api/inbox-purchasing/jobs/${jobId}`,
      { method: 'DELETE' }
    );
  },

  /**
   * Confirm manual checkout payment for an awaiting_checkout job.
   */
  async confirmCheckout(jobId: string): Promise<{ message: string; jobId: string; status: string }> {
    return fetchApi<{ message: string; jobId: string; status: string }>(
      `/api/inbox-purchasing/jobs/${jobId}/confirm-checkout`,
      { method: 'POST' }
    );
  },

  // ===== MANUAL ORDER PROCESSING =====

  /**
   * Get a human-readable order summary for manual processing.
   * Returns formatted text optimized for copy-pasting into Hypertide forms.
   */
  async getOrderSummary(jobId: string): Promise<{
    jobId: string;
    summary: string;
    clientName: string;
    providerType: string;
    orderCount: number;
  }> {
    const response = await fetchApi<Record<string, unknown>>(
      `/api/inbox-purchasing/jobs/${jobId}/order-summary`
    );
    return toCamelCase<{
      jobId: string;
      summary: string;
      clientName: string;
      providerType: string;
      orderCount: number;
    }>(response);
  },

  /**
   * Send order details to Slack for manual processing.
   * Updates job status to 'manual_processing' after successful send.
   */
  async sendToSlack(jobId: string): Promise<{
    message: string;
    jobId: string;
    status: string;
    channel: string;
  }> {
    return fetchApi<{
      message: string;
      jobId: string;
      status: string;
      channel: string;
    }>(
      `/api/inbox-purchasing/jobs/${jobId}/send-to-slack`,
      { method: 'POST' }
    );
  },

  /**
   * Mark a job as manually completed.
   * Use after a team member has processed the order manually in Hypertide.
   */
  async manualComplete(jobId: string, notes?: string): Promise<{
    message: string;
    jobId: string;
    status: string;
    domainsUpdated: number;
    infrastructureType: string;
  }> {
    return fetchApi<{
      message: string;
      jobId: string;
      status: string;
      domainsUpdated: number;
      infrastructureType: string;
    }>(
      `/api/inbox-purchasing/jobs/${jobId}/manual-complete`,
      {
        method: 'POST',
        body: JSON.stringify({ notes }),
      }
    );
  },
};

// ===== CAMPAIGN DOCUMENT API =====

export const campaignDocumentApi = {
  /**
   * Get all campaign documents for a client
   */
  async getClientDocuments(clientId: string): Promise<ClientDocumentsResponse> {
    const response = await fetchApi<Record<string, unknown>>(`/api/strategy/documents/${clientId}`);
    return toCamelCase<ClientDocumentsResponse>(response);
  },

  /**
   * Get a single campaign document
   */
  async getDocument(clientId: string, documentId: string): Promise<CampaignDocument> {
    const response = await fetchApi<Record<string, unknown>>(`/api/strategy/documents/${clientId}/${documentId}`);
    return toCamelCase<CampaignDocument>(response);
  },

  /**
   * Edit a variant within a document
   */
  async editVariant(
    documentId: string,
    variantId: string,
    data: { subjectLine?: string; emailBody: string }
  ): Promise<{ success: boolean; message: string }> {
    return fetchApi<{ success: boolean; message: string }>(
      `/api/strategy/documents/${documentId}/variants/${variantId}`,
      {
        method: 'PATCH',
        body: JSON.stringify(toSnakeCase(data as Record<string, unknown>)),
      }
    );
  },

  /**
   * Select a variant as recommended for a position
   */
  async selectRecommended(
    documentId: string,
    position: number,
    variantNumber: number
  ): Promise<{ success: boolean; message: string }> {
    return fetchApi<{ success: boolean; message: string }>(
      `/api/strategy/documents/${documentId}/select-variant`,
      {
        method: 'POST',
        body: JSON.stringify({ position, variant_number: variantNumber }),
      }
    );
  },

  /**
   * Review a campaign document (approve/deny/revision_requested)
   */
  async reviewDocument(
    documentId: string,
    action: 'approve' | 'deny' | 'revision_requested',
    comment?: string,
    reviewer?: string
  ): Promise<{ success: boolean; message: string; status: string }> {
    return fetchApi<{ success: boolean; message: string; status: string }>(
      `/api/strategy/documents/${documentId}/review`,
      {
        method: 'POST',
        body: JSON.stringify({ action, comment, reviewer }),
      }
    );
  },

  /**
   * Add spintax to an approved campaign document
   */
  async addSpintax(documentId: string): Promise<{
    documentId: string;
    status: string;
    emailCount: number;
    message: string;
  }> {
    const response = await fetchApi<Record<string, unknown>>(
      `/api/strategy/campaigns/${documentId}/spintax`,
      { method: 'POST' }
    );
    return toCamelCase<{
      documentId: string;
      status: string;
      emailCount: number;
      message: string;
    }>(response);
  },

  /**
   * Push a campaign document to EmailBison
   */
  async pushToEmailBison(documentId: string): Promise<{
    documentId: string;
    clientId: string;
    emailbisonCampaignId: number;
    campaignName: string;
    emailsPushed: number;
    stepsCompleted: string[];
    status: string;
    message: string;
    nextSteps: string[];
  }> {
    const response = await fetchApi<Record<string, unknown>>(
      `/api/strategy/campaigns/${documentId}/push-to-emailbison`,
      { method: 'POST' }
    );
    return toCamelCase<{
      documentId: string;
      clientId: string;
      emailbisonCampaignId: number;
      campaignName: string;
      emailsPushed: number;
      stepsCompleted: string[];
      status: string;
      message: string;
      nextSteps: string[];
    }>(response);
  },

  /**
   * Update campaign document status
   */
  async updateStatus(
    documentId: string,
    status: string,
    comment?: string
  ): Promise<{ documentId: string; status: string; message: string }> {
    const params = new URLSearchParams({ status });
    if (comment) params.append('human_comment', comment);
    return fetchApi<{ documentId: string; status: string; message: string }>(
      `/api/strategy/campaigns/${documentId}/status?${params.toString()}`,
      { method: 'PUT' }
    );
  },
};

// ===== UNIFIED CYCLE API =====

export const unifiedCycleApi = {
  /**
   * Get unified cycle data for a client (cycle + config + 4 campaigns + variables)
   */
  async getUnifiedCycle(clientId: string, cycleId?: string): Promise<UnifiedCycleResponse> {
    const endpoint = cycleId
      ? `/api/strategy/cycles/${cycleId}/unified`
      : `/api/strategy/clients/${clientId}/current-cycle`;
    const response = await fetchApi<Record<string, unknown>>(endpoint);
    return toCamelCase<UnifiedCycleResponse>(response);
  },

  /**
   * Get cycle strategy config
   */
  async getCycleConfig(cycleId: string): Promise<CycleStrategyConfig> {
    const response = await fetchApi<Record<string, unknown>>(`/api/strategy/cycles/${cycleId}/config`);
    return toCamelCase<CycleStrategyConfig>(response);
  },

  /**
   * Update cycle strategy config
   */
  async updateCycleConfig(
    cycleId: string,
    data: Partial<CycleStrategyConfig>
  ): Promise<{ success: boolean; message: string }> {
    return fetchApi<{ success: boolean; message: string }>(
      `/api/strategy/cycles/${cycleId}/config`,
      {
        method: 'PUT',
        body: JSON.stringify(toSnakeCase(data as Record<string, unknown>)),
      }
    );
  },

  /**
   * Add a cycle-level variable
   */
  async addCycleVariable(
    cycleId: string,
    variable: CycleVariable
  ): Promise<{ success: boolean; message: string }> {
    return fetchApi<{ success: boolean; message: string }>(
      `/api/strategy/cycles/${cycleId}/config/variables`,
      {
        method: 'POST',
        body: JSON.stringify(toSnakeCase(variable as unknown as Record<string, unknown>)),
      }
    );
  },

  /**
   * Get all resolved variables for a campaign (inherited + campaign-specific)
   */
  async getResolvedVariables(
    campaignId: string
  ): Promise<{ cycleVariables: CycleVariable[]; campaignVariables: CycleVariable[]; copyVariables: CycleVariable[] }> {
    const response = await fetchApi<Record<string, unknown>>(
      `/api/strategy/campaigns/${campaignId}/resolved-variables`
    );
    return toCamelCase<{ cycleVariables: CycleVariable[]; campaignVariables: CycleVariable[]; copyVariables: CycleVariable[] }>(response);
  },

  /**
   * List all cycles for a client
   */
  async listClientCycles(
    clientId: string
  ): Promise<{ cycles: Array<{ id: string; cycleNumber: number; startDate: string; endDate: string; status: string }> }> {
    const response = await fetchApi<Record<string, unknown>>(`/api/strategy/clients/${clientId}/cycles`);
    return toCamelCase<{ cycles: Array<{ id: string; cycleNumber: number; startDate: string; endDate: string; status: string }> }>(response);
  },

  /**
   * Regenerate a specific section of the cycle strategy
   */
  async regenerateSection(
    cycleId: string,
    request: CycleRegenerationRequest
  ): Promise<CycleRegenerationResponse> {
    const response = await fetchApi<Record<string, unknown>>(
      `/api/strategy/cycles/${cycleId}/regenerate`,
      {
        method: 'POST',
        body: JSON.stringify(toSnakeCase(request as unknown as Record<string, unknown>)),
      }
    );
    return toCamelCase<CycleRegenerationResponse>(response);
  },

  /**
   * Check status of a regeneration job
   */
  async getRegenerationStatus(
    jobId: string
  ): Promise<CycleRegenerationResponse> {
    const response = await fetchApi<Record<string, unknown>>(
      `/api/strategy/regeneration/${jobId}/status`
    );
    return toCamelCase<CycleRegenerationResponse>(response);
  },
};

// ===== INFRASTRUCTURE PROVISIONING API =====

export const infrastructureApi = {
  /**
   * Get complete waterfall view for a client (looks up client's workspace)
   */
  async getWaterfallByClient(
    clientId: string,
    options?: {
      purchaseStatus?: 'all' | 'purchased' | 'not_purchased';
      tld?: 'com' | 'co' | 'info';
      provider?: 'entra' | 'google';
      status?: 'live' | 'flagged' | 'dead';
      showOverBudget?: boolean;
      showDeactivated?: boolean;
      showNeedsReconnection?: boolean;
    }
  ): Promise<WaterfallResponse> {
    const params = new URLSearchParams();
    if (options?.purchaseStatus && options.purchaseStatus !== 'all') {
      params.set('purchase_status', options.purchaseStatus);
    }
    if (options?.tld) params.set('tld', options.tld);
    if (options?.provider) params.set('provider', options.provider);
    if (options?.status) params.set('status', options.status);
    if (options?.showOverBudget) params.set('show_over_budget', 'true');
    if (options?.showDeactivated) params.set('show_deactivated', 'true');
    if (options?.showNeedsReconnection) params.set('show_needs_reconnection', 'true');

    const query = params.toString();
    const response = await fetchApi<Record<string, unknown>>(
      `/api/infrastructure/waterfall/client/${clientId}${query ? `?${query}` : ''}`
    );
    return toCamelCase<WaterfallResponse>(response);
  },

  /**
   * Get complete waterfall view for workspace (direct query)
   */
  async getWaterfallByWorkspace(
    workspaceId: string,
    options?: {
      view?: 'all' | 'owned' | 'new';
      stage?: number;
      provider?: 'entra' | 'google';
    }
  ): Promise<WaterfallResponse> {
    const params = new URLSearchParams();
    if (options?.view) params.set('view', options.view);
    if (options?.stage) params.set('stage', options.stage.toString());
    if (options?.provider) params.set('provider', options.provider);

    const query = params.toString();
    const response = await fetchApi<Record<string, unknown>>(
      `/api/infrastructure/waterfall/workspace/${workspaceId}${query ? `?${query}` : ''}`
    );
    return toCamelCase<WaterfallResponse>(response);
  },

  /**
   * Bulk price check for multiple domains by ID
   */
  async bulkPriceCheck(domainIds: string[]): Promise<{ jobId: string; totalDomains: number; status: string }> {
    const response = await fetchApi<Record<string, unknown>>('/api/infrastructure/bulk-price-check', {
      method: 'POST',
      body: JSON.stringify({ domain_ids: domainIds }),
    });
    return toCamelCase<{ jobId: string; totalDomains: number; status: string }>(response);
  },

  /**
   * Bulk price check for all unpriced domains in a workspace
   */
  async bulkPriceCheckWorkspace(
    workspaceId: string,
    maxDomains?: number
  ): Promise<{
    checked: number;
    available: number;
    unavailable: number;
    errors: number;
    domains: Array<{ domainName: string; porkbunPrice?: number; dynadotPrice?: number; available: boolean; error?: string }>;
  }> {
    const response = await fetchApi<Record<string, unknown>>('/api/infrastructure/bulk-price-check', {
      method: 'POST',
      body: JSON.stringify({
        workspace_id: workspaceId,
        max_domains: maxDomains || 50,
      }),
    });
    return toCamelCase<{
      checked: number;
      available: number;
      unavailable: number;
      errors: number;
      domains: Array<{ domainName: string; porkbunPrice?: number; dynadotPrice?: number; available: boolean; error?: string }>;
    }>(response);
  },

  /**
   * Bulk purchase multiple domains
   */
  async bulkPurchase(
    clientId: string,
    domainIds: string[],
    provider?: 'porkbun' | 'dynadot'
  ): Promise<{ jobId: string; totalDomains: number; status: string }> {
    const params = provider ? `?provider=${provider}` : '';
    const response = await fetchApi<Record<string, unknown>>(
      `/api/infrastructure/bulk-purchase${params}`,
      {
        method: 'POST',
        body: JSON.stringify({ client_id: clientId, domain_ids: domainIds }),
      }
    );
    return toCamelCase<{ jobId: string; totalDomains: number; status: string }>(response);
  },

  /**
   * Get purchase job status
   */
  async getPurchaseJobStatus(jobId: string): Promise<{
    jobId: string;
    status: string;
    registrar: string;
    successfulCount: number;
    failedCount: number;
    totalCost: number;
    results: Array<{
      domain: string;
      success: boolean;
      error?: string;
      orderId?: string;
    }> | null;
    errorMessage: string | null;
  }> {
    const response = await fetchApi<Record<string, unknown>>(
      `/api/infrastructure/purchase-job/${jobId}`
    );
    return toCamelCase(response);
  },

  /**
   * Execute bulk purchase and wait for completion
   * Polls job status until complete, returns final result
   */
  async bulkPurchaseAndWait(
    clientId: string,
    domainIds: string[],
    provider?: 'porkbun' | 'dynadot',
    onProgress?: (status: string, message: string) => void
  ): Promise<{
    success: boolean;
    successfulCount: number;
    failedCount: number;
    totalCost: number;
    results: Array<{
      domain: string;
      success: boolean;
      error?: string;
    }>;
    errorMessage?: string;
  }> {
    // Create the job
    onProgress?.('creating', 'Creating purchase job...');
    const { jobId } = await this.bulkPurchase(clientId, domainIds, provider);

    // Poll for completion
    const maxAttempts = 60; // 60 * 2s = 2 minutes max
    const pollInterval = 2000; // 2 seconds

    for (let attempt = 0; attempt < maxAttempts; attempt++) {
      await new Promise((resolve) => setTimeout(resolve, pollInterval));

      const job = await this.getPurchaseJobStatus(jobId);

      if (job.status === 'processing') {
        onProgress?.('processing', 'Purchasing domains...');
      }

      if (job.status === 'completed' || job.status === 'failed') {
        const allSucceeded = job.failedCount === 0 && job.successfulCount > 0;
        return {
          success: allSucceeded,
          successfulCount: job.successfulCount,
          failedCount: job.failedCount,
          totalCost: job.totalCost,
          results: job.results || [],
          errorMessage: job.errorMessage || undefined,
        };
      }
    }

    // Timeout
    return {
      success: false,
      successfulCount: 0,
      failedCount: domainIds.length,
      totalCost: 0,
      results: [],
      errorMessage: 'Purchase job timed out. Check job status manually.',
    };
  },

  /**
   * Set nameservers to DNSimple for multiple domains
   */
  async setNameservers(domainIds: string[]): Promise<{ jobId: string; totalDomains: number }> {
    const response = await fetchApi<Record<string, unknown>>('/api/infrastructure/set-nameservers', {
      method: 'POST',
      body: JSON.stringify({ domain_ids: domainIds }),
    });
    return toCamelCase<{ jobId: string; totalDomains: number }>(response);
  },

  /**
   * Verify DNS records for multiple domains
   */
  async verifyDNS(domainIds: string[]): Promise<{ results: unknown[]; allConfigured: number; partiallyConfigured: number }> {
    const response = await fetchApi<Record<string, unknown>>('/api/infrastructure/verify-dns', {
      method: 'POST',
      body: JSON.stringify({ domain_ids: domainIds }),
    });
    return toCamelCase<{ results: unknown[]; allConfigured: number; partiallyConfigured: number }>(response);
  },

  /**
   * Assign Entra or Google provider to domains
   */
  async assignProvider(domainIds: string[], provider: 'entra' | 'google'): Promise<{ updated: number; provider: string }> {
    const response = await fetchApi<Record<string, unknown>>(
      `/api/infrastructure/assign-provider?provider=${provider}`,
      {
        method: 'POST',
        body: JSON.stringify({ domain_ids: domainIds }),
      }
    );
    return toCamelCase<{ updated: number; provider: string }>(response);
  },

  /**
   * Create HyperTide order with workspace configuration
   */
  async createHyperTideOrder(request: HyperTideOrderRequest): Promise<HyperTideOrderResponse> {
    const response = await fetchApi<Record<string, unknown>>('/api/infrastructure/hypertide-order', {
      method: 'POST',
      body: JSON.stringify(toSnakeCase(request as unknown as Record<string, unknown>)),
    });
    return toCamelCase<HyperTideOrderResponse>(response);
  },

  /**
   * Get sender names for client (reads from clients.onboarding_data)
   */
  async getSenderNamesByClient(clientId: string): Promise<SenderNamesResponse> {
    const response = await fetchApi<Record<string, unknown>>(
      `/api/infrastructure/sender-names/client/${clientId}`
    );
    return toCamelCase<SenderNamesResponse>(response);
  },
};

// ===== COMBINED API EXPORT =====

export const api = {
  workspaces: workspaceApi,
  clients: clientApi,
  domains: domainApi,
  domainSourcing: domainSourcingApi,
  inboxes: inboxApi,
  inboxProvisioning: inboxProvisioningApi,
  campaigns: campaignApi,
  leads: leadApi,
  health: healthApi,
  inventory: inventoryApi,
  infrastructure: infrastructureApi,
  onboarding: onboardingApi,
  strategy: strategyApi,
  subscriptions: subscriptionApi,
  campaignDocuments: campaignDocumentApi,
  unifiedCycles: unifiedCycleApi,
};

export default api;
