// Charm Email OS - Core Data Models
// Aligned with OwnRBL database schema

// Re-export health types for convenience
export type {
  InboxHealthState,
  DomainHealthState,
  CampaignHealthState,
  DomainLifecyclePhase,
  KillTriggerType,
  KillTriggerSeverity,
} from './types/health';

// ===== WORKSPACE (from OwnRBL workspaces table) =====
export interface Workspace {
  id: string;
  workspaceName: string;
  emailbisonWorkspaceId?: number;
  senderAccountCount: number;
  campaignCount: number;
  automationEnabled: boolean;
  createdAt?: Date;
  updatedAt?: Date;
}

// ===== CLIENT (new clients table linking to workspace) =====
export interface Client {
  id: string;
  name: string;
  workspaceId?: string;  // Link to OwnRBL workspace
  workspaceName?: string;  // Joined from workspaces table
  domain: string;  // Kept for backwards compatibility (primary domain)
  logo?: string;
  onboardingComplete: boolean;
  onboardingData?: OnboardingData;
  // Profile fields
  contactName?: string;
  contactEmail?: string;
  website?: string;
  industry?: string;
  domainPattern?: string;
  createdAt: Date;
  updatedAt?: Date;
  // Computed from linked workspace
  inboxCount?: number;
  domainCount?: number;
  campaignCount?: number;
}

// Onboarding data collected during client setup
export interface OnboardingPersona {
  job_title?: string;
  first_name?: string;
  last_name?: string;
  name?: string;
  primary_segment?: string;
  seniority_level?: string;
}

// Base/seed name for variation generation (Phase 6A.5)
export interface BaseName {
  firstName: string;
  lastName: string;
  isFounder?: boolean;  // If true, always include firstname.lastname as first variation
}

// Sender name for inbox provisioning
export interface SenderName {
  firstName: string;
  lastName: string;
  emailPrefix: string;  // e.g., "john.smith"
  source: 'persona' | 'custom' | 'generated' | 'founder';  // Where this name came from
}

// Generated variation from a base name (Phase 6A.5)
export interface SenderNameVariation {
  firstName: string;      // Display name (may be abbreviated, e.g., "C" for initial)
  lastName: string;       // Display name (may be abbreviated)
  emailPrefix: string;    // e.g., "chris.booth", "c.booth", "chrisbooth"
  baseName: string;       // Reference to base name: "Chris Booth"
  pattern: string;        // Pattern used: "firstname.lastname", "f.lastname", etc.
  isFounder?: boolean;    // True if this is the founder's primary variation
}

// Available variation pattern info
export interface VariationPattern {
  name: string;           // e.g., "firstname.lastname"
  description: string;    // e.g., "Full name with dot (chris.booth)"
  example: string;        // e.g., "chris.booth"
}

// Sender name preferences for Hypertide inbox setup
export interface SenderNamePreferences {
  usePersonas: boolean;  // Use personas from onboarding
  customNames?: SenderName[];  // Custom names provided by client
  nameCount: number;  // How many names to use (max 10 for Hypertide)
}

export interface OnboardingData {
  contactFirstNames: string[];
  primaryDomain: string;
  industry: string;
  product: string;
  inboxesNeeded: number;
  notes?: string;
  personas?: OnboardingPersona[];
  // Sender name configuration for inbox provisioning
  senderNamePreferences?: SenderNamePreferences;
  preGeneratedSenderNames?: SenderName[];  // Names ready for Hypertide
  // Variation-based name generation (Phase 6A.5)
  baseSenderNames?: BaseName[];            // Base/seed names for variation generation
  variationPatterns?: string[];            // Which patterns to use for generation
}

// Domain status enum (aligned with OwnRBL)
// Simplified flow: available → purchased → active (with inboxes)
export type DomainStatus =
  | 'available'   // Generated, ready for purchase (price checking in progress)
  | 'pending'     // Legacy: alias for available
  | 'pending_approval'  // Legacy: alias for available
  | 'approved'    // Legacy: alias for available (approval step removed)
  | 'rejected'    // Legacy: deprecated (use remove instead)
  | 'denied'      // Legacy: deprecated (use remove instead)
  | 'purchasing'  // Legacy: purchase in progress
  | 'purchased'   // Domain bought, no inboxes yet
  | 'provisioning' // Inboxes being created in Hypertide
  | 'active'      // Domain with active inboxes in EmailBison
  | 'warming'     // In warmup period (< 2 weeks)
  | 'flagged'     // OwnRBL: flagged for issues
  | 'dead'        // OwnRBL: dead/retired
  | 'legacy';     // Pre-existing domains before new workflow - needs audit

// Domain entity (from OwnRBL domains table)
// Nameserver verification status
export type NameserverStatus = 'pending' | 'verified' | 'propagating' | 'mismatch' | 'failed';

export interface Domain {
  id: string;
  clientId: string;  // Kept for backwards compatibility
  workspaceId: string;  // OwnRBL workspace link
  domain: string;  // Kept for backwards compatibility
  domainName?: string;  // OwnRBL field name
  status: DomainStatus;
  healthScore?: number;
  createdAt: Date;
  updatedAt?: Date;
  // Purchase & DNS tracking for Hypertide readiness
  purchasedAt?: Date;  // When domain was purchased
  nameserversUpdatedAt?: Date;  // When nameservers were set to DNSimple (for Hypertide readiness)
  selectedProvider?: 'porkbun' | 'dynadot';  // Which registrar owns this domain
  // Price checking fields (from bulk price check)
  cachedPrice?: number;           // Best price from last check
  porkbunPrice?: number;          // Porkbun price from last check
  porkbunAvailable?: boolean;     // Whether available on Porkbun
  dynadotPrice?: number;          // Dynadot price from last check
  dynadotAvailable?: boolean;     // Whether available on Dynadot
  // Nameserver verification (can we confirm NS at registrar matches DNSimple?)
  nameserverStatus?: NameserverStatus;  // pending, verified, propagating, mismatch, failed
  nameserverVerifiedAt?: Date;  // When verification was last run
  currentNameservers?: string[];  // Actual NS returned from registrar
  // Domain age tracking (30-day setup requirement)
  registrationDate?: Date;  // When domain was first registered (from WHOIS/registrar)
  availableForSetupAt?: Date;  // When domain becomes eligible (registration + 30 days)
  domainAgeDays?: number;  // Computed: days since registration
  daysUntilAvailable?: number;  // Computed: days until 30-day threshold (0 if ready/exempt)
  isSetupEligible?: boolean;  // Computed: (30+ days old OR exempt) AND NS verified
  isAgeExempt?: boolean;  // True if status is 'legacy' or 'active' (bypasses 30-day check)
  // Infrastructure type (Entra or Google) - set when inboxes are provisioned
  infrastructureType?: 'entra' | 'google';  // Which provider inboxes use
  infrastructureSetAt?: Date;  // When infrastructure was assigned
  // Purchase job locking (domain reserved by active purchase job)
  purchaseJobId?: string;
  purchaseJobStatus?: 'pending' | 'executing' | 'failed' | 'completed' | null;
  // Health monitoring fields (from OwnRBL domain_check_summary)
  healthState?: 'live' | 'flagged' | 'dead' | 'healthy' | 'warning' | 'critical' | 'unknown';
  latestHealthScore?: number;  // OwnRBL
  latestBlacklistCount?: number;  // OwnRBL RBL data
  latestWhitelistCount?: number;  // OwnRBL RBL data
  isClean?: boolean;  // OwnRBL RBL status
  lastCheckedAt?: Date;  // OwnRBL RBL check timestamp
  flaggedAt?: Date;
  deadAt?: Date;
  // Computed inbox counts
  inboxCount?: number;
  liveInboxCount?: number;
  deadInboxCount?: number;
  // Blacklist details (names of RBLs domain is listed on)
  blacklistNames?: string[];
}

// Helper to check if DNS has propagated (24 hours since nameserver update)
export function isDnsReady(domain: Domain): boolean {
  if (!domain.nameserversUpdatedAt) return false;
  const nsDate = new Date(domain.nameserversUpdatedAt);
  const hoursSinceUpdate = (Date.now() - nsDate.getTime()) / (1000 * 60 * 60);
  return hoursSinceUpdate >= 24;
}

// Get hours remaining until DNS is ready
export function hoursUntilDnsReady(domain: Domain): number | null {
  if (!domain.nameserversUpdatedAt) return null;
  const nsDate = new Date(domain.nameserversUpdatedAt);
  const hoursSinceUpdate = (Date.now() - nsDate.getTime()) / (1000 * 60 * 60);
  if (hoursSinceUpdate >= 24) return 0;
  return Math.ceil(24 - hoursSinceUpdate);
}

// Check if domain meets 30-day age requirement (or is exempt)
export function isDomainAgeEligible(domain: Domain): boolean {
  if (domain.isAgeExempt) return true;
  return (domain.domainAgeDays ?? 0) >= 30;
}

// Get days until domain is ready for setup (0 if ready, null if unknown)
export function daysUntilDomainReady(domain: Domain): number | null {
  if (domain.isAgeExempt) return 0;
  if (domain.daysUntilAvailable !== undefined) return domain.daysUntilAvailable;
  if (!domain.registrationDate) return null;
  const regDate = new Date(domain.registrationDate);
  const ageMs = Date.now() - regDate.getTime();
  const ageDays = Math.floor(ageMs / (1000 * 60 * 60 * 24));
  if (ageDays >= 30) return 0;
  return 30 - ageDays;
}

// Inbox status enum (aligned with OwnRBL)
export type InboxStatus =
  | 'pending'        // OwnRBL: pending
  | 'pending_approval'  // Legacy
  | 'approved'      // Legacy
  | 'rejected'      // Legacy
  | 'provisioning'  // Legacy
  | 'active'        // OwnRBL: active
  | 'warming'       // Legacy
  | 'warmup'        // OwnRBL: warmup
  | 'paused'        // OwnRBL: paused
  | 'dead';         // OwnRBL: dead

// Inbox state (v3.0 health state)
export type InboxState = 'live' | 'dead';

// ESP type
export type ESPType = 'gmail' | 'microsoft' | 'other';

// v3.0 Kill Trigger types from OwnRBL
export type OwnRBLKillTriggerType =
  | 'bounce_24h'
  | 'bounce_7d'
  | 'bounce_rate_7d'
  | 'total_bounce_rate'
  | 'fresh_inbox_bounce'
  | 'spam_complaint'
  | 'rbl_critical'
  | 'warmup_failed'
  | 'manual';

// Inbox entity (from OwnRBL sender_accounts table)
export interface Inbox {
  id: string;
  clientId: string;  // Kept for backwards compatibility
  workspaceId: string;  // OwnRBL workspace link
  domainId: string;
  emailbisonAccountId?: number;  // OwnRBL: External sync ID
  email: string;  // Kept for backwards compatibility
  emailAddress?: string;  // OwnRBL field name
  firstName: string;
  lastName: string;
  displayName?: string;  // OwnRBL
  status: InboxStatus;
  inboxState?: InboxState;  // v3.0 health state
  espType?: ESPType;  // OwnRBL
  // Warmup metrics
  warmupEnabled?: boolean;
  warmupProgress?: number; // 0-100
  warmupScore?: number;  // OwnRBL: From warmup snapshots
  dailySendLimit?: number;
  // Bounce metrics (kill trigger data)
  hardBounces24h?: number;  // OwnRBL
  hardBounces7d?: number;  // OwnRBL
  softBounces7d?: number;  // OwnRBL
  totalSends7d?: number;  // OwnRBL
  bounceRate7d?: number;  // Computed
  // v3.0 Kill trigger
  removalTag?: string;  // OwnRBL: v3.0 kill trigger tag
  removalTaggedAt?: Date;  // OwnRBL
  removedAt?: Date;  // OwnRBL
  createdAt: Date;
  updatedAt?: Date;
  // Health monitoring fields
  healthState?: 'live' | 'dead' | 'healthy' | 'warning' | 'critical';
  killedAt?: Date;
  killReason?: string;
  provider?: ESPType;
  // Domain info (joined)
  domainName?: string;
}

// Campaign idea status enum
export type CampaignIdeaStatus = 'pending' | 'approved' | 'rejected' | 'editing';

// Campaign type enum (from copywriting skill)
export type CampaignType = 'custom_signal' | 'creative_ideas' | 'whole_offer' | 'fallback';

// Clay variables structure
export interface ClayVariables {
  // Core variables (always present)
  core: {
    firstName?: string;
    companyName?: string;
    roleTitle?: string;
  };
  // High-signal variables (from research)
  highSignal?: {
    tenureYears?: string;
    recentPostTopic?: string;
    recentPostDate?: string;
    competitor?: string;
    stackCrm?: string;
    hiringRoles?: string;
    pressHeadline?: string;
    eventDate?: string;
  };
  // AI-generated variables
  aiGenerated?: {
    customerDescription?: string;
    customerType?: string;
    customGeneration?: string;
  };
  // Campaign-specific custom variables
  custom?: Record<string, string>;
  // Case study variables
  caseStudy?: {
    company?: string;
    result?: string;
    metric?: string;
    timeframe?: string;
  };
}

// Email copy structure
export interface EmailCopy {
  subject: string;
  body: string;
  cta: string;
}

// Creative idea (for creative_ideas campaign type)
export interface CreativeIdea {
  feature: string;
  action: string;
  target: string;
  benefit: string;
}

// Follow-up email in sequence
export interface FollowUpEmail {
  day: number;
  subject?: string; // No subject = threads to previous
  copy: EmailCopy;
  angle: string; // Different value prop angle
}

// QA Score breakdown
export interface QAScore {
  total: number; // 0-100
  situationRecognition: number; // 0-25
  valueClarity: number; // 0-25
  personalizationQuality: number; // 0-20
  ctaEffort: number; // 0-15
  length: number; // 0-10
  subjectLine: number; // 0-5
}

// Campaign idea entity (AI-generated) - Enhanced
export interface CampaignIdea {
  id: string;
  clientId: string;
  // Hierarchy
  industry: string;
  segment: string;
  title: string;
  angle: string;
  // Strategy (optional - populated when using full copywriting skill)
  campaignType?: CampaignType;
  constraintBox?: string[]; // 3-5 features for creative_ideas
  icpDescription?: string;
  objections?: string[];
  valueProposition?: {
    business: string; // What the company gets
    personal: string; // What they personally get
  };
  // Clay / Variables
  variables?: ClayVariables;
  // Copy
  email1?: EmailCopy;
  creativeIdeas?: CreativeIdea[]; // For creative_ideas type
  // Follow-up sequence
  followUps?: FollowUpEmail[];
  // QA
  qaScore?: QAScore;
  // Meta
  status: CampaignIdeaStatus;
  generatedAt: Date;
}

// OwnRBL campaign status (for emailbison_campaigns table)
export type OwnRBLCampaignStatus = 'draft' | 'active' | 'paused' | 'completed' | 'archived';

// Campaign entity (from OwnRBL emailbison_campaigns table)
export interface Campaign {
  id: string;
  clientId: string;  // Kept for backwards compatibility
  workspaceId: string;  // OwnRBL workspace link
  emailbisonCampaignId?: number;  // OwnRBL: External sync ID
  ideaId: string;
  name: string;
  campaignName?: string;  // OwnRBL field name
  industry: string;
  segment: string;
  angle: string;
  status: OwnRBLCampaignStatus;
  campaignStatus?: OwnRBLCampaignStatus;  // OwnRBL field name
  // Lead counts
  leadsTotal: number;
  totalLeads?: number;  // OwnRBL field name
  leadsContacted: number;
  totalLeadsContacted?: number;  // OwnRBL field name
  leadsCapacity: number; // e.g., 3000
  repliesCount: number;
  // Metrics from OwnRBL snapshots
  emailsSent?: number;
  uniqueOpens?: number;
  uniqueReplies?: number;
  bounced?: number;
  unsubscribed?: number;
  spamComplaints?: number;
  // Computed rates
  replyRate?: number;
  openRate?: number;
  bounceRate?: number;
  completionPercentage?: number;
  // Timestamps
  createdAt: Date;
  updatedAt?: Date;
  lastSnapshotAt?: Date;  // OwnRBL
}

// Lead status enum
export type LeadStatus = 'queued' | 'contacted' | 'replied' | 'bounced' | 'unsubscribed';

// Lead source enum (aligned with OwnRBL)
export type LeadSource = 'manual_upload' | 'csv_upload' | 'script_pull' | 'enrichment' | 'manual_entry' | 'emailbison_sync';

// Lead entity (from new leads table)
export interface Lead {
  id: string;
  campaignId: string;
  email: string;
  firstName: string;
  lastName: string;
  company: string;
  title: string;
  status: LeadStatus;
  contactedAt?: Date;
  // Enhanced fields for CSV upload / script pulling
  linkedInUrl?: string;
  phone?: string;
  website?: string;
  location?: string;
  industry?: string;
  companySize?: string;
  notes?: string;
  tags?: string[];
  source?: LeadSource;
  // Custom fields from CSV mapping
  customFields?: Record<string, string>;
  // Enrichment data
  enrichedAt?: Date;
  // Original row data for reference
  rawData?: Record<string, string>;
  // Timestamps
  createdAt?: Date;
  updatedAt?: Date;
}

// CSV Column mapping for lead upload
export interface CSVColumnMapping {
  csvColumn: string;
  leadField: keyof Lead | 'custom' | 'skip';
  customFieldName?: string; // Used when leadField is 'custom'
}

// Lead field options for CSV mapping
export const LEAD_FIELD_OPTIONS: { value: keyof Lead | 'custom' | 'skip'; label: string }[] = [
  { value: 'skip', label: 'Skip this column' },
  { value: 'email', label: 'Email' },
  { value: 'firstName', label: 'First Name' },
  { value: 'lastName', label: 'Last Name' },
  { value: 'company', label: 'Company' },
  { value: 'title', label: 'Job Title' },
  { value: 'linkedInUrl', label: 'LinkedIn URL' },
  { value: 'phone', label: 'Phone' },
  { value: 'website', label: 'Website' },
  { value: 'location', label: 'Location' },
  { value: 'industry', label: 'Industry' },
  { value: 'companySize', label: 'Company Size' },
  { value: 'notes', label: 'Notes' },
  { value: 'custom', label: 'Custom Field...' },
];

// Industry options for dropdowns
export const INDUSTRIES = [
  'SaaS',
  'E-commerce',
  'Financial Services',
  'Healthcare',
  'Real Estate',
  'Marketing Agency',
  'Consulting',
  'Manufacturing',
  'Technology',
  'Education',
  'Other',
] as const;

// Status colors mapping
export const STATUS_COLORS: Record<string, { bg: string; text: string }> = {
  // Domain/Inbox statuses
  pending: { bg: 'bg-yellow-100', text: 'text-yellow-800' },
  pending_approval: { bg: 'bg-yellow-100', text: 'text-yellow-800' },
  approved: { bg: 'bg-blue-100', text: 'text-blue-800' },
  rejected: { bg: 'bg-red-100', text: 'text-red-800' },
  purchasing: { bg: 'bg-purple-100', text: 'text-purple-800' },
  provisioning: { bg: 'bg-purple-100', text: 'text-purple-800' },
  active: { bg: 'bg-green-100', text: 'text-green-800' },
  warming: { bg: 'bg-orange-100', text: 'text-orange-800' },
  warmup: { bg: 'bg-orange-100', text: 'text-orange-800' },
  // Campaign idea statuses
  editing: { bg: 'bg-blue-100', text: 'text-blue-800' },
  // Campaign statuses
  draft: { bg: 'bg-gray-100', text: 'text-gray-800' },
  paused: { bg: 'bg-yellow-100', text: 'text-yellow-800' },
  completed: { bg: 'bg-green-100', text: 'text-green-800' },
  archived: { bg: 'bg-gray-100', text: 'text-gray-800' },
  // Lead statuses
  queued: { bg: 'bg-gray-100', text: 'text-gray-800' },
  contacted: { bg: 'bg-blue-100', text: 'text-blue-800' },
  replied: { bg: 'bg-green-100', text: 'text-green-800' },
  bounced: { bg: 'bg-red-100', text: 'text-red-800' },
  unsubscribed: { bg: 'bg-gray-100', text: 'text-gray-800' },
  // Health states
  live: { bg: 'bg-green-100', text: 'text-green-800' },
  dead: { bg: 'bg-red-100', text: 'text-red-800' },
  flagged: { bg: 'bg-yellow-100', text: 'text-yellow-800' },
  quarantined: { bg: 'bg-yellow-100', text: 'text-yellow-800' },
  healthy: { bg: 'bg-green-100', text: 'text-green-800' },
  warning: { bg: 'bg-yellow-100', text: 'text-yellow-800' },
  critical: { bg: 'bg-red-100', text: 'text-red-800' },
  unknown: { bg: 'bg-gray-100', text: 'text-gray-800' },
};

// ===== API RESPONSE TYPES =====

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
}

export interface HealthOverview {
  clientId: string;
  clientName: string;
  workspaceId?: string;
  totalInboxes: number;
  healthyInboxes: number;
  warningInboxes: number;
  criticalInboxes: number;
  deadInboxes: number;
  totalDomains: number;
  cleanDomains: number;
  flaggedDomains: number;
  activeCampaigns: number;
  totalEmailsSent: number;
  overallReplyRate: number;
  overallBounceRate: number;
  criticalAlerts: number;
  warningAlerts: number;
  lastUpdated: Date;
}

export interface Alert {
  id: string;
  type: string;
  severity: 'info' | 'warning' | 'critical';
  title: string;
  message: string;
  clientId?: string;
  workspaceId?: string;
  inboxId?: string;
  domainId?: string;
  campaignId?: string;
  entityName?: string;
  createdAt: Date;
  acknowledgedAt?: Date;
}

// ===== SUBSCRIPTION TYPES =====

export interface PackageTemplate {
  id: string;
  name: string;
  entraPackages: number;
  entraDomainsPerPackage: number;
  entraInboxesPerDomain: number;
  googlePackages: number;
  googleDomainsPerPackage: number;
  googleInboxesPerDomain: number;
  totalDomains: number;
  totalInboxes: number;
  monthlyPrice?: number;
  isActive: boolean;
  createdAt: Date;
}

export interface Subscription {
  id: string;
  clientId: string;
  packageTemplateId?: string;
  packageTemplateName?: string;

  // Entra configuration
  entraPackages: number;
  entraDomainsPerPackage: number;
  entraInboxesPerDomain: number;

  // Google configuration
  googlePackages: number;
  googleDomainsPerPackage: number;
  googleInboxesPerDomain: number;

  // Spare capacity
  spareRatio: number;

  // Status
  status: 'active' | 'paused' | 'cancelled';
  startedAt: Date;
  cancelledAt?: Date;
  notes?: string;
  createdAt: Date;
  updatedAt: Date;

  // Computed fields
  entraDomains: number;
  entraInboxes: number;
  googleDomains: number;
  googleInboxes: number;
  totalDomains: number;
  totalInboxes: number;
  targetSpareInboxes: number;
}

export interface SubscriptionWithUsage extends Subscription {
  // Current inventory counts
  currentActiveDomains: number;
  currentActiveInboxes: number;
  currentWarmingInboxes: number;
  currentSpareInboxes: number;
  currentFlaggedInboxes: number;

  // Computed usage fields
  domainsUsedPercent: number;
  inboxesUsedPercent: number;
  domainsRemaining: number;
  inboxesRemaining: number;
  spareStatus: 'healthy' | 'low' | 'critical';
}

export interface SubscriptionChange {
  id: string;
  subscriptionId: string;
  changeType: 'created' | 'upgrade' | 'downgrade' | 'modify' | 'cancelled';
  previousEntraPackages?: number;
  previousGooglePackages?: number;
  newEntraPackages?: number;
  newGooglePackages?: number;
  reason?: string;
  changedBy?: string;
  createdAt: Date;
}


// ===== INBOX PROVISIONING V2 TYPES =====

// Infrastructure provider type
export type InfrastructureType = 'entra' | 'google';

// Hypertide order constraints (FIXED - cannot be changed)
export const HYPERTIDE_CONSTRAINTS = {
  entra: {
    domainsPerOrder: 2,
    inboxesPerDomain: 50,
    inboxesPerOrder: 100,
    prefixLimit: 50,  // How many prefixes from our 52 to use
  },
  google: {
    domainsPerOrder: 5,
    inboxesPerDomain: 3,
    inboxesPerOrder: 15,
    prefixLimit: 3,   // How many prefixes from our 10 to use
  },
} as const;

// Sender name for provisioning (with prefix counts)
export interface SenderNameForProvisioning {
  id: string;
  firstName: string;
  lastName: string;
  isFounder: boolean;
  prefixes: string[];           // All generated prefixes
  totalPrefixCount: number;
  entraPrefixCount: number;     // How many usable for Entra (50)
  googlePrefixCount: number;    // How many usable for Google (3)
  entraPrefixes: string[];      // Top 50 prefixes for Entra
  googlePrefixes: string[];     // Top 3 prefixes for Google
  provider: string;             // Provider used to generate
  createdAt?: string;
}

// Response from sender-names-for-provisioning endpoint
export interface SenderNamesForProvisioningResponse {
  clientId: string;
  clientName: string;
  senderNames: SenderNameForProvisioning[];
  totalNames: number;
  hypertideConstraints: {
    entra: {
      domainsPerOrder: number;
      inboxesPerDomain: number;
      inboxesPerOrder: number;
    };
    google: {
      domainsPerOrder: number;
      inboxesPerDomain: number;
      inboxesPerOrder: number;
    };
  };
}

// Order group for V2 provisioning (groups domains for one Hypertide order)
export interface OrderGroup {
  orderType: InfrastructureType;
  domainIds: string[];
  domainNames: string[];       // Populated for display
  senderNameId: string;        // Which sender name to use
}

// V2 purchase request
export interface ExecutePurchaseV2Request {
  clientId: string;
  clientName: string;
  forwardingDomain: string;
  orderGroups: OrderGroup[];
  overrideAgeCheck?: boolean;
  bisonUsername?: string;
  bisonPassword?: string;
  bisonWorkspace?: string;
  bisonUrl?: string;
  useSavedPayment?: boolean;
}

// V2 purchase preview/summary
export interface ExecutePurchaseV2Summary {
  totalOrders: number;
  entraOrders: number;
  googleOrders: number;
  totalDomains: number;
  totalInboxes: number;
  entraInboxes: number;
  googleInboxes: number;
  estimatedMonthlyCost: number;
  domainBreakdown: {
    orderType: InfrastructureType;
    domains: string[];
    senderNameId: string;
    inboxes: number;
  }[];
}

// Helper: Calculate total inboxes for a set of order groups
export function calculateTotalInboxes(groups: OrderGroup[]): number {
  return groups.reduce((sum, group) => {
    const constraint = HYPERTIDE_CONSTRAINTS[group.orderType];
    return sum + constraint.inboxesPerOrder;
  }, 0);
}

// Helper: Validate order group has correct domain count
export function validateOrderGroup(group: OrderGroup): { valid: boolean; message: string } {
  const constraint = HYPERTIDE_CONSTRAINTS[group.orderType];
  const expected = constraint.domainsPerOrder;
  const actual = group.domainIds.length;

  if (actual !== expected) {
    return {
      valid: false,
      message: `${group.orderType} requires exactly ${expected} domains, got ${actual}`,
    };
  }

  return { valid: true, message: 'OK' };
}

// Helper: Check if domains can form valid order groups
export function canFormValidGroups(
  domainCount: number,
  orderType: InfrastructureType
): { canForm: boolean; completeGroups: number; remaining: number } {
  const required = HYPERTIDE_CONSTRAINTS[orderType].domainsPerOrder;
  const completeGroups = Math.floor(domainCount / required);
  const remaining = domainCount % required;

  return {
    canForm: completeGroups > 0 || remaining === 0,
    completeGroups,
    remaining,
  };
}


// ===== SMART ORDER TYPES (One-Click Provisioning) =====

// Smart order preview - auto-populated from database
export interface SmartOrderPreview {
  // Client info (auto-populated)
  clientId: string;
  clientName: string;
  forwardingDomain?: string;
  emailbisonWorkspaceId?: number;

  // Sender name info
  senderName: {
    firstName: string;
    lastName: string;
    prefixCount: number;
  };

  // Order calculation
  providerType: InfrastructureType;
  domains: string[];
  orderCount: number;
  inboxCount: number;
  monthlyCost: number;

  // Package validation
  packageUsage: {
    used: number;
    available: number;
    withinLimit: boolean;
  };

  // Validation
  isValid: boolean;
  validationErrors: string[];
}

// Smart order request - minimal input required
export interface SmartOrderRequest {
  clientId: string;
  domainIds: string[];
  providerType?: InfrastructureType;
  overrideAgeCheck?: boolean;
  customPurchase?: boolean; // Bypass package limits, only validate domain count
}

// Smart order response - job tracking
export interface SmartOrderResponse {
  jobId: string;
  clientId: string;
  status: string;
  message: string;
  estimatedDurationSeconds: number;
}

// ===== Inventory Health (from EmailBison + RBL) =====

export interface InventoryProvider {
  name: string;
  count: number;
  connected: number;
  connectionRate: number;
  avgHealth: number;
}

export interface InventoryAttentionItem {
  type: 'blacklist' | 'high_bounce' | 'low_health';
  domain?: string;
  email?: string;
  count?: number;
  lists?: string[];
  bounceRate?: number;
  bounced?: number;
  sent?: number;
  healthScore?: number;
  severity: 'critical' | 'warning' | 'info';
}

export interface InventoryHealth {
  clientId: string;
  clientName: string;
  workspaceName?: string;
  // EmailBison metrics
  totalInboxes: number;
  connectedInboxes: number;
  disconnectedInboxes: number;
  avgHealthScore: number;
  connectionRate: number;
  // Provider breakdown
  providers: InventoryProvider[];
  // Domain metrics (RBL)
  totalDomains: number;
  cleanDomains: number;
  flaggedDomains: number;
  // Issues
  attentionItems: InventoryAttentionItem[];
  // Data source info
  emailbisonAvailable: boolean;
  emailbisonError?: string;
  rblLastCheck?: Date;
}

// ===== CAMPAIGN DOCUMENT TYPES (Stablekernel Format) =====

// Target ICP definition
export interface TargetICP {
  role: string;
  companyType: string;
  companySize: string;
}

// Pain point category
export interface PainPoint {
  category: string;
  label: string;
  points: string[];
}

// Objection with preemption strategy
export interface Objection {
  objection: string;
  preemption: string;
}

// Complete ICP mapping
export interface ICPMapping {
  targetIcp: TargetICP;
  painPoints: PainPoint[];
  objections: Objection[];
}

// Variable definition
export interface VariableDefinition {
  name: string;
  description: string;
  source?: string;
  usedIn?: number[];  // Email positions where this variable is used (e.g., [1, 2, 4])
}

// Variable schema
export interface VariableSchema {
  core: VariableDefinition[];
  highSignal: VariableDefinition[];
  aiGenerated: VariableDefinition[];
}

// Email variant within a position
export interface EmailVariant {
  id?: string;
  variantNumber: number;
  variantName?: string;
  isRecommended: boolean;
  subjectLine?: string | null;
  emailBody: string;
  waitDays: number;
  threadReply: boolean;
  wordCount?: number;
  themUsRatio?: string;
  score?: number;
  angle?: string;
  strategy?: string;
  valueProp?: string;
  editedSubjectLine?: string | null;
  editedEmailBody?: string | null;
}

// Subject line option with rationale
export interface SubjectOption {
  subjectLine: string;
  rationale: string;
}

// Email position with variants
export interface EmailPosition {
  position: number;
  title: string;
  day?: number | string;  // Timing: 0, "3-4", "7-8", "11-12"
  threadBehavior?: string;  // "new_thread" or "threads_to_position_N"
  variants: EmailVariant[];
  subjectOptions?: SubjectOption[];
  subjectLineOptions?: SubjectOption[];  // Alternative name from skill output
}

// Sequence summary step
export interface SequenceSummaryStep {
  day: string;
  title: string;
  description: string;
}

// QA scoring dimension
export interface QADimension {
  name: string;
  max?: number;  // Maximum points for this dimension (e.g., 25)
  score: string | number;  // Score as "24/25" string or just 24 number
  notes: string;
}

// Complete QA scoring
export interface QAScoring {
  overallScore: number;
  verdict: string;
  dimensions: QADimension[];
}

// Strategy callout
export interface StrategyCallout {
  type: 'recommendation' | 'warning' | 'info';
  text: string;
}

// Data enrichment source
export interface DataEnrichment {
  variable: string;
  source: string;
}

// Strategy notes section
export interface StrategyNotes {
  callouts: StrategyCallout[];
  dataEnrichment: DataEnrichment[];
  abTesting: string[];
  afterSequenceNote?: string;  // Post-sequence guidance (e.g., "Stop after Email 4...")
}

// Complete campaign document (stablekernel format)
export interface CampaignDocument {
  id: string;
  jobId: string;
  clientId: string;
  strategyId?: string;
  documentName: string;
  documentVersion: number;
  vertical?: string;
  objective?: string;
  icpMapping?: ICPMapping;
  variableSchema?: VariableSchema;
  emailPositions: EmailPosition[];
  sequenceSummary?: SequenceSummaryStep[];
  qaScoring?: QAScoring;
  strategyNotes?: StrategyNotes;
  status: 'draft' | 'approved' | 'denied' | 'revision_requested';
  humanComment?: string;
  reviewedBy?: string;
  reviewedAt?: Date;
  createdAt: Date;
  updatedAt: Date;
}

// Response for client documents list
export interface ClientDocumentsResponse {
  clientId: string;
  documents: CampaignDocument[];
  total: number;
}

// Document status colors
export const DOCUMENT_STATUS_COLORS: Record<string, { bg: string; text: string }> = {
  draft: { bg: 'bg-gray-100', text: 'text-gray-800' },
  approved: { bg: 'bg-green-100', text: 'text-green-800' },
  denied: { bg: 'bg-red-100', text: 'text-red-800' },
  revision_requested: { bg: 'bg-yellow-100', text: 'text-yellow-800' },
};

// Verdict colors
export const VERDICT_COLORS: Record<string, { bg: string; text: string; border: string }> = {
  'Ship it': { bg: 'bg-emerald-50', text: 'text-emerald-700', border: 'border-emerald-200' },
  'One more pass': { bg: 'bg-amber-50', text: 'text-amber-700', border: 'border-amber-200' },
  'Start over': { bg: 'bg-red-50', text: 'text-red-700', border: 'border-red-200' },
};

// Callout type colors
export const CALLOUT_COLORS: Record<string, { bg: string; border: string; icon: string }> = {
  recommendation: { bg: 'bg-purple-50', border: 'border-purple-300', icon: 'text-purple-600' },
  warning: { bg: 'bg-amber-50', border: 'border-amber-300', icon: 'text-amber-600' },
  info: { bg: 'bg-cyan-50', border: 'border-cyan-300', icon: 'text-cyan-600' },
};

// ===== UNIFIED CYCLE TYPES (1 Cycle = 4 Campaigns = 16 Emails) =====

// Campaign angles (4 per cycle)
export type CampaignAngle = 'custom_signal' | 'persona_pain' | 'case_study' | 'risk_efficiency';

export const CAMPAIGN_ANGLES: { value: CampaignAngle; label: string; description: string }[] = [
  { value: 'custom_signal', label: 'Custom Signal', description: 'Trigger-based outreach using hiring signals, tech stack, etc.' },
  { value: 'persona_pain', label: 'Persona Pain', description: 'Pain point focused messaging for target persona' },
  { value: 'case_study', label: 'Case Study', description: 'Social proof driven with relevant case study' },
  { value: 'risk_efficiency', label: 'Risk/Efficiency', description: 'Focus on reducing risk or improving efficiency' },
];

// Variable with source information
export interface CycleVariable {
  name: string;          // e.g., "{{competitor}}"
  description: string;   // What this variable represents
  value?: string;        // Default value if known
  source?: string;       // Where to find data (e.g., "Onboarding form", "BuiltWith")
  leadGenUse?: string;   // How this helps with lead filtering
}

// Cycle strategy configuration
export interface CycleStrategyConfig {
  id: string;
  cycleId: string;
  icpMapping?: ICPMapping;
  cycleVariables: CycleVariable[];
  strategicFocus?: string;
  targetOutcome?: string;
  createdAt: Date;
  updatedAt: Date;
}

// Campaign status includes both approval and spintax workflow states
export type CampaignStatus =
  | 'draft'              // Initial state, awaiting review
  | 'approved'           // Human approved, ready for spintax
  | 'denied'             // Human rejected
  | 'revision_requested' // Human requested changes
  | 'spintax_pending'    // Spintax processing in progress
  | 'spintaxed'          // Spintax complete, ready to push
  | 'sent';              // Pushed to EmailBison

// Campaign within a cycle (extends CampaignDocument)
export interface UnifiedCampaign {
  id: string;
  cycleId: string;
  campaignNumber: 1 | 2 | 3 | 4;
  angle: CampaignAngle;
  documentName: string;
  status: CampaignStatus;
  campaignVariables: CycleVariable[];  // Campaign-specific variables
  emails: UnifiedEmail[];
  spintaxedEmails?: UnifiedEmail[];    // Populated after spintax processing
  qaScoring?: QAScoring;
  revisionHistory?: RevisionEntry[];   // History of revision requests
  reviewedBy?: string;
  reviewedAt?: Date;
  createdAt: Date;
  updatedAt: Date;
}

// Revision history entry
export interface RevisionEntry {
  id: string;
  instruction: string;
  section: string;          // 'campaign', 'email', 'icp', 'variables'
  scope?: string;           // Which specific item
  status: 'pending' | 'processed';
  createdAt: Date;
  processedAt?: Date;
}

// Email within a campaign
export interface UnifiedEmail {
  position: 1 | 2 | 3 | 4;
  title: string;           // e.g., "Poke the Bear"
  waitDays: number;
  subjectLine?: string;
  emailBody: string;
  threadReply: boolean;
  wordCount?: number;
  copyVariables: CycleVariable[];  // Variables used in this email
  score?: number;
}

// Complete unified cycle data
export interface UnifiedCycleData {
  cycle: {
    id: string;
    cycleNumber: number;
    startDate: Date;
    endDate: Date;
    status: 'planning' | 'active' | 'completed';
  };
  config: CycleStrategyConfig;
  campaigns: UnifiedCampaign[];
}

// Response from unified cycle endpoint
export interface UnifiedCycleResponse {
  clientId: string;
  data: UnifiedCycleData;
}

// Campaign angle colors
export const ANGLE_COLORS: Record<CampaignAngle, { bg: string; text: string; border: string }> = {
  custom_signal: { bg: 'bg-violet-50', text: 'text-violet-700', border: 'border-violet-200' },
  persona_pain: { bg: 'bg-blue-50', text: 'text-blue-700', border: 'border-blue-200' },
  case_study: { bg: 'bg-emerald-50', text: 'text-emerald-700', border: 'border-emerald-200' },
  risk_efficiency: { bg: 'bg-amber-50', text: 'text-amber-700', border: 'border-amber-200' },
};

// Variable level for breadcrumb
export type VariableLevel = 'cycle' | 'campaign' | 'copy';

export const VARIABLE_LEVEL_COLORS: Record<VariableLevel, { bg: string; text: string }> = {
  cycle: { bg: 'bg-purple-100', text: 'text-purple-800' },
  campaign: { bg: 'bg-blue-100', text: 'text-blue-800' },
  copy: { bg: 'bg-green-100', text: 'text-green-800' },
};

// ===== SECTION REGENERATION TYPES =====

// Sections that can be regenerated
export type RegenerationSection = 'header' | 'icp' | 'variables' | 'campaign' | 'email';

// Sub-sections for ICP
export type ICPSubSection = 'target_icp' | 'pain_points' | 'objections';

// Regeneration scope options
export interface RegenerationScope {
  campaignNumber?: 1 | 2 | 3 | 4;
  emailPosition?: 1 | 2 | 3 | 4;
  variableLevel?: VariableLevel;
  painPointCategory?: string;
  objectionIndex?: number;
}

// Request to regenerate a section
export interface CycleRegenerationRequest {
  section: RegenerationSection;
  subSection?: ICPSubSection;
  scope?: RegenerationScope;
  instruction: string;
  preserveExisting?: boolean;
}

// Response from regeneration endpoint
export interface CycleRegenerationResponse {
  regenerationId: string;
  jobId: string;
  cycleId: string;
  section: RegenerationSection;
  status: 'queued' | 'processing' | 'completed' | 'failed';
  message?: string;
  estimatedDuration?: number;
}
