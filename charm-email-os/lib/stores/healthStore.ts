import { create } from 'zustand';
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
  DomainHealthState,
} from '@/lib/types/health';
import { api } from '@/lib/api';

interface HealthStore {
  // State
  inboxMetrics: InboxHealthMetrics[];
  domainMetrics: DomainHealthMetrics[];
  campaignMetrics: CampaignHealthMetrics[];
  killTriggers: KillTrigger[];
  alerts: HealthAlert[];
  backupCapacity: OverallBackupCapacity | null;
  contaminationSources: ListContaminationSource[];
  espSummaries: ESPHealthSummary[];
  overallSummary: OverallHealthSummary | null;

  // Loading/Error states
  isLoading: boolean;
  lastRefresh: Date | null;
  error: string | null;

  // Actions - Data management
  setInboxMetrics: (metrics: InboxHealthMetrics[]) => void;
  setDomainMetrics: (metrics: DomainHealthMetrics[]) => void;
  setCampaignMetrics: (metrics: CampaignHealthMetrics[]) => void;
  setKillTriggers: (triggers: KillTrigger[]) => void;
  setAlerts: (alerts: HealthAlert[]) => void;
  setBackupCapacity: (capacity: OverallBackupCapacity) => void;
  setContaminationSources: (sources: ListContaminationSource[]) => void;
  setESPSummaries: (summaries: ESPHealthSummary[]) => void;
  setOverallSummary: (summary: OverallHealthSummary) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;

  // Async API actions
  fetchHealthOverview: (clientId: string) => Promise<void>;
  fetchAlerts: (clientId?: string) => Promise<void>;
  fetchKillTriggers: (clientId?: string) => Promise<void>;

  // Actions - Inbox management
  killInbox: (inboxId: string, reason: KillTriggerType) => Promise<void>;
  getInboxMetrics: (inboxId: string) => InboxHealthMetrics | undefined;
  getInboxMetricsByClient: (clientId: string) => InboxHealthMetrics[];

  // Actions - Domain management
  flagDomain: (domainId: string) => void;
  killDomain: (domainId: string) => void;
  getDomainMetrics: (domainId: string) => DomainHealthMetrics | undefined;
  getDomainMetricsByClient: (clientId: string) => DomainHealthMetrics[];

  // Actions - Alerts
  acknowledgeAlert: (alertId: string) => void;
  dismissAlert: (alertId: string) => void;
  addAlert: (alert: Omit<HealthAlert, 'id' | 'createdAt'>) => void;
  getActiveAlerts: () => HealthAlert[];
  getAlertsByClient: (clientId: string) => HealthAlert[];

  // Actions - Kill triggers
  executeKillTrigger: (triggerId: string) => Promise<void>;
  dismissKillTrigger: (triggerId: string) => void;
  addKillTrigger: (trigger: Omit<KillTrigger, 'id' | 'detectedAt'>) => void;
  getPendingTriggers: () => KillTrigger[];
  getTriggersByClient: (clientId: string) => KillTrigger[];

  // Actions - Campaign management
  quarantineCampaign: (campaignId: string, reason: string) => void;
  unquarantineCampaign: (campaignId: string) => void;
  getCampaignMetrics: (campaignId: string) => CampaignHealthMetrics | undefined;

  // Refresh
  refreshHealth: (clientId?: string) => Promise<void>;
}

// Helper to generate IDs
const generateId = () => Math.random().toString(36).substring(2, 11);

export const useHealthStore = create<HealthStore>((set, get) => ({
  // Initial state
  inboxMetrics: [],
  domainMetrics: [],
  campaignMetrics: [],
  killTriggers: [],
  alerts: [],
  backupCapacity: null,
  contaminationSources: [],
  espSummaries: [],
  overallSummary: null,
  isLoading: false,
  lastRefresh: null,
  error: null,

  // Data setters
  setInboxMetrics: (metrics) => set({ inboxMetrics: metrics }),
  setDomainMetrics: (metrics) => set({ domainMetrics: metrics }),
  setCampaignMetrics: (metrics) => set({ campaignMetrics: metrics }),
  setKillTriggers: (triggers) => set({ killTriggers: triggers }),
  setAlerts: (alerts) => set({ alerts }),
  setBackupCapacity: (capacity) => set({ backupCapacity: capacity }),
  setContaminationSources: (sources) => set({ contaminationSources: sources }),
  setESPSummaries: (summaries) => set({ espSummaries: summaries }),
  setOverallSummary: (summary) => set({ overallSummary: summary }),
  setLoading: (loading) => set({ isLoading: loading }),
  setError: (error) => set({ error }),

  // Async API actions
  fetchHealthOverview: async (clientId) => {
    // Delegate to refreshHealth which fetches everything
    await get().refreshHealth(clientId);
  },

  fetchAlerts: async (clientId) => {
    set({ isLoading: true, error: null });
    try {
      const result = await api.health.getAlerts({ clientId });
      // getAlerts returns { items, total, criticalCount, warningCount }
      set({ alerts: result.items as unknown as HealthAlert[], isLoading: false });
    } catch (error) {
      set({ error: (error as Error).message, isLoading: false });
    }
  },

  fetchKillTriggers: async (_clientId) => {
    // Kill triggers are now fetched via refreshHealth / full-dashboard
    set({ isLoading: false });
  },

  // Inbox management
  killInbox: async (inboxId, reason) => {
    // Optimistic update
    set((state) => ({
      inboxMetrics: state.inboxMetrics.map((m) =>
        m.inboxId === inboxId
          ? { ...m, state: 'dead' as const, killedAt: new Date(), killReason: reason }
          : m
      ),
    }));

    try {
      await api.inboxes.kill(inboxId, reason);

      // Add alert
      const inbox = get().inboxMetrics.find((m) => m.inboxId === inboxId);
      if (inbox) {
        get().addAlert({
          type: 'inbox_killed',
          severity: 'critical',
          title: `Inbox Killed: ${inbox.email}`,
          description: `Killed due to ${reason}`,
          resourceId: inboxId,
          resourceType: 'inbox',
          resourceName: inbox.email,
        });
      }
    } catch (error) {
      // Rollback
      set((state) => ({
        inboxMetrics: state.inboxMetrics.map((m) =>
          m.inboxId === inboxId
            ? { ...m, state: 'live' as const, killedAt: undefined, killReason: undefined }
            : m
        ),
        error: (error as Error).message,
      }));
    }
  },

  getInboxMetrics: (inboxId) => get().inboxMetrics.find((m) => m.inboxId === inboxId),

  getInboxMetricsByClient: (_clientId) => {
    // InboxHealthMetrics does not have clientId property - return all
    return get().inboxMetrics;
  },

  // Domain management
  flagDomain: (domainId) => {
    set((state) => ({
      domainMetrics: state.domainMetrics.map((m) =>
        m.domainId === domainId
          ? { ...m, state: 'flagged' as DomainHealthState, flaggedAt: new Date() }
          : m
      ),
    }));

    const domain = get().domainMetrics.find((m) => m.domainId === domainId);
    if (domain) {
      get().addAlert({
        type: 'domain_flagged',
        severity: 'warning',
        title: `Domain Flagged: ${domain.domain}`,
        description: 'Domain has 1 dead inbox. Prepare backup.',
        resourceId: domainId,
        resourceType: 'domain',
        resourceName: domain.domain,
      });
    }
  },

  killDomain: (domainId) => {
    set((state) => ({
      domainMetrics: state.domainMetrics.map((m) =>
        m.domainId === domainId
          ? { ...m, state: 'dead' as DomainHealthState, deadAt: new Date() }
          : m
      ),
    }));

    const domain = get().domainMetrics.find((m) => m.domainId === domainId);
    if (domain) {
      get().addAlert({
        type: 'domain_dead',
        severity: 'critical',
        title: `Domain Dead: ${domain.domain}`,
        description: 'Domain has ≥2 dead inboxes. Retire immediately.',
        resourceId: domainId,
        resourceType: 'domain',
        resourceName: domain.domain,
      });
    }
  },

  getDomainMetrics: (domainId) => get().domainMetrics.find((m) => m.domainId === domainId),

  getDomainMetricsByClient: (_clientId) => {
    // DomainHealthMetrics does not have clientId property - return all
    return get().domainMetrics;
  },

  // Alerts
  acknowledgeAlert: (alertId) => {
    set((state) => ({
      alerts: state.alerts.map((a) =>
        a.id === alertId ? { ...a, acknowledgedAt: new Date() } : a
      ),
    }));
  },

  dismissAlert: (alertId) => {
    set((state) => ({
      alerts: state.alerts.filter((a) => a.id !== alertId),
    }));
  },

  addAlert: (alertData) => {
    const alert: HealthAlert = {
      ...alertData,
      id: generateId(),
      createdAt: new Date(),
    };
    set((state) => ({
      alerts: [alert, ...state.alerts],
    }));
  },

  getActiveAlerts: () => get().alerts.filter((a) => !a.acknowledgedAt),

  getAlertsByClient: (_clientId) => {
    // HealthAlert does not have clientId property - return all
    return get().alerts;
  },

  // Kill triggers
  executeKillTrigger: async (triggerId) => {
    const trigger = get().killTriggers.find((t) => t.id === triggerId);
    if (trigger) {
      await get().killInbox(trigger.inboxId, trigger.type);

      set((state) => ({
        killTriggers: state.killTriggers.map((t) =>
          t.id === triggerId
            ? { ...t, actionTaken: 'killed' as const, resolvedAt: new Date() }
            : t
        ),
      }));
    }
  },

  dismissKillTrigger: (triggerId) => {
    set((state) => ({
      killTriggers: state.killTriggers.map((t) =>
        t.id === triggerId
          ? { ...t, actionTaken: 'dismissed' as const, resolvedAt: new Date() }
          : t
      ),
    }));
  },

  addKillTrigger: (triggerData) => {
    const trigger: KillTrigger = {
      ...triggerData,
      id: generateId(),
      detectedAt: new Date(),
      actionTaken: 'pending',
    };
    set((state) => ({
      killTriggers: [trigger, ...state.killTriggers],
    }));
  },

  getPendingTriggers: () =>
    get().killTriggers.filter((t) => t.actionTaken === 'pending'),

  getTriggersByClient: (_clientId) => {
    // KillTrigger does not have clientId property - return all
    return get().killTriggers;
  },

  // Campaign management
  quarantineCampaign: (campaignId, reason) => {
    set((state) => ({
      campaignMetrics: state.campaignMetrics.map((m) =>
        m.campaignId === campaignId
          ? {
              ...m,
              state: 'quarantined' as const,
              quarantinedAt: new Date(),
              quarantineReason: reason,
            }
          : m
      ),
    }));

    const campaign = get().campaignMetrics.find((m) => m.campaignId === campaignId);
    if (campaign) {
      get().addAlert({
        type: 'campaign_quarantined',
        severity: 'warning',
        title: `Campaign Quarantined: ${campaign.campaignName}`,
        description: reason,
        resourceId: campaignId,
        resourceType: 'campaign',
        resourceName: campaign.campaignName,
      });
    }
  },

  unquarantineCampaign: (campaignId) => {
    set((state) => ({
      campaignMetrics: state.campaignMetrics.map((m) =>
        m.campaignId === campaignId
          ? {
              ...m,
              state: 'live' as const,
              quarantinedAt: undefined,
              quarantineReason: undefined,
            }
          : m
      ),
    }));
  },

  getCampaignMetrics: (campaignId) =>
    get().campaignMetrics.find((m) => m.campaignId === campaignId),

  // Refresh all health data via composite endpoint
  refreshHealth: async (clientId) => {
    if (!clientId) return;
    set({ isLoading: true, error: null });
    try {
      const data = await api.health.getFullDashboard(clientId);

      // Map overall summary
      const summary = data.overallSummary;
      const overallSummary: OverallHealthSummary = {
        clientId: summary.clientId,
        healthScore: summary.healthScore,
        status: summary.status as 'healthy' | 'warning' | 'critical',
        statusMessage: summary.statusMessage,
        totalDomains: summary.totalDomains,
        liveDomains: summary.liveDomains,
        flaggedDomains: summary.flaggedDomains,
        deadDomains: summary.deadDomains,
        totalInboxes: summary.totalInboxes,
        liveInboxes: summary.liveInboxes,
        deadInboxes: summary.deadInboxes,
        warmingInboxes: summary.warmingInboxes,
        pendingKillTriggers: summary.pendingKillTriggers,
        activeAlerts: summary.activeAlerts,
        lastRefresh: new Date(),
      };

      // Map kill triggers
      const killTriggers: KillTrigger[] = (data.killTriggers || []).map((t) => ({
        id: t.id,
        inboxId: t.inboxId,
        inboxEmail: t.inboxEmail,
        domainId: t.domainId || '',
        domainName: t.domainName || '',
        type: t.type as KillTrigger['type'],
        severity: t.severity as KillTrigger['severity'],
        value: t.value,
        threshold: t.threshold,
        detectedAt: new Date(t.detectedAt),
        retestAt: t.retestAt ? new Date(t.retestAt) : undefined,
        resolvedAt: t.resolvedAt ? new Date(t.resolvedAt) : undefined,
        actionTaken: (t.actionTaken || 'pending') as 'killed' | 'dismissed' | 'pending',
      }));

      // Map backup capacity
      const backupCapacity: OverallBackupCapacity | null = data.backupCapacity ? {
        primary: {
          tier: 'primary' as const,
          label: data.backupCapacity.primary.label,
          count: data.backupCapacity.primary.count,
          targetCount: data.backupCapacity.primary.targetCount,
          percentage: data.backupCapacity.primary.percentage,
          status: data.backupCapacity.primary.status as 'healthy' | 'warning' | 'critical',
        },
        hotBackup: {
          tier: 'hot_backup' as const,
          label: data.backupCapacity.hotBackup.label,
          count: data.backupCapacity.hotBackup.count,
          targetCount: data.backupCapacity.hotBackup.targetCount,
          percentage: data.backupCapacity.hotBackup.percentage,
          status: data.backupCapacity.hotBackup.status as 'healthy' | 'warning' | 'critical',
        },
        warmingPipeline: {
          tier: 'warming_pipeline' as const,
          label: data.backupCapacity.warmingPipeline.label,
          count: data.backupCapacity.warmingPipeline.count,
          targetCount: data.backupCapacity.warmingPipeline.targetCount,
          percentage: data.backupCapacity.warmingPipeline.percentage,
          status: data.backupCapacity.warmingPipeline.status as 'healthy' | 'warning' | 'critical',
        },
        totalCapacity: data.backupCapacity.totalCapacity,
        activeCapacity: data.backupCapacity.activeCapacity,
        backupRatio: data.backupCapacity.backupRatio,
        overallStatus: data.backupCapacity.overallStatus as 'healthy' | 'warning' | 'critical',
      } : null;

      // Map domain metrics
      const domainMetrics: DomainHealthMetrics[] = (data.domainGrid || []).map((d) => ({
        domainId: d.domainId,
        domain: d.domain,
        state: d.state as DomainHealthMetrics['state'],
        phase: d.phase as DomainHealthMetrics['phase'],
        overallHealthScore: d.overallHealthScore,
        totalInboxes: d.totalInboxes,
        liveInboxes: d.liveInboxes,
        deadInboxes: d.deadInboxes,
        warmingInboxes: d.warmingInboxes,
        infrastructureType: d.infrastructureType ?? undefined,
        ageInDays: d.ageInDays,
        daysUntilRotation: d.daysUntilRotation,
        gmailReputation: d.gmailReputation as DomainHealthMetrics['gmailReputation'],
        microsoftReputation: d.microsoftReputation as DomainHealthMetrics['microsoftReputation'],
        lastInboxPlacement: d.lastInboxPlacement ?? undefined,
        lastSpamPlacement: d.lastSpamPlacement ?? undefined,
        createdAt: new Date(d.createdAt),
        lastHealthCheck: d.lastHealthCheck ? new Date(d.lastHealthCheck) : new Date(),
      }));

      // Map campaign metrics
      const campaignMetrics: CampaignHealthMetrics[] = (data.campaignAttribution || []).map((c) => ({
        campaignId: c.campaignId,
        campaignName: c.campaignName,
        state: c.state as CampaignHealthMetrics['state'],
        inboxesKilled7d: c.inboxesKilled7d,
        domainsAffected: c.domainsAffected,
        totalSent: c.totalSent,
        bounceCount: c.bounceCount,
        bounceRate: c.bounceRate,
        complaintCount: c.complaintCount,
        complaintRate: c.complaintRate,
        riskLevel: c.riskLevel as CampaignHealthMetrics['riskLevel'],
      }));

      // Map contamination sources
      const contaminationSources: ListContaminationSource[] = (data.contaminationSources || []).map((s) => ({
        id: s.id,
        listName: s.listName,
        campaignId: s.campaignId,
        campaignName: s.campaignName,
        totalLeads: s.totalLeads,
        bouncedLeads: s.bouncedLeads,
        bounceRate: s.bounceRate,
        sourceType: s.sourceType as ListContaminationSource['sourceType'],
        sourceProvider: s.sourceProvider ?? undefined,
        importedAt: new Date(s.importedAt),
        status: s.status as ListContaminationSource['status'],
        inboxesAffected: s.inboxesAffected,
        domainsAffected: s.domainsAffected,
      }));

      // Map ESP summaries
      const espSummaries: ESPHealthSummary[] = (data.espSummaries || []).map((e) => ({
        provider: e.provider as ESPHealthSummary['provider'],
        reputation: e.reputation as ESPHealthSummary['reputation'],
        reputationTrend: e.reputationTrend as ESPHealthSummary['reputationTrend'],
        inboxPlacementRate: e.inboxPlacementRate,
        spamPlacementRate: e.spamPlacementRate,
        promotionsPlacementRate: e.promotionsPlacementRate ?? undefined,
        spfPassing: e.spfPassing,
        dkimPassing: e.dkimPassing,
        dmarcPassing: e.dmarcPassing,
        userReportedSpamRate: e.userReportedSpamRate ?? undefined,
        ipReputation: (e.ipReputation ?? undefined) as ESPHealthSummary['ipReputation'],
        complaintRate: e.complaintRate ?? undefined,
        trapHits: e.trapHits ?? undefined,
        filterResult: (e.filterResult ?? undefined) as ESPHealthSummary['filterResult'],
        lastUpdated: new Date(e.lastUpdated),
      }));

      set({
        overallSummary,
        killTriggers,
        backupCapacity,
        domainMetrics,
        campaignMetrics,
        contaminationSources,
        espSummaries,
        isLoading: false,
        lastRefresh: new Date(),
      });
    } catch (error) {
      set({ error: (error as Error).message, isLoading: false });
    }
  },
}));
