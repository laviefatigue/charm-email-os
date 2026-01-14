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
    set({ isLoading: true, error: null });
    try {
      const data = await api.health.getOverview(clientId);
      // Map HealthOverview fields to OverallHealthSummary
      set({
        overallSummary: {
          clientId: data.clientId,
          healthScore: Math.round(100 - (data.deadInboxes / Math.max(data.totalInboxes, 1)) * 100),
          status: data.deadInboxes > 5 ? 'critical' : data.deadInboxes > 0 ? 'warning' : 'healthy',
          statusMessage: data.deadInboxes > 0
            ? `${data.deadInboxes} dead inbox(es) detected`
            : 'All inboxes healthy',
          totalDomains: data.totalDomains,
          liveDomains: data.cleanDomains,
          flaggedDomains: data.flaggedDomains,
          deadDomains: 0,
          totalInboxes: data.totalInboxes,
          liveInboxes: data.healthyInboxes,
          deadInboxes: data.deadInboxes,
          warmingInboxes: data.warningInboxes,
          pendingKillTriggers: get().killTriggers.filter(t => t.actionTaken === 'pending').length,
          activeAlerts: get().alerts.filter(a => !a.acknowledgedAt).length,
          lastRefresh: new Date(),
        },
        isLoading: false,
        lastRefresh: new Date(),
      });
    } catch (error) {
      set({ error: (error as Error).message, isLoading: false });
    }
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
    // api.health.getKillTriggers does not exist - use local state only
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

  // Refresh all health data
  refreshHealth: async (clientId) => {
    set({ isLoading: true, error: null });
    try {
      if (clientId) {
        await get().fetchHealthOverview(clientId);
      }
      set({ lastRefresh: new Date(), isLoading: false });
    } catch (error) {
      set({ error: (error as Error).message, isLoading: false });
    }
  },
}));
