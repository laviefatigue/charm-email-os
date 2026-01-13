// ===== STATE MACHINE TYPES =====

// Inbox lifecycle: Live -> Dead (one-way, permanent)
export type InboxHealthState = 'live' | 'dead';

// Domain lifecycle: Live -> Flagged (1 dead inbox) -> Dead (>=2 dead inboxes)
export type DomainHealthState = 'live' | 'flagged' | 'dead';

// Campaign lifecycle: Live -> Quarantined -> Live/Dead
export type CampaignHealthState = 'live' | 'quarantined' | 'dead';

// ===== DOMAIN LIFECYCLE PHASES =====
export type DomainLifecyclePhase =
  | 'warming'      // 0-14 days (yellow)
  | 'ramping'      // 14-30 days (blue)
  | 'establishing' // 30-90 days (green)
  | 'peak'         // 90-180 days (green)
  | 'monitoring'   // 180-240 days (yellow, "Prepare replacement")
  | 'rotation';    // 240+ days (red, "Force rotation required")

// ===== KILL TRIGGER TYPES =====
export type KillTriggerSeverity = 'instant' | 'confirming';

export type KillTriggerType =
  // Instant Kill (Red)
  | 'spam_complaint'           // >=1
  | 'hard_bounces_24h'         // >=2
  | 'consecutive_hard_bounces' // >=2
  | 'hard_bounce_rate_7d'      // >0.5% (min 50 sends)
  | 'bounce_rate_all_7d'       // >5%
  | 'provider_block'           // any
  | 'fresh_inbox_hard_bounce'  // >=1 (inbox <14 days)
  // Confirming Kill (Yellow)
  | 'low_inbox_placement'      // <85%
  | 'high_spam_placement'      // >5%
  | 'degrading_trend';         // 3 consecutive days

export interface KillTrigger {
  id: string;
  inboxId: string;
  inboxEmail: string;
  domainId: string;
  domainName: string;
  type: KillTriggerType;
  severity: KillTriggerSeverity;
  value: number;
  threshold: number;
  detectedAt: Date;
  retestAt?: Date; // For confirming triggers
  resolvedAt?: Date;
  actionTaken?: 'killed' | 'dismissed' | 'pending';
}

// Kill trigger threshold configuration
export const KILL_TRIGGER_THRESHOLDS: Record<KillTriggerType, { threshold: number; severity: KillTriggerSeverity; label: string; minSends?: number }> = {
  spam_complaint: { threshold: 1, severity: 'instant', label: 'Spam Complaint' },
  hard_bounces_24h: { threshold: 2, severity: 'instant', label: 'Hard Bounces (24h)' },
  consecutive_hard_bounces: { threshold: 2, severity: 'instant', label: 'Consecutive Hard Bounces' },
  hard_bounce_rate_7d: { threshold: 0.5, severity: 'instant', label: 'Hard Bounce Rate (7d)', minSends: 50 },
  bounce_rate_all_7d: { threshold: 5, severity: 'instant', label: 'Bounce Rate All (7d)' },
  provider_block: { threshold: 1, severity: 'instant', label: 'Provider Block' },
  fresh_inbox_hard_bounce: { threshold: 1, severity: 'instant', label: 'Fresh Inbox Hard Bounce' },
  low_inbox_placement: { threshold: 85, severity: 'confirming', label: 'Low Inbox Placement' },
  high_spam_placement: { threshold: 5, severity: 'confirming', label: 'High Spam Placement' },
  degrading_trend: { threshold: 3, severity: 'confirming', label: 'Degrading Trend' },
};

// ===== HEALTH METRICS =====
export interface InboxHealthMetrics {
  inboxId: string;
  email: string;
  state: InboxHealthState;

  // Sending metrics
  emailsSent24h: number;
  emailsSent7d: number;
  dailySendLimit: number;

  // Bounce metrics
  hardBounces24h: number;
  softBounces24h: number;
  hardBounceRate7d: number;
  bounceRateAll7d: number;
  consecutiveHardBounces: number;

  // Complaint metrics
  spamComplaints: number;

  // Deliverability metrics (from ESP)
  inboxPlacementRate?: number;
  spamPlacementRate?: number;

  // Warmup/Age
  ageInDays: number;
  isWarming: boolean;
  warmupProgress: number;

  // Provider status
  providerBlocked: boolean;
  provider: 'gmail' | 'microsoft' | 'other';

  // Active triggers
  activeTriggers: KillTrigger[];

  // Timestamps
  lastHealthCheck: Date;
  killedAt?: Date;
  killReason?: KillTriggerType;
}

export interface DomainHealthMetrics {
  domainId: string;
  domain: string;
  state: DomainHealthState;
  phase: DomainLifecyclePhase;

  // Aggregated health score
  overallHealthScore: number; // 0-100

  // Inbox counts
  totalInboxes: number;
  liveInboxes: number;
  deadInboxes: number;
  warmingInboxes: number;

  // ESP reputation (mock initially)
  gmailReputation?: 'high' | 'medium' | 'low' | 'bad';
  microsoftReputation?: 'high' | 'medium' | 'low' | 'bad';

  // Last placement test
  lastInboxPlacement?: number;
  lastSpamPlacement?: number;

  // Age and lifecycle
  ageInDays: number;
  daysUntilRotation: number;

  // Timestamps
  createdAt: Date;
  lastHealthCheck: Date;
  flaggedAt?: Date;
  deadAt?: Date;
}

export interface CampaignHealthMetrics {
  campaignId: string;
  campaignName: string;
  state: CampaignHealthState;

  // Attribution (which campaigns are causing damage)
  inboxesKilled7d: number;
  domainsAffected: number;

  // Bounce attribution
  totalSent: number;
  bounceCount: number;
  bounceRate: number;

  // Complaint attribution
  complaintCount: number;
  complaintRate: number;

  // Risk assessment
  riskLevel: 'low' | 'medium' | 'high' | 'critical';

  // Quarantine info
  quarantinedAt?: Date;
  quarantineReason?: string;
}

// ===== BACKUP CAPACITY =====
export type BackupTier = 'primary' | 'hot_backup' | 'warming_pipeline';

export interface BackupCapacityStatus {
  tier: BackupTier;
  label: string;
  count: number;
  targetCount: number;
  percentage: number;
  status: 'healthy' | 'warning' | 'critical';
}

export interface OverallBackupCapacity {
  primary: BackupCapacityStatus;
  hotBackup: BackupCapacityStatus;
  warmingPipeline: BackupCapacityStatus;
  totalCapacity: number;
  activeCapacity: number;
  backupRatio: number; // Should be >= 1.0 (100% backup)
  overallStatus: 'healthy' | 'warning' | 'critical';
}

// ===== LIST CONTAMINATION =====
export interface ListContaminationSource {
  id: string;
  listName: string;
  campaignId: string;
  campaignName: string;

  // Contamination metrics
  totalLeads: number;
  bouncedLeads: number;
  bounceRate: number;

  // Source breakdown
  sourceType: 'enrichment' | 'scraped' | 'manual' | 'purchased' | 'unknown';
  sourceProvider?: string; // e.g., "Apollo", "ZoomInfo"
  importedAt: Date;

  // Status
  status: 'live' | 'quarantined' | 'flagged';

  // Attribution
  inboxesAffected: number;
  domainsAffected: number;
}

// ===== ALERT FEED =====
export type HealthAlertType =
  | 'kill_trigger'
  | 'domain_flagged'
  | 'domain_dead'
  | 'inbox_killed'
  | 'campaign_quarantined'
  | 'capacity_warning'
  | 'rotation_due'
  | 'list_contaminated';

export interface HealthAlert {
  id: string;
  type: HealthAlertType;
  severity: 'info' | 'warning' | 'critical';
  title: string;
  description: string;
  resourceId: string;
  resourceType: 'inbox' | 'domain' | 'campaign' | 'list';
  resourceName: string;
  createdAt: Date;
  acknowledgedAt?: Date;
  actionTaken?: string;
}

// ===== ESP HEALTH SUMMARY =====
export type ESPProvider = 'gmail' | 'microsoft';
export type ESPReputation = 'high' | 'medium' | 'low' | 'bad';

export interface ESPHealthSummary {
  provider: ESPProvider;

  // Reputation
  reputation: ESPReputation;
  reputationTrend: 'improving' | 'stable' | 'declining';

  // Metrics
  inboxPlacementRate: number;
  spamPlacementRate: number;
  promotionsPlacementRate?: number; // Gmail only

  // Authentication
  spfPassing: boolean;
  dkimPassing: boolean;
  dmarcPassing: boolean;

  // Provider-specific
  // Gmail Postmaster
  userReportedSpamRate?: number;
  ipReputation?: ESPReputation;

  // Microsoft SNDS
  complaintRate?: number;
  trapHits?: number;
  filterResult?: 'green' | 'yellow' | 'red';

  lastUpdated: Date;
}

// ===== OVERALL HEALTH SUMMARY =====
export interface OverallHealthSummary {
  clientId: string;
  healthScore: number; // 0-100
  status: 'healthy' | 'warning' | 'critical';
  statusMessage: string;

  // Counts
  totalDomains: number;
  liveDomains: number;
  flaggedDomains: number;
  deadDomains: number;

  totalInboxes: number;
  liveInboxes: number;
  deadInboxes: number;
  warmingInboxes: number;

  // Active issues
  pendingKillTriggers: number;
  activeAlerts: number;

  // Timestamps
  lastRefresh: Date;
}

// ===== PHASE COLORS =====
export const PHASE_COLORS: Record<DomainLifecyclePhase, { bg: string; text: string; label: string; action?: string }> = {
  warming: { bg: 'bg-yellow-100', text: 'text-yellow-800', label: 'Warming', action: 'Handle with care' },
  ramping: { bg: 'bg-blue-100', text: 'text-blue-800', label: 'Ramping', action: 'Increasing sends' },
  establishing: { bg: 'bg-green-100', text: 'text-green-800', label: 'Establishing', action: 'Building reputation' },
  peak: { bg: 'bg-emerald-100', text: 'text-emerald-800', label: 'Peak', action: 'Maximum performance' },
  monitoring: { bg: 'bg-amber-100', text: 'text-amber-800', label: 'Monitoring', action: 'Prepare replacement' },
  rotation: { bg: 'bg-red-100', text: 'text-red-800', label: 'Rotation', action: 'Force rotation required' },
};

// ===== HEALTH STATE COLORS =====
export const HEALTH_STATE_COLORS = {
  inbox: {
    live: { bg: 'bg-green-100', text: 'text-green-800' },
    dead: { bg: 'bg-red-100', text: 'text-red-800' },
  },
  domain: {
    live: { bg: 'bg-green-100', text: 'text-green-800' },
    flagged: { bg: 'bg-yellow-100', text: 'text-yellow-800' },
    dead: { bg: 'bg-red-100', text: 'text-red-800' },
  },
  campaign: {
    live: { bg: 'bg-green-100', text: 'text-green-800' },
    quarantined: { bg: 'bg-yellow-100', text: 'text-yellow-800' },
    dead: { bg: 'bg-red-100', text: 'text-red-800' },
  },
};

// ===== UTILITY FUNCTIONS =====

export function calculateDomainPhase(ageInDays: number): DomainLifecyclePhase {
  if (ageInDays < 14) return 'warming';
  if (ageInDays < 30) return 'ramping';
  if (ageInDays < 90) return 'establishing';
  if (ageInDays < 180) return 'peak';
  if (ageInDays < 240) return 'monitoring';
  return 'rotation';
}

export function calculateDaysUntilRotation(ageInDays: number): number {
  return Math.max(0, 240 - ageInDays);
}

export function getDomainHealthState(deadInboxes: number): DomainHealthState {
  if (deadInboxes >= 2) return 'dead';
  if (deadInboxes === 1) return 'flagged';
  return 'live';
}

export function isInstantKillTrigger(type: KillTriggerType): boolean {
  return KILL_TRIGGER_THRESHOLDS[type].severity === 'instant';
}
