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

  // Provider type
  infrastructureType?: 'entra' | 'google' | string;

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

// ===== ROTATION DASHBOARD TYPES =====

// Group domains by lifecycle phase for distribution visualization
export interface DomainsByPhase {
  warming: number;
  ramping: number;
  establishing: number;
  peak: number;
  monitoring: number;
  rotation: number;
}

// Domain needing rotation attention
export interface RotationAttentionItem {
  domainId: string;
  domain: string;
  phase: DomainLifecyclePhase;
  ageInDays: number;
  daysUntilRotation: number;
  inboxCount: number;
  urgency: 'critical' | 'warning' | 'monitor';
}

// Helper to group domains by phase
export function groupDomainsByPhase(domains: DomainHealthMetrics[]): DomainsByPhase {
  const result: DomainsByPhase = {
    warming: 0,
    ramping: 0,
    establishing: 0,
    peak: 0,
    monitoring: 0,
    rotation: 0,
  };

  for (const domain of domains) {
    if (domain.phase in result) {
      result[domain.phase]++;
    }
  }

  return result;
}

// Helper to get domains needing rotation attention (monitoring + rotation phases)
export function getRotationAttentionItems(domains: DomainHealthMetrics[]): RotationAttentionItem[] {
  return domains
    .filter(d => d.phase === 'monitoring' || d.phase === 'rotation')
    .map(d => ({
      domainId: d.domainId,
      domain: d.domain,
      phase: d.phase,
      ageInDays: d.ageInDays,
      daysUntilRotation: d.daysUntilRotation,
      inboxCount: d.totalInboxes,
      urgency: d.phase === 'rotation' ? 'critical' as const :
               d.ageInDays >= 210 ? 'warning' as const : 'monitor' as const,
    }))
    .sort((a, b) => b.ageInDays - a.ageInDays); // Oldest first
}

// ===== HEALTH DISTRIBUTION (PIE CHART) =====

export type HealthRange = 'healthy' | 'good' | 'warning' | 'critical';

export interface HealthDistribution {
  healthy: number;   // 80-100
  good: number;      // 60-80
  warning: number;   // 40-60
  critical: number;  // 0-40
  total: number;
}

export const HEALTH_RANGE_THRESHOLDS: Record<HealthRange, { min: number; max: number; label: string }> = {
  healthy: { min: 80, max: 100, label: 'Healthy (80-100)' },
  good: { min: 60, max: 80, label: 'Good (60-80)' },
  warning: { min: 40, max: 60, label: 'Warning (40-60)' },
  critical: { min: 0, max: 40, label: 'Critical (0-40)' },
};

// ===== LIFECYCLE DISTRIBUTION (INVENTORY VISIBILITY) =====

export type LifecycleStatus = 'incubating' | 'active' | 'dead';
export type PoolStatus = 'deployed' | 'reserve' | 'warning';

export interface LifecycleDistribution {
  // Lifecycle states (mutually exclusive)
  incubating: number;  // < 14 days old or on warming domain
  active: number;      // Mature, ready for deployment
  dead: number;        // Killed/deactivated

  // Pool status (for live inboxes only)
  deployed: number;    // Currently assigned to active campaigns
  reserve: number;     // Ready pool, not in campaigns
  warning: number;     // Has recent bounces, needs cooldown

  // Total for display (excludes dead by default in pie chart)
  totalLive: number;   // incubating + active (or deployed + reserve + warning for live only)
}

export const LIFECYCLE_STATUS_CONFIG: Record<LifecycleStatus, { label: string; color: string; bgColor: string }> = {
  incubating: { label: 'Incubating', color: 'rgb(59, 130, 246)', bgColor: 'rgb(219, 234, 254)' },  // blue
  active: { label: 'Active', color: 'rgb(34, 197, 94)', bgColor: 'rgb(220, 252, 231)' },           // green
  dead: { label: 'Dead', color: 'rgb(107, 114, 128)', bgColor: 'rgb(243, 244, 246)' },             // gray
};

export const POOL_STATUS_CONFIG: Record<PoolStatus, { label: string; color: string; bgColor: string }> = {
  deployed: { label: 'Deployed', color: 'rgb(34, 197, 94)', bgColor: 'rgb(220, 252, 231)' },       // green
  reserve: { label: 'Reserve', color: 'rgb(59, 130, 246)', bgColor: 'rgb(219, 234, 254)' },        // blue
  warning: { label: 'Warning', color: 'rgb(249, 115, 22)', bgColor: 'rgb(255, 237, 213)' },        // orange
};

// ===== INFRASTRUCTURE HEALTH (DATABASE-ONLY) =====

export interface ProviderMetrics {
  name: string;  // gmail, microsoft, other
  count: number;
  liveCount: number;
  deadCount: number;
  avgHealthScore: number;
}

export interface InfrastructureHealthResponse {
  clientId: string;
  totalInboxes: number;
  liveInboxes: number;
  deadInboxes: number;
  avgHealthScore: number;
  providers: ProviderMetrics[];
  healthDistribution: HealthDistribution;
  lifecycleDistribution?: LifecycleDistribution;  // Optional for backwards compatibility
  totalDomains: number;
  cleanDomains: number;
  flaggedDomains: number;
  lastSync: string | null;
  syncSource: string;
}
