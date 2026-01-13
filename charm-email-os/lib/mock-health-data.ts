import type {
  InboxHealthMetrics,
  DomainHealthMetrics,
  CampaignHealthMetrics,
  KillTrigger,
  HealthAlert,
  OverallBackupCapacity,
  ListContaminationSource,
  ESPHealthSummary,
  OverallHealthSummary,
  KillTriggerType,
} from '@/lib/types/health';
import { calculateDomainPhase, calculateDaysUntilRotation, getDomainHealthState } from '@/lib/types/health';
import { mockDomains, mockInboxes, mockCampaigns } from './mock-data';

// Helper to create dates in the past
const daysAgo = (days: number) => {
  const date = new Date();
  date.setDate(date.getDate() - days);
  return date;
};

const hoursAgo = (hours: number) => {
  const date = new Date();
  date.setHours(date.getHours() - hours);
  return date;
};

// ===== INBOX HEALTH METRICS =====
export function generateInboxHealthMetrics(clientId: string): InboxHealthMetrics[] {
  const clientInboxes = mockInboxes.filter((i) => i.clientId === clientId);

  return clientInboxes.map((inbox) => {
    const ageInDays = Math.floor(
      (Date.now() - new Date(inbox.createdAt).getTime()) / (1000 * 60 * 60 * 24)
    );
    const isWarming = inbox.status === 'warming';
    const isActive = inbox.status === 'active';

    // Determine provider from email
    const provider = inbox.email.includes('gmail')
      ? 'gmail'
      : inbox.email.includes('outlook') || inbox.email.includes('hotmail')
      ? 'microsoft'
      : 'other';

    // Generate realistic metrics
    const emailsSent7d = isActive ? Math.floor(Math.random() * 300) + 50 : 0;
    const emailsSent24h = isActive ? Math.floor(emailsSent7d / 7) : 0;
    const hardBounceRate7d = Math.random() * 2; // 0-2%
    const bounceRateAll7d = hardBounceRate7d + Math.random() * 3; // Add soft bounces

    return {
      inboxId: inbox.id,
      email: inbox.email,
      state: inbox.healthState || 'live',
      emailsSent24h,
      emailsSent7d,
      dailySendLimit: inbox.dailySendLimit || 50,
      hardBounces24h: Math.random() > 0.8 ? Math.floor(Math.random() * 2) : 0,
      softBounces24h: Math.floor(Math.random() * 3),
      hardBounceRate7d,
      bounceRateAll7d,
      consecutiveHardBounces: Math.random() > 0.9 ? 1 : 0,
      spamComplaints: 0,
      inboxPlacementRate: 85 + Math.random() * 15,
      spamPlacementRate: Math.random() * 5,
      ageInDays,
      isWarming,
      warmupProgress: inbox.warmupProgress || (isWarming ? 50 : 100),
      providerBlocked: false,
      provider: provider as 'gmail' | 'microsoft' | 'other',
      activeTriggers: [],
      lastHealthCheck: new Date(),
    };
  });
}

// ===== DOMAIN HEALTH METRICS =====
export function generateDomainHealthMetrics(clientId: string): DomainHealthMetrics[] {
  const clientDomains = mockDomains.filter((d) => d.clientId === clientId);
  const clientInboxes = mockInboxes.filter((i) => i.clientId === clientId);

  return clientDomains.map((domain) => {
    const domainInboxes = clientInboxes.filter((i) => i.domainId === domain.id);
    const ageInDays = Math.floor(
      (Date.now() - new Date(domain.createdAt).getTime()) / (1000 * 60 * 60 * 24)
    );

    // Count inbox states
    const liveInboxes = domainInboxes.filter(
      (i) => i.status === 'active' || i.status === 'warming'
    ).length;
    const deadInboxes = domainInboxes.filter((i) => i.healthState === 'dead').length;
    const warmingInboxes = domainInboxes.filter((i) => i.status === 'warming').length;

    // Calculate health state based on dead inboxes
    const state = getDomainHealthState(deadInboxes);
    const phase = calculateDomainPhase(ageInDays);

    return {
      domainId: domain.id,
      domain: domain.domain,
      state,
      phase,
      overallHealthScore: domain.healthScore || 85 + Math.floor(Math.random() * 15),
      totalInboxes: domainInboxes.length,
      liveInboxes,
      deadInboxes,
      warmingInboxes,
      gmailReputation: Math.random() > 0.3 ? 'high' : 'medium',
      microsoftReputation: Math.random() > 0.4 ? 'high' : 'medium',
      lastInboxPlacement: 88 + Math.random() * 10,
      lastSpamPlacement: Math.random() * 4,
      ageInDays,
      daysUntilRotation: calculateDaysUntilRotation(ageInDays),
      createdAt: domain.createdAt,
      lastHealthCheck: new Date(),
    };
  });
}

// ===== CAMPAIGN HEALTH METRICS =====
export function generateCampaignHealthMetrics(clientId: string): CampaignHealthMetrics[] {
  const clientCampaigns = mockCampaigns.filter((c) => c.clientId === clientId);

  return clientCampaigns.map((campaign) => {
    const bounceRate = Math.random() * 5;
    const complaintRate = Math.random() * 0.5;

    // Determine risk level based on metrics
    let riskLevel: 'low' | 'medium' | 'high' | 'critical' = 'low';
    if (bounceRate > 4 || complaintRate > 0.3) riskLevel = 'critical';
    else if (bounceRate > 3 || complaintRate > 0.2) riskLevel = 'high';
    else if (bounceRate > 2 || complaintRate > 0.1) riskLevel = 'medium';

    return {
      campaignId: campaign.id,
      campaignName: campaign.name,
      state: campaign.status === 'active' ? 'live' : 'live',
      inboxesKilled7d: Math.floor(Math.random() * 2),
      domainsAffected: Math.floor(Math.random() * 2),
      totalSent: campaign.leadsContacted,
      bounceCount: Math.floor(campaign.leadsContacted * (bounceRate / 100)),
      bounceRate,
      complaintCount: Math.floor(campaign.leadsContacted * (complaintRate / 100)),
      complaintRate,
      riskLevel,
    };
  });
}

// ===== KILL TRIGGERS (Sample) =====
export function generateKillTriggers(clientId: string): KillTrigger[] {
  const clientInboxes = mockInboxes.filter((i) => i.clientId === clientId);
  const clientDomains = mockDomains.filter((d) => d.clientId === clientId);

  const triggers: KillTrigger[] = [];

  // Add a few sample triggers for demonstration
  if (clientInboxes.length > 0) {
    const randomInbox = clientInboxes[Math.floor(Math.random() * clientInboxes.length)];
    const domain = clientDomains.find((d) => d.id === randomInbox.domainId);

    // Confirming trigger (low inbox placement)
    triggers.push({
      id: 'trigger-1',
      inboxId: randomInbox.id,
      inboxEmail: randomInbox.email,
      domainId: randomInbox.domainId,
      domainName: domain?.domain || 'unknown',
      type: 'low_inbox_placement',
      severity: 'confirming',
      value: 78,
      threshold: 85,
      detectedAt: hoursAgo(4),
      retestAt: hoursAgo(-44), // 48 hours from detection
      actionTaken: 'pending',
    });

    // Add another inbox with high spam placement
    if (clientInboxes.length > 1) {
      const anotherInbox = clientInboxes[1];
      const anotherDomain = clientDomains.find((d) => d.id === anotherInbox.domainId);

      triggers.push({
        id: 'trigger-2',
        inboxId: anotherInbox.id,
        inboxEmail: anotherInbox.email,
        domainId: anotherInbox.domainId,
        domainName: anotherDomain?.domain || 'unknown',
        type: 'high_spam_placement',
        severity: 'confirming',
        value: 8,
        threshold: 5,
        detectedAt: hoursAgo(12),
        retestAt: hoursAgo(-36),
        actionTaken: 'pending',
      });
    }
  }

  return triggers;
}

// ===== HEALTH ALERTS =====
export function generateHealthAlerts(clientId: string): HealthAlert[] {
  const alerts: HealthAlert[] = [
    {
      id: 'alert-1',
      type: 'rotation_due',
      severity: 'warning',
      title: 'Domain Rotation Due',
      description: 'techflow-mail.com approaching 240-day rotation threshold',
      resourceId: 'domain-2',
      resourceType: 'domain',
      resourceName: 'techflow-mail.com',
      createdAt: hoursAgo(2),
    },
    {
      id: 'alert-2',
      type: 'capacity_warning',
      severity: 'warning',
      title: 'Backup Capacity Low',
      description: 'Hot backup inboxes below 100% threshold',
      resourceId: clientId,
      resourceType: 'domain',
      resourceName: 'Infrastructure',
      createdAt: hoursAgo(6),
    },
  ];

  return alerts;
}

// ===== BACKUP CAPACITY =====
export function generateBackupCapacity(clientId: string): OverallBackupCapacity {
  const clientInboxes = mockInboxes.filter((i) => i.clientId === clientId);

  const activeCount = clientInboxes.filter((i) => i.status === 'active').length;
  const warmingCount = clientInboxes.filter((i) => i.status === 'warming').length;

  // Calculate backup counts (ideally 100% hot backup, 50% warming)
  const hotBackupTarget = activeCount;
  const warmingTarget = Math.ceil(activeCount * 0.5);

  // Simulate current backup levels (slightly under target for demo)
  const hotBackupCount = Math.max(0, warmingCount);
  const warmingPipelineCount = Math.floor(warmingCount * 0.6);

  const hotBackupPercentage = hotBackupTarget > 0 ? (hotBackupCount / hotBackupTarget) * 100 : 0;
  const warmingPercentage = warmingTarget > 0 ? (warmingPipelineCount / warmingTarget) * 100 : 0;

  return {
    primary: {
      tier: 'primary',
      label: 'Primary (Active)',
      count: activeCount,
      targetCount: activeCount,
      percentage: 100,
      status: 'healthy',
    },
    hotBackup: {
      tier: 'hot_backup',
      label: 'Hot Backup',
      count: hotBackupCount,
      targetCount: hotBackupTarget,
      percentage: hotBackupPercentage,
      status: hotBackupPercentage >= 100 ? 'healthy' : hotBackupPercentage >= 75 ? 'warning' : 'critical',
    },
    warmingPipeline: {
      tier: 'warming_pipeline',
      label: 'Warming Pipeline',
      count: warmingPipelineCount,
      targetCount: warmingTarget,
      percentage: warmingPercentage,
      status: warmingPercentage >= 100 ? 'healthy' : warmingPercentage >= 50 ? 'warning' : 'critical',
    },
    totalCapacity: activeCount + hotBackupCount + warmingPipelineCount,
    activeCapacity: activeCount,
    backupRatio: hotBackupTarget > 0 ? hotBackupCount / hotBackupTarget : 0,
    overallStatus:
      hotBackupPercentage >= 100 && warmingPercentage >= 100
        ? 'healthy'
        : hotBackupPercentage >= 75
        ? 'warning'
        : 'critical',
  };
}

// ===== LIST CONTAMINATION =====
export function generateContaminationSources(clientId: string): ListContaminationSource[] {
  return [
    {
      id: 'list-1',
      listName: 'Apollo Export Jan 2025',
      campaignId: 'campaign-1',
      campaignName: 'Remote Team Pain Points',
      totalLeads: 1250,
      bouncedLeads: 45,
      bounceRate: 3.6,
      sourceType: 'enrichment',
      sourceProvider: 'Apollo',
      importedAt: daysAgo(30),
      status: 'flagged',
      inboxesAffected: 2,
      domainsAffected: 1,
    },
    {
      id: 'list-2',
      listName: 'Manual Import Dec 2024',
      campaignId: 'campaign-2',
      campaignName: 'Productivity Benchmark',
      totalLeads: 800,
      bouncedLeads: 12,
      bounceRate: 1.5,
      sourceType: 'manual',
      importedAt: daysAgo(45),
      status: 'live',
      inboxesAffected: 0,
      domainsAffected: 0,
    },
  ];
}

// ===== ESP HEALTH SUMMARIES =====
export function generateESPSummaries(): ESPHealthSummary[] {
  return [
    {
      provider: 'gmail',
      reputation: 'high',
      reputationTrend: 'stable',
      inboxPlacementRate: 94,
      spamPlacementRate: 2,
      promotionsPlacementRate: 4,
      spfPassing: true,
      dkimPassing: true,
      dmarcPassing: true,
      userReportedSpamRate: 0.02,
      ipReputation: 'high',
      lastUpdated: hoursAgo(1),
    },
    {
      provider: 'microsoft',
      reputation: 'medium',
      reputationTrend: 'stable',
      inboxPlacementRate: 88,
      spamPlacementRate: 5,
      spfPassing: true,
      dkimPassing: true,
      dmarcPassing: true,
      complaintRate: 0.1,
      trapHits: 0,
      filterResult: 'green',
      lastUpdated: hoursAgo(2),
    },
  ];
}

// ===== OVERALL HEALTH SUMMARY =====
export function generateOverallSummary(clientId: string): OverallHealthSummary {
  const domainMetrics = generateDomainHealthMetrics(clientId);
  const inboxMetrics = generateInboxHealthMetrics(clientId);
  const killTriggers = generateKillTriggers(clientId);

  const liveDomains = domainMetrics.filter((d) => d.state === 'live').length;
  const flaggedDomains = domainMetrics.filter((d) => d.state === 'flagged').length;
  const deadDomains = domainMetrics.filter((d) => d.state === 'dead').length;

  const liveInboxes = inboxMetrics.filter((i) => i.state === 'live').length;
  const deadInboxes = inboxMetrics.filter((i) => i.state === 'dead').length;
  const warmingInboxes = inboxMetrics.filter((i) => i.isWarming).length;

  const pendingTriggers = killTriggers.filter((t) => t.actionTaken === 'pending').length;

  // Calculate overall health score
  const domainHealthAvg =
    domainMetrics.length > 0
      ? domainMetrics.reduce((sum, d) => sum + d.overallHealthScore, 0) / domainMetrics.length
      : 100;

  // Determine status
  let status: 'healthy' | 'warning' | 'critical' = 'healthy';
  let statusMessage = 'All systems operational';

  if (deadDomains > 0 || deadInboxes > 2) {
    status = 'critical';
    statusMessage = `${deadDomains} dead domain(s), ${deadInboxes} dead inbox(es)`;
  } else if (flaggedDomains > 0 || pendingTriggers > 0) {
    status = 'warning';
    statusMessage = `${pendingTriggers} pending trigger(s), ${flaggedDomains} flagged domain(s)`;
  }

  return {
    clientId,
    healthScore: Math.round(domainHealthAvg),
    status,
    statusMessage,
    totalDomains: domainMetrics.length,
    liveDomains,
    flaggedDomains,
    deadDomains,
    totalInboxes: inboxMetrics.length,
    liveInboxes,
    deadInboxes,
    warmingInboxes,
    pendingKillTriggers: pendingTriggers,
    activeAlerts: 2, // From generateHealthAlerts
    lastRefresh: new Date(),
  };
}

// ===== INITIALIZE ALL HEALTH DATA =====
export function initializeHealthData(clientId: string) {
  return {
    inboxMetrics: generateInboxHealthMetrics(clientId),
    domainMetrics: generateDomainHealthMetrics(clientId),
    campaignMetrics: generateCampaignHealthMetrics(clientId),
    killTriggers: generateKillTriggers(clientId),
    alerts: generateHealthAlerts(clientId),
    backupCapacity: generateBackupCapacity(clientId),
    contaminationSources: generateContaminationSources(clientId),
    espSummaries: generateESPSummaries(),
    overallSummary: generateOverallSummary(clientId),
  };
}
