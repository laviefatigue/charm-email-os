// Type definitions for Charm Executive Dashboard

export interface Infrastructure {
  total_inboxes: number;
  live_inboxes: number;
  dead_inboxes: number;
  avg_health_score: number;
  flagged_domains: number;
  clean_domains: number;
  health_distribution: {
    healthy: number;
    good: number;
    warning: number;
    critical: number;
    total: number;
  };
  lifecycle_distribution: {
    deployed: number;
    reserve: number;
    incubating: number;
    warning: number;
  };
  providers: Array<{
    name: string;
    live_count: number;
    dead_count: number;
    avg_health_score: number;
  }>;
  last_sync: string;
  sync_source: string;
}

export interface KillVelocity {
  totalDeaths7d: number;
  totalDeaths30d: number;
  trend: 'up' | 'down' | 'stable';
  weeklyData: Array<{
    week: string;
    deaths: number;
  }>;
}

export interface KillBreakdown {
  total_kills: number;
  by_trigger: Array<{
    trigger: string;
    count: number;
    percentage: number;
  }>;
}

export interface VolumeHistory {
  snapshots: Array<{
    date: string;
    emails_sent: number;
    daily_capacity_available: number;
    live_inboxes: number;
  }>;
}

export interface Client {
  id: string;
  name: string;
  created_at: string;
}

export interface DashboardData {
  infrastructure: Infrastructure;
  killVelocity: KillVelocity | null;
  killBreakdown: KillBreakdown | null;
  volumeHistory: VolumeHistory | null;
  client: Client | null;
  clientId: string;
  fetchedAt: string;
}
