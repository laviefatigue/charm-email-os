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
} from './types';

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
        detail = errorData.detail;
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
  async create(data: { name: string; workspaceId?: string; logoUrl?: string }) {
    const response = await fetchApi<Record<string, unknown>>('/api/clients', {
      method: 'POST',
      body: JSON.stringify(toSnakeCase(data)),
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
  domainId: string;
  domainName: string;
  status: 'approved' | 'denied';
  message: string;
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
  jobId: string;
  clientId: string;
  clientName: string;
  count: number;
  status: string;
  createdAt: string;
  message: string;
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

export const domainSourcingApi = {
  /**
   * Generate unique domain suggestions for a client using their onboarding data.
   * Automatically filters out duplicates and saves unique domains to DB.
   */
  async generateForClient(clientId: string, options?: GenerateForClientRequest): Promise<GenerateForClientResponse> {
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

  /**
   * Approve a domain candidate for pricing search and potential purchase.
   */
  async approveDomain(domainId: string): Promise<DomainApprovalResult> {
    const response = await fetchApi<Record<string, unknown>>(
      `/api/domain-sourcing/approve/${domainId}`,
      { method: 'POST' }
    );
    return toCamelCase<DomainApprovalResult>(response);
  },

  /**
   * Deny a domain candidate - it won't appear in future pending lists.
   */
  async denyDomain(domainId: string): Promise<DomainApprovalResult> {
    const response = await fetchApi<Record<string, unknown>>(
      `/api/domain-sourcing/deny/${domainId}`,
      { method: 'POST' }
    );
    return toCamelCase<DomainApprovalResult>(response);
  },

  /**
   * Get all approved domains for a client that are ready for pricing search.
   */
  async getApprovedDomains(clientId: string): Promise<ApprovedDomainsResponse> {
    const response = await fetchApi<Record<string, unknown>>(
      `/api/domain-sourcing/approved/${clientId}`
    );
    return toCamelCase<ApprovedDomainsResponse>(response);
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
  async createGenerationJob(clientId: string, count: number = 10): Promise<GenerationJobResponse> {
    const response = await fetchApi<Record<string, unknown>>(
      `/api/domain-sourcing/jobs/create/${clientId}?count=${count}`,
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

export interface CampaignSequence {
  id: string;
  jobId: string;
  clientId: string;
  strategyId?: string;
  campaignName: string;  // Email 1 subject
  campaignType?: 'custom_signal' | 'creative_ideas' | 'whole_offer' | 'fallback';
  status: 'pending' | 'approved' | 'denied' | 'revision_requested' | 'sent';
  score?: number;
  valuePropRotation?: ('save_time' | 'save_money' | 'make_money')[];
  emails: SequenceEmail[];
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
   * Push an approved sequence to EmailBison
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

// ===== COMBINED API EXPORT =====

export const api = {
  workspaces: workspaceApi,
  clients: clientApi,
  domains: domainApi,
  domainSourcing: domainSourcingApi,
  inboxes: inboxApi,
  campaigns: campaignApi,
  leads: leadApi,
  health: healthApi,
  onboarding: onboardingApi,
  strategy: strategyApi,
  subscriptions: subscriptionApi,
};

export default api;
