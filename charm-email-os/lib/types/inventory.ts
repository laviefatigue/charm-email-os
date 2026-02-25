// ===== INVENTORY STATUS TYPES =====

// Pool status: where inbox is in the inventory flow
export type InventoryPoolStatus = 'deployed' | 'warning' | 'reserve';

// Lifecycle status: maturity of the inbox
export type InventoryLifecycleStatus = 'active' | 'incubating' | 'dead';

// Capacity status: overall inventory health
export type CapacityStatus = 'healthy' | 'warning' | 'critical';


// ===== STATUS COLORS & LABELS =====

export const POOL_STATUS_CONFIG: Record<InventoryPoolStatus, {
  bg: string;
  text: string;
  border: string;
  label: string;
  description: string;
}> = {
  deployed: {
    bg: 'bg-green-500',
    text: 'text-green-700',
    border: 'border-green-500',
    label: 'Deployed',
    description: 'Actively used in campaigns'
  },
  warning: {
    bg: 'bg-yellow-500',
    text: 'text-yellow-700',
    border: 'border-yellow-500',
    label: 'Warning',
    description: 'Needs cooldown due to bounces'
  },
  reserve: {
    bg: 'bg-blue-500',
    text: 'text-blue-700',
    border: 'border-blue-500',
    label: 'Reserve',
    description: 'Ready to join active pool'
  },
};

export const LIFECYCLE_STATUS_CONFIG: Record<InventoryLifecycleStatus, {
  bg: string;
  text: string;
  label: string;
  description: string;
}> = {
  active: {
    bg: 'bg-emerald-100',
    text: 'text-emerald-800',
    label: 'Active',
    description: 'Mature, healthy inbox'
  },
  incubating: {
    bg: 'bg-amber-100',
    text: 'text-amber-800',
    label: 'Incubating',
    description: 'In 2-week warmup period'
  },
  dead: {
    bg: 'bg-red-100',
    text: 'text-red-800',
    label: 'Dead',
    description: 'Killed due to bounces or domain flags'
  },
};

export const CAPACITY_STATUS_CONFIG: Record<CapacityStatus, {
  icon: string;
  color: string;
  bg: string;
  label: string;
}> = {
  healthy: {
    icon: 'CheckCircle',
    color: 'text-green-600',
    bg: 'bg-green-100',
    label: 'Healthy'
  },
  warning: {
    icon: 'AlertTriangle',
    color: 'text-yellow-600',
    bg: 'bg-yellow-100',
    label: 'Warning'
  },
  critical: {
    icon: 'AlertTriangle',
    color: 'text-red-600',
    bg: 'bg-red-100',
    label: 'Critical'
  },
};


// ===== INVENTORY OVERVIEW =====

export interface InventoryOverview {
  workspaceId: string;

  // Pool distribution
  deployedCount: number;
  deployedTarget: number;
  warningCount: number;
  reserveCount: number;
  reserveTarget: number;

  // Lifecycle distribution
  activeCount: number;
  incubatingCount: number;
  deadCount: number;

  // Death breakdown (separates health issues from business churn)
  killedByTrigger: number;  // System-killed (spam, bounces) - health metric
  deactivated: number;  // Manual/business churn - not a health problem

  // Capacity metrics
  totalInboxes: number;
  spareCapacity: number;
  sparePercentage: number;
  capacityStatus: CapacityStatus;

  // Feature flag
  autoKillEnabled: boolean;

  lastUpdated: Date;
}


// ===== INVENTORY INBOX =====

export interface InventoryInbox {
  inboxId: string;
  email: string;
  domainName: string;
  poolStatus: InventoryPoolStatus | null;
  lifecycleStatus: InventoryLifecycleStatus;
  ageDays: number;
  healthScore?: number;
  hardBounces24h: number;
  hardBounces7d: number;
  associatedCampaigns: string[];
  warningReason?: string;
  cooldownEndsAt?: Date;
}

export interface InventoryInboxListResponse {
  items: InventoryInbox[];
  total: number;
  filteredBy?: string;
}


// ===== AUTO-KILL CONFIGURATION =====

export interface AutoKillConfig {
  enabled: boolean;
  cooldownHours: number;
  autoReplace: boolean;
  notifyOnKill: boolean;
}


// ===== KILL AND REPLACE =====

export interface KillAndReplaceRequest {
  inboxId: string;
  killReason: string;
  autoReplace: boolean;
}

export interface KillAndReplaceResponse {
  killedInboxId: string;
  killedInboxEmail: string;
  affectedCampaigns: string[];
  replacementInboxId?: string;
  replacementInboxEmail?: string;
  success: boolean;
  message: string;
}


// ===== AUDIT LOG =====

export interface InventoryAuditEvent {
  id: string;
  workspaceId?: string;
  inboxId?: string;
  inboxEmail?: string;
  eventType: string;
  previousPoolStatus?: string;
  newPoolStatus?: string;
  previousLifecycleStatus?: string;
  newLifecycleStatus?: string;
  reason?: string;
  triggeredBy?: string;
  relatedCampaignIds?: string[];
  createdAt: Date;
}


// ===== BAR CHART DATA =====

export interface InventoryBarChartData {
  // Pool counts
  deployed: number;
  warning: number;
  reserve: number;

  // Total for percentage calculation
  total: number;

  // Targets for reference lines
  deployedTarget: number;
  reserveTarget: number;

  // Capacity
  spareCapacity: number;
  sparePercentage: number;
  capacityStatus: CapacityStatus;
}


// ===== UTILITY FUNCTIONS =====

export function getPoolStatusColor(status: InventoryPoolStatus | null): string {
  if (!status) return 'bg-gray-200';
  return POOL_STATUS_CONFIG[status].bg;
}

export function getLifecycleStatusColor(status: InventoryLifecycleStatus): string {
  return LIFECYCLE_STATUS_CONFIG[status].bg;
}

export function formatCooldownTime(cooldownEndsAt?: Date): string {
  if (!cooldownEndsAt) return '';
  const now = new Date();
  const diff = new Date(cooldownEndsAt).getTime() - now.getTime();
  if (diff <= 0) return 'Cooldown complete';
  const hours = Math.floor(diff / (1000 * 60 * 60));
  const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
  return `${hours}h ${minutes}m remaining`;
}
