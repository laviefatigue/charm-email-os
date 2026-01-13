# Health Monitoring

Comprehensive system for tracking [[infrastructure]] and [[campaigns|campaign]] health.

## Overview

Health monitoring tracks:
- Inbox deliverability and kill triggers
- Domain reputation and lifecycle
- Campaign impact on infrastructure
- ESP (Gmail/Microsoft) reputation
- Backup capacity

## State Machines

### Inbox Health State

```
Live → Dead (permanent)
```

Inboxes are killed by [[kill-triggers|kill triggers]] and cannot be recovered.

### Domain Health State

```
Live → Flagged (1 dead inbox) → Dead (≥2 dead inboxes)
```

### Campaign Health State

```
Live → Quarantined → Live (if cleared)
                  → Dead (if confirmed bad)
```

## Domain Lifecycle Phases

Domains progress through phases by age:

| Phase | Days | Status | Action |
|-------|------|--------|--------|
| warming | 0-14 | Yellow | Handle with care |
| ramping | 14-30 | Blue | Increasing sends |
| establishing | 30-90 | Green | Building reputation |
| peak | 90-180 | Green | Maximum performance |
| monitoring | 180-240 | Yellow | Prepare replacement |
| rotation | 240+ | Red | Force rotation |

```typescript
function calculateDomainPhase(ageInDays: number): DomainLifecyclePhase {
  if (ageInDays < 14) return 'warming';
  if (ageInDays < 30) return 'ramping';
  if (ageInDays < 90) return 'establishing';
  if (ageInDays < 180) return 'peak';
  if (ageInDays < 240) return 'monitoring';
  return 'rotation';
}
```

## Kill Triggers

Conditions that terminate an inbox:

### Instant Kill (Red)

| Trigger | Threshold |
|---------|-----------|
| spam_complaint | ≥1 |
| hard_bounces_24h | ≥2 |
| consecutive_hard_bounces | ≥2 |
| hard_bounce_rate_7d | >0.5% (min 50 sends) |
| bounce_rate_all_7d | >5% |
| provider_block | any |
| fresh_inbox_hard_bounce | ≥1 (inbox <14 days) |

### Confirming Kill (Yellow)

Requires retest before killing:

| Trigger | Threshold |
|---------|-----------|
| low_inbox_placement | <85% |
| high_spam_placement | >5% |
| degrading_trend | 3 consecutive days |

### Kill Trigger Data

```typescript
interface KillTrigger {
  id: string;
  inboxId: string;
  inboxEmail: string;
  domainId: string;
  domainName: string;
  type: KillTriggerType;
  severity: 'instant' | 'confirming';
  value: number;
  threshold: number;
  detectedAt: Date;
  retestAt?: Date;
  resolvedAt?: Date;
  actionTaken?: 'killed' | 'dismissed' | 'pending';
}
```

## Health Metrics

### Inbox Health Metrics

```typescript
interface InboxHealthMetrics {
  inboxId: string;
  email: string;
  state: 'live' | 'dead';
  // Sending
  emailsSent24h: number;
  emailsSent7d: number;
  dailySendLimit: number;
  // Bounces
  hardBounces24h: number;
  softBounces24h: number;
  hardBounceRate7d: number;
  consecutiveHardBounces: number;
  // Complaints
  spamComplaints: number;
  // Deliverability
  inboxPlacementRate?: number;
  spamPlacementRate?: number;
  // Age
  ageInDays: number;
  isWarming: boolean;
  warmupProgress: number;
  // Provider
  provider: 'gmail' | 'microsoft' | 'other';
  providerBlocked: boolean;
  // Triggers
  activeTriggers: KillTrigger[];
}
```

### Domain Health Metrics

```typescript
interface DomainHealthMetrics {
  domainId: string;
  domain: string;
  state: 'live' | 'flagged' | 'dead';
  phase: DomainLifecyclePhase;
  overallHealthScore: number;
  // Inbox counts
  totalInboxes: number;
  liveInboxes: number;
  deadInboxes: number;
  warmingInboxes: number;
  // ESP reputation
  gmailReputation?: 'high' | 'medium' | 'low' | 'bad';
  microsoftReputation?: 'high' | 'medium' | 'low' | 'bad';
  // Lifecycle
  ageInDays: number;
  daysUntilRotation: number;
}
```

## ESP Health Summary

Gmail/Microsoft reputation tracking:

```typescript
interface ESPHealthSummary {
  provider: 'gmail' | 'microsoft';
  reputation: 'high' | 'medium' | 'low' | 'bad';
  reputationTrend: 'improving' | 'stable' | 'declining';
  inboxPlacementRate: number;
  spamPlacementRate: number;
  // Authentication
  spfPassing: boolean;
  dkimPassing: boolean;
  dmarcPassing: boolean;
  // Gmail specific
  userReportedSpamRate?: number;
  // Microsoft specific
  complaintRate?: number;
  trapHits?: number;
}
```

## Backup Capacity

Track inbox backup levels:

```typescript
interface OverallBackupCapacity {
  primary: BackupCapacityStatus;
  hotBackup: BackupCapacityStatus;
  warmingPipeline: BackupCapacityStatus;
  totalCapacity: number;
  activeCapacity: number;
  backupRatio: number;  // Should be ≥1.0
  overallStatus: 'healthy' | 'warning' | 'critical';
}
```

## Store: [[healthStore]]

### State
```typescript
{
  inboxMetrics: InboxHealthMetrics[];
  domainMetrics: DomainHealthMetrics[];
  campaignMetrics: CampaignHealthMetrics[];
  killTriggers: KillTrigger[];
  alerts: HealthAlert[];
  backupCapacity: OverallBackupCapacity | null;
  contaminationSources: ListContaminationSource[];
  espSummaries: ESPHealthSummary[];
  overallSummary: OverallHealthSummary | null;
}
```

### Key Actions
- `killInbox(inboxId, reason)`
- `flagDomain(domainId)` / `killDomain(domainId)`
- `executeKillTrigger(triggerId)` / `dismissKillTrigger(triggerId)`
- `quarantineCampaign(campaignId, reason)`
- `addAlert(alert)` / `acknowledgeAlert(alertId)`

## Components

| Component | Purpose |
|-----------|---------|
| [[HealthScoreRing]] | Overall score visualization |
| [[DomainHealthGrid]] | Domain status grid |
| [[DomainHealthCard]] | Individual domain health |
| [[DomainPhaseBadge]] | Lifecycle phase badge |
| [[KillTriggerMonitor]] | Active trigger alerts |
| [[KillTriggerCard]] | Trigger with actions |
| [[ESPHealthSummary]] | ESP reputation cards |
| [[BackupCapacityGauge]] | Capacity visualization |
| [[ListContaminationTracker]] | List quality |
| [[CampaignAttributionPanel]] | Campaign impact |

## Route

`/clients/[clientId]/health`

## Alert Types

```typescript
type HealthAlertType =
  | 'kill_trigger'
  | 'domain_flagged'
  | 'domain_dead'
  | 'inbox_killed'
  | 'campaign_quarantined'
  | 'capacity_warning'
  | 'rotation_due'
  | 'list_contaminated';
```

## Related

- [[infrastructure]] - Domains and inboxes
- [[campaigns]] - Campaign health
- [[kill-triggers]] - Detailed trigger docs
- [[data-models]] - Full type definitions

---
Tags: #health #monitoring #deliverability
