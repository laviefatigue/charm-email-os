/**
 * Reports API client — fleet-wide CSV-style operator queues.
 *
 * Kept in its own file (rather than appended to lib/api.ts) so the reports
 * feature is reviewable as a standalone slice. Mirrors the conventions of
 * the existing api.ts named-method-object pattern.
 */
import type {
  ReportEnvelope,
  DisconnectRow,
  KillRow,
  RotationRow,
  CancelCandidateRow,
  QuarantinedRow,
  IncubationStuckRow,
  CapacityRow,
  ReportSlug,
} from './types/reports';

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ||
  'http://ccssgc4gowsog04wck400o0w.31.97.142.123.sslip.io';

class APIError extends Error {
  constructor(public status: number, public statusText: string, public detail?: string) {
    super(detail || `API Error: ${status} ${statusText}`);
    this.name = 'APIError';
  }
}

async function fetchJson<T>(endpoint: string): Promise<T> {
  const url = `${API_BASE}${endpoint}`;
  const userEmail =
    typeof window !== 'undefined' ? sessionStorage.getItem('user_email') : null;

  const res = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...(userEmail && { 'X-User-Email': userEmail }),
    },
  });
  if (!res.ok) {
    let detail: string | undefined;
    try {
      const data = await res.json();
      if (typeof data.detail === 'string') detail = data.detail;
    } catch {
      // ignore
    }
    throw new APIError(res.status, res.statusText, detail);
  }
  return res.json();
}

export const reportsApi = {
  async getDisconnects(attentionOnly = true): Promise<ReportEnvelope<DisconnectRow>> {
    return fetchJson<ReportEnvelope<DisconnectRow>>(
      `/api/reports/disconnects?attention_only=${attentionOnly}`,
    );
  },
  async getKills(window: '24h' | '7d' | '30d' = '24h'): Promise<ReportEnvelope<KillRow>> {
    return fetchJson<ReportEnvelope<KillRow>>(`/api/reports/kills?window=${window}`);
  },
  async getRotation(): Promise<ReportEnvelope<RotationRow>> {
    return fetchJson<ReportEnvelope<RotationRow>>('/api/reports/rotation');
  },
  async getCancelCandidates(): Promise<ReportEnvelope<CancelCandidateRow>> {
    return fetchJson<ReportEnvelope<CancelCandidateRow>>('/api/reports/cancel-candidates');
  },
  async getQuarantined(): Promise<ReportEnvelope<QuarantinedRow>> {
    return fetchJson<ReportEnvelope<QuarantinedRow>>('/api/reports/quarantined');
  },
  async getIncubationStuck(minDays = 14): Promise<ReportEnvelope<IncubationStuckRow>> {
    return fetchJson<ReportEnvelope<IncubationStuckRow>>(
      `/api/reports/incubation-stuck?min_calendar_days=${minDays}`,
    );
  },
  async getCapacity(): Promise<ReportEnvelope<CapacityRow>> {
    return fetchJson<ReportEnvelope<CapacityRow>>('/api/reports/capacity');
  },
  csvUrl(slug: ReportSlug, params: Record<string, string> = {}): string {
    const qs = new URLSearchParams({ format: 'csv', ...params }).toString();
    return `${API_BASE}/api/reports/${slug}?${qs}`;
  },
};
