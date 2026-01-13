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
  createdAt: Date;
  updatedAt?: Date;
  // Computed from linked workspace
  inboxCount?: number;
  domainCount?: number;
  campaignCount?: number;
}

// Onboarding data collected during client setup
export interface OnboardingData {
  contactFirstNames: string[];
  primaryDomain: string;
  industry: string;
  product: string;
  inboxesNeeded: number;
  notes?: string;
}

// Domain status enum (aligned with OwnRBL)
export type DomainStatus =
  | 'pending'      // OwnRBL: pending
  | 'pending_approval'  // Legacy
  | 'approved'    // Legacy
  | 'rejected'    // Legacy
  | 'purchasing'  // Legacy
  | 'active'      // OwnRBL: active
  | 'warming'     // Legacy
  | 'flagged'     // OwnRBL: flagged
  | 'dead';       // OwnRBL: dead

// Domain entity (from OwnRBL domains table)
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
  // Health monitoring fields (from OwnRBL domain_check_summary)
  healthState?: 'live' | 'flagged' | 'dead' | 'healthy' | 'warning' | 'critical' | 'unknown';
  latestHealthScore?: number;  // OwnRBL
  latestBlacklistCount?: number;  // OwnRBL RBL data
  latestWhitelistCount?: number;  // OwnRBL RBL data
  isClean?: boolean;  // OwnRBL RBL status
  lastCheckedAt?: Date;  // OwnRBL RBL check timestamp
  flaggedAt?: Date;
  deadAt?: Date;
  // Computed
  inboxCount?: number;
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

// Campaign status enum (aligned with OwnRBL)
export type CampaignStatus = 'draft' | 'active' | 'paused' | 'completed' | 'archived';

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
  status: CampaignStatus;
  campaignStatus?: CampaignStatus;  // OwnRBL field name
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
