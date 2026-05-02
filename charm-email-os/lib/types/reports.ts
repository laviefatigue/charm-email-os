export interface ReportEnvelope<T> {
  report_name: string;
  generated_at: string;
  row_count: number;
  rows: T[];
}

export interface DisconnectRow {
  workspace_name: string;
  domain_name: string | null;
  email_address: string;
  esp: string | null;
  connection_status: string;
  disconnected_at: string | null;
  hours_disconnected: number | null;
  needs_attention: boolean;
  pool_status: string | null;
  warmup_enabled: boolean | null;
  daily_limit: number | null;
  total_sends_7d: number;
}

export interface KillRow {
  workspace_name: string;
  domain_name: string | null;
  email_address: string;
  kill_trigger: string;
  kill_reason: string | null;
  killed_at: string;
  esp: string | null;
  pool_status_before_kill: string | null;
  total_sends_7d: number;
  hard_bounces_24h: number;
}

export interface RotationRow {
  workspace_name: string;
  domain_name: string;
  total_inboxes: number;
  dead_inboxes: number;
  spam_complaints: number;
  provider_blocks: number;
  death_rate_pct: number | null;
  rotation_reason: 'spam_compromised' | 'provider_blocked' | 'all_dead' | 'high_death_rate' | 'monitor';
  most_recent_kill: string | null;
}

export interface CancelCandidateRow {
  workspace_name: string;
  audit_date: string;
  domain_name: string;
  domain_id: string;
  total_inboxes: number;
  dead_inboxes: number;
  live_connected: number;
  live_disconnected: number;
  dead_connected: number;
  dead_disconnected: number;
  most_recent_kill: string | null;
  recency_eligible: boolean;
}

export interface QuarantinedRow {
  workspace_name: string;
  domain_name: string | null;
  email_address: string;
  is_quarantined: boolean;
  quarantine_reason: string | null;
  inventory_pool_status: string | null;
  inbox_state: string;
  connection_status: string;
  created_at: string;
  updated_at: string;
}

export interface IncubationStuckRow {
  workspace_name: string;
  domain_name: string | null;
  email_address: string;
  inventory_lifecycle_status: string;
  inventory_pool_status: string | null;
  warmup_started_at: string | null;
  created_at: string;
  calendar_days_in_incubation: number;
  last_synced_at: string | null;
}

export interface CapacityRow {
  workspace_name: string;
  total_inboxes: number;
  live_connected: number;
  live_disconnected: number;
  dead: number;
  health_pct: number | null;
  spam_compromised_domains: number;
  target_live: number | null;
  most_recent_event: string | null;
}

export type ReportSlug =
  | 'disconnects'
  | 'kills'
  | 'rotation'
  | 'cancel-candidates'
  | 'quarantined'
  | 'incubation-stuck'
  | 'capacity';
