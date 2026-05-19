/**
 * Screen: Workspace Infrastructure
 *
 * Trend-first AE monitoring view. The page is designed so an account executive
 * can SEE the shape of the infrastructure (volume + inbox health trajectory)
 * not just read isolated counters. When an agent later reviews this same data,
 * the AE has the context to verify the agent's conclusion.
 *
 *   ┌─ Header ─────────────────────────────────────────────────────────────┐
 *   │  Title + package context line (package · live/target · synced)       │
 *   │  Date range picker (7/14/30/90/180 + custom)                         │
 *   ├─ Volume bar chart ───────────────────────────────────────────────────┤
 *   │  Daily emails_sent (stacked by ESP when backend supports per-day     │
 *   │  ESP split; today: total volume + current-period ESP composition     │
 *   │  shown alongside for mental mapping)                                 │
 *   ├─ Trend lines ────────────────────────────────────────────────────────┤
 *   │  Inbox composition over time + kills (secondary axis)                │
 *   ├─ Pool snapshot ──────────────────────────────────────────────────────┤
 *   │  Live / Flagged (warning) / Reserve / Dead   + package gap context   │
 *   ├─ Sits in ────────────────────────────────────────────────────────────┤
 *   │  Provider + workspace locator (EmailBison today; Instantly when wired)│
 *   ├─ Operational events ─────────────────────────────────────────────────┤
 *   │  Recent kills · Disconnects needing attention · Rotation candidates  │
 *   └──────────────────────────────────────────────────────────────────────┘
 *
 * Data sources (all live production CharmDB via charm-api):
 *   • healthApi.getDailyVolumeHistory     — daily volume + inbox composition + kills
 *   • infrastructureApi.getWaterfallByClient — current ESP split for snapshot row
 *   • inventoryApi.getOverview            — pool distribution + package targets
 *   • reportsApi.getKills(window)         — recent kill events
 *   • reportsApi.getDisconnects(true)     — attention-only disconnects
 *   • reportsApi.getRotation()            — rotation candidates
 *   • getWorkspace                        — workspace name for fleet filtering + locator
 */
"use client";

import * as React from "react";
import { useParams } from "next/navigation";
import { formatDistanceToNowStrict } from "date-fns";
import {
  Activity,
  Plug,
  RotateCw,
  Clock,
  Skull,
  CheckCircle2,
  Server,
  Package,
} from "lucide-react";
import { PageHeader } from "@/components/charm";
import { VolumeBarChart } from "@/components/charm/volume-bar-chart";
import { TrendLineChart } from "@/components/charm/trend-line-chart";
import { DateRangePicker, type DateRangeValue } from "@/components/charm/date-range-picker";
import { DomainsTable } from "@/components/charm/domains-table";
import { infrastructureApi, inventoryApi, healthApi } from "@/lib/api";
import { reportsApi } from "@/lib/reports-api";
import { getWorkspace } from "@/lib/data/charm";
import type { DailyVolumeHistoryResponse } from "@/lib/types/health";
import type { ClientInfraSummary, WaterfallDomain } from "@/lib/types/infrastructure";
import type { InventoryOverview, InventoryInbox } from "@/lib/types/inventory";
import type { KillRow, DisconnectRow, RotationRow } from "@/lib/types/reports";
import { cn } from "@/lib/utils";

interface LoadedData {
  volume: DailyVolumeHistoryResponse | null;
  summary: ClientInfraSummary | null;
  inventory: InventoryOverview | null;
  kills: KillRow[];
  disconnects: DisconnectRow[];
  rotations: RotationRow[];
  workspaceName: string | null;
  packageName: string | null;
  packageInboxTarget: number | null;
  domains: WaterfallDomain[];
  inboxes: InventoryInbox[];
}

// Per migration 097, workspace_packages.daily_limit_per_inbox defaults to 20.
// Charm doesn't expose this per-workspace in the clients endpoint, so we use the
// canonical default to estimate package daily-send potential. If you customize
// daily_limit on a package, surface it via /api/clients and read it here.
const DEFAULT_DAILY_LIMIT_PER_INBOX = 20;

export default function WorkspaceInfrastructurePage() {
  const { id } = useParams<{ id: string }>();
  const [range, setRange] = React.useState<DateRangeValue>({ days: 30 });
  const [data, setData] = React.useState<LoadedData>({
    volume: null,
    summary: null,
    inventory: null,
    kills: [],
    disconnects: [],
    rotations: [],
    workspaceName: null,
    packageName: null,
    packageInboxTarget: null,
    domains: [],
    inboxes: [],
  });
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [poolView, setPoolView] = React.useState<"cards" | "table">("cards");

  React.useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const workspace = await getWorkspace(id);
        const workspaceName = workspace?.name ?? null;
        const packageName = workspace?.packageName ?? null;
        const packageInboxTarget = workspace?.packageInboxTarget ?? null;

        const [volume, waterfall, inventory, inboxesRes, killsRes, disconnectsRes, rotationsRes] =
          await Promise.all([
            healthApi.getDailyVolumeHistory(id, { days: range.days }).catch(() => null),
            infrastructureApi.getWaterfallByClient(id).catch(() => null),
            inventoryApi.getOverview(id).catch(() => null),
            inventoryApi.getInboxes(id, { limit: 500 }).catch(() => null),
            reportsApi.getKills(range.days <= 1 ? "24h" : range.days <= 7 ? "7d" : "30d").catch(() => null),
            reportsApi.getDisconnects(true).catch(() => null),
            reportsApi.getRotation().catch(() => null),
          ]);
        if (cancelled) return;

        const matchWs = (row: { workspace_name?: string | null }) =>
          !workspaceName || row.workspace_name === workspaceName;

        setData({
          volume,
          summary: waterfall?.summary ?? null,
          inventory,
          kills: (killsRes?.rows ?? []).filter(matchWs),
          disconnects: (disconnectsRes?.rows ?? []).filter(matchWs),
          rotations: (rotationsRes?.rows ?? []).filter(matchWs),
          workspaceName,
          packageName,
          packageInboxTarget,
          domains: waterfall?.domains ?? [],
          inboxes: inboxesRes?.items ?? [],
        });
        setError(null);
      } catch (err) {
        console.error("Infrastructure load failed", err);
        if (!cancelled) setError("Failed to load infrastructure — backend may be unreachable.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id, range.days]);

  const { volume, summary, inventory, kills, disconnects, rotations, packageName, packageInboxTarget, domains, inboxes } = data;

  // Subtitle: package + live/target + synced freshness, all in one line
  const packageLiveTarget = inventory && summary
    ? `${summary.totalLiveInboxes.toLocaleString()} live / ${(inventory.deployedTarget || 0).toLocaleString()} target`
    : null;
  const lastSync = volume?.endDate ? new Date(volume.endDate) : null;

  // ─── Volume delta computation ─────────────────────────────────────────────
  // CRITICAL: daily_volume_snapshots.emails_sent stores the workspace's CUMULATIVE
  // total across all campaigns as of end-of-day (sourced from EB campaign_snapshots
  // which is per-campaign lifetime totals). To show "sends added per day" we diff
  // consecutive days. First day in the window can't be diffed — we drop it from the
  // displayed series so every bar represents a real day-over-day delta.
  //
  // This is a frontend correction. The proper fix is in sync_modules/daily_snapshot.py
  // (store deltas, not cumulative) — see chart note below. Math.max guards against
  // backfill cases where a later snapshot has a lower cumulative than its predecessor.
  const cumSnapshots = volume?.snapshots ?? [];
  const dailySends = cumSnapshots.slice(1).map((s, i) => ({
    date: s.date,
    sent: Math.max(0, s.emailsSent - cumSnapshots[i].emailsSent),
    capacity: s.dailyCapacityAvailable,
  }));
  const periodTotalSent = cumSnapshots.length > 1
    ? Math.max(0, cumSnapshots[cumSnapshots.length - 1].emailsSent - cumSnapshots[0].emailsSent)
    : 0;
  const avgDailySent = dailySends.length > 0
    ? Math.round(periodTotalSent / dailySends.length)
    : 0;
  const avgDailyCapacity = dailySends.length > 0
    ? Math.round(dailySends.reduce((sum, d) => sum + d.capacity, 0) / dailySends.length)
    : 0;
  const realUtilizationPct = avgDailyCapacity > 0
    ? (avgDailySent / avgDailyCapacity) * 100
    : 0;

  // ─── Capacity math: separate production-only ceiling from total quota ────
  //
  // CRITICAL distinction (verified against production CharmDB):
  //   • Active production capacity = active inboxes × daily_limit
  //     The realistic ceiling for production campaign sends. Incubating inboxes
  //     are excluded because their daily_limit is largely consumed by EmailBison's
  //     warmup automation, not by production campaigns.
  //   • Total daily quota = SUM(daily_limit) across ALL connected live inboxes
  //     (includes incubating). This is what `daily_capacity_available` returns
  //     from the snapshot. Useful for context — it shows how much warming
  //     pipeline is available — but it is NOT a production ceiling.
  //
  // The bars only contain production campaign sends (from campaign_snapshots).
  // Warmup volume is not captured per-day by EmailBison so it never appears in
  // the bars. Comparing bars to total-quota overstates the "gap" by ~2× because
  // it pits production-only volume against production+warmup capacity.
  //
  // See docs: api/routes/health.py:1789-1792 (daily_limit shared between warmup
  // and production) and sync_modules/daily_snapshot.py:94 (capacity sum).
  const activeProductionCapacity = inventory
    ? (inventory.activeCount + inventory.warningCount) * DEFAULT_DAILY_LIMIT_PER_INBOX
    : 0;
  const packagePotentialDaily = packageInboxTarget && packageInboxTarget > 0
    ? packageInboxTarget * DEFAULT_DAILY_LIMIT_PER_INBOX
    : null;
  const productionUtilizationPct = activeProductionCapacity > 0
    ? (avgDailySent / activeProductionCapacity) * 100
    : null;
  const targetVsActualPct = packagePotentialDaily && packagePotentialDaily > 0
    ? (avgDailySent / packagePotentialDaily) * 100
    : null;
  const capacityVsTargetPct = packagePotentialDaily && packagePotentialDaily > 0
    ? (activeProductionCapacity / packagePotentialDaily) * 100
    : null;

  return (
    <div className="space-y-6">
      <PageHeader
        kicker="Workspace infrastructure"
        title="Infrastructure"
        subtitle={
          loading
            ? "Loading…"
            : [
                packageName ? `Package · ${packageName}` : null,
                packageLiveTarget,
                lastSync ? `Synced ${formatDistanceToNowStrict(lastSync, { addSuffix: true })}` : null,
              ].filter(Boolean).join("  ·  ")
        }
        actions={
          <DateRangePicker value={range} onChange={setRange} />
        }
      />

      {error && (
        <div className="rounded-md border-[1.5px] border-rust bg-rust/10 px-4 py-3 text-sm text-rust">
          {error}
        </div>
      )}

      {/* ───── Volume bar chart vs capacity vs package target ───── */}
      <section aria-labelledby="volume-chart" className="rounded-lg border-[1.5px] border-border-bold bg-card p-5 space-y-3">
        <header className="flex items-end justify-between gap-3 flex-wrap">
          <div>
            <h2 id="volume-chart" className="text-base font-semibold">
              Daily sending volume vs production capacity{packagePotentialDaily ? " vs package target" : ""}
            </h2>
            <p className="text-xs text-ink-soft mt-0.5">
              Last {dailySends.length} day{dailySends.length === 1 ? "" : "s"}
              {periodTotalSent > 0 && (
                <> · <span className="font-mono text-foreground">{periodTotalSent.toLocaleString()}</span> sent</>
              )}
              {avgDailySent > 0 && (
                <> · <span className="font-mono text-foreground">{avgDailySent.toLocaleString()}</span>/day avg</>
              )}
              {productionUtilizationPct != null && productionUtilizationPct > 0 && (
                <> · <span className={cn(
                  "font-mono",
                  productionUtilizationPct >= 70 ? "text-moss" :
                  productionUtilizationPct >= 40 ? "text-honey" : "text-rust"
                )}>{productionUtilizationPct.toFixed(0)}%</span> of production capacity</>
              )}
              {targetVsActualPct != null && (
                <> · <span className={cn(
                  "font-mono",
                  targetVsActualPct >= 70 ? "text-moss" :
                  targetVsActualPct >= 40 ? "text-honey" : "text-rust"
                )}>{targetVsActualPct.toFixed(0)}%</span> of package target</>
              )}
            </p>
          </div>
          <CurrentEspSplit summary={summary} loading={loading} />
        </header>
        <VolumeBarChart
          data={dailySends.map((d) => ({
            date: d.date,
            series: { sent: d.sent },
          }))}
          seriesConfig={[
            { key: "sent", label: "Daily sends", color: "var(--amber)" },
          ]}
          overlayLines={
            dailySends.length > 0
              ? [
                  {
                    label: "Total daily quota (incl. warming)",
                    color: "var(--moss)",
                    values: dailySends.map((d) => d.capacity),
                    dashed: true,
                  },
                ]
              : []
          }
          referenceLines={[
            ...(activeProductionCapacity > 0
              ? [
                  {
                    label: "Production capacity",
                    value: activeProductionCapacity,
                    color: "var(--moss)",
                    dashed: false,
                  },
                ]
              : []),
            ...(packagePotentialDaily
              ? [
                  {
                    label: "Package target",
                    value: packagePotentialDaily,
                    color: "var(--sky)",
                    dashed: true,
                  },
                ]
              : []),
          ]}
          emptyMessage={
            loading
              ? "Loading volume…"
              : cumSnapshots.length < 2
                ? "Need at least 2 daily snapshots to compute day-over-day deltas. The sync worker captures snapshots at 00:05 UTC."
                : "No volume snapshots yet."
          }
        />
        <div className="space-y-1.5">
          <p className="text-[11px] text-ink-soft leading-relaxed">
            <span className="font-medium">How to read this:</span> bars are daily campaign sends. The{" "}
            <span className="text-moss font-medium">solid green line</span> is{" "}
            <span className="font-medium">production capacity</span>
            {inventory && (
              <> — <span className="font-mono">{(inventory.activeCount + inventory.warningCount).toLocaleString()}</span> active &amp;
              warning inboxes × <span className="font-mono">{DEFAULT_DAILY_LIMIT_PER_INBOX}</span>/day ={" "}
              <span className="font-mono">{activeProductionCapacity.toLocaleString()}</span>/day</>
            )}.
            The <span className="text-moss font-medium">dotted line</span> is total daily quota including the{" "}
            {inventory?.incubatingCount ?? 0} incubating inboxes — their quota is mostly consumed by EmailBison&apos;s
            warmup automation, so bars compare against the solid line, not the dotted one.
            {packagePotentialDaily && (
              <>
                {" "}The <span className="text-sky font-medium">blue dashed line</span> is package target (
                <span className="font-mono">{packageInboxTarget}</span> ×{" "}
                <span className="font-mono">{DEFAULT_DAILY_LIMIT_PER_INBOX}</span> ={" "}
                <span className="font-mono">{packagePotentialDaily.toLocaleString()}</span>/day).
                {capacityVsTargetPct != null && capacityVsTargetPct < 90 && (
                  <>
                    {" "}Production capacity is at{" "}
                    <span className="font-mono text-honey">{capacityVsTargetPct.toFixed(0)}%</span>{" "}
                    of target — graduate incubating inboxes to active to close the gap.
                  </>
                )}
              </>
            )}
            {!packagePotentialDaily && (
              <> No package target shown — this workspace isn&apos;t assigned to a package in CharmDB.</>
            )}
          </p>
          <p className="text-[11px] text-ink-soft italic leading-relaxed">
            Bars = day-over-day deltas of cumulative campaign totals from EmailBison; warmup volume is NOT in the bars
            (EmailBison only exposes warmup as aggregate, not per-day). Production capacity uses the package default
            of <span className="font-mono">{DEFAULT_DAILY_LIMIT_PER_INBOX}</span>/day per inbox — if you&apos;ve
            customized <code>workspace_packages.daily_limit_per_inbox</code> the actual ceiling differs.
            Per-ESP daily split not yet captured in <code>daily_volume_snapshots</code>; current-period ESP composition shown above right.
          </p>
        </div>
      </section>

      {/* ───── Trend lines ───── */}
      <section aria-labelledby="trend-chart" className="rounded-lg border-[1.5px] border-border-bold bg-card p-5 space-y-3">
        <header>
          <h2 id="trend-chart" className="text-base font-semibold">Inbox health trajectory</h2>
          <p className="text-xs text-ink-soft mt-0.5">
            Live + dead inbox counts over time, with daily kill events on the secondary axis.
          </p>
        </header>
        <TrendLineChart
          data={(volume?.snapshots ?? []).map((s) => ({
            date: s.date,
            series: {
              live: s.liveInboxes,
              incubating: s.incubatingInboxes,
              dead: s.deadInboxes,
              kills: s.killsThatDay,
            },
          }))}
          seriesConfig={[
            { key: "live", label: "Live", color: "var(--moss)" },
            { key: "incubating", label: "Incubating", color: "var(--sky)" },
            { key: "dead", label: "Dead (cumulative)", color: "var(--ink-soft)", dashed: true },
            { key: "kills", label: "Kills that day", color: "var(--rust)", secondaryScale: true },
          ]}
          formatSecondary={(n) => Math.round(n).toString()}
          emptyMessage={loading ? "Loading trajectory…" : "No daily history yet."}
        />
      </section>

      {/* ───── Pool snapshot — toggle between aggregate cards and domains table ───── */}
      <section aria-labelledby="pool-snapshot">
        <header className="mb-3 flex items-end justify-between gap-3 flex-wrap">
          <div>
            <h2 id="pool-snapshot" className="text-base font-semibold inline-flex items-center gap-2">
              <Package className="h-4 w-4 text-copper" aria-hidden="true" />
              {poolView === "cards" ? "Pool snapshot" : "Domains & inboxes"}
            </h2>
            <p className="text-xs text-ink-soft mt-0.5">
              {poolView === "cards"
                ? <>Where every inbox sits right now. <strong>Live</strong> + <strong>Flagged</strong> + <strong>Reserve</strong> are pool states; <strong>Dead</strong> exited the pool.</>
                : <>Every domain under this workspace, sortable by any column. Click a row to expand its inboxes.</>
              }
            </p>
          </div>
          <div className="flex items-center gap-3 flex-wrap">
            {poolView === "cards" && inventory && <PackageGap inventory={inventory} />}
            <PoolViewToggle value={poolView} onChange={setPoolView} />
          </div>
        </header>
        {poolView === "cards" ? (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <PoolCard
              label="Live"
              sub="deployed (sending)"
              value={inventory?.deployedCount ?? 0}
              target={inventory?.deployedTarget ?? 0}
              tone="moss"
              loading={loading}
            />
            <PoolCard
              label="Flagged"
              sub="warning (in cooldown)"
              value={inventory?.warningCount ?? 0}
              tone={inventory && inventory.warningCount > 0 ? "honey" : "ink"}
              loading={loading}
            />
            <PoolCard
              label="Reserve"
              sub="ready to promote"
              value={inventory?.reserveCount ?? 0}
              target={inventory?.reserveTarget ?? 0}
              tone="sky"
              loading={loading}
            />
            <PoolCard
              label="Dead"
              sub={`${inventory?.killedByTrigger ?? 0} killed · ${inventory?.deactivated ?? 0} deactivated`}
              value={inventory?.deadCount ?? 0}
              tone="ink-soft"
              loading={loading}
            />
          </div>
        ) : (
          <DomainsTable domains={domains} inboxes={inboxes} loading={loading} />
        )}
      </section>

      {/* ───── Sits in (provider locator) ───── */}
      <section aria-labelledby="sits-in">
        <h2 id="sits-in" className="text-base font-semibold inline-flex items-center gap-2 mb-3">
          <Server className="h-4 w-4 text-ink-soft" aria-hidden="true" />
          Sits in
        </h2>
        <div className="rounded-lg border-[1.5px] border-border-bold bg-card divide-y divide-border">
          <ProviderRow
            connected
            providerLabel="EmailBison"
            workspaceLabel={data.workspaceName ?? "—"}
            inboxCount={summary?.totalInboxes ?? 0}
            loading={loading}
          />
          <ProviderRow
            connected={false}
            providerLabel="Instantly"
            workspaceLabel="not connected"
            note="Multi-provider per client lands when migration 123 + Instantly extraction ship."
          />
        </div>
      </section>

      {/* ───── Operational events ───── */}
      <section aria-labelledby="ops-events">
        <h2 id="ops-events" className="text-base font-semibold inline-flex items-center gap-2 mb-3">
          <Activity className="h-4 w-4 text-amber" aria-hidden="true" />
          Operational events
        </h2>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
          <KillsPanel rows={kills} loading={loading} />
          <DisconnectsPanel rows={disconnects} loading={loading} />
          <RotationPanel rows={rotations} loading={loading} />
        </div>
      </section>
    </div>
  );
}

// ─── Header support ──────────────────────────────────────────────────────────

function CurrentEspSplit({
  summary,
  loading,
}: {
  summary: ClientInfraSummary | null;
  loading: boolean;
}) {
  if (loading || !summary) return null;
  const entraSent = summary.entra.inboxesLive * (summary.entra.dailyCapacity / Math.max(summary.entra.inboxesLive, 1));
  const googleSent = summary.google.inboxesLive * (summary.google.dailyCapacity / Math.max(summary.google.inboxesLive, 1));
  const total = entraSent + googleSent;
  if (total === 0) return null;
  const entraPct = (entraSent / total) * 100;
  const googlePct = 100 - entraPct;
  return (
    <div className="text-right">
      <p className="text-[10px] uppercase tracking-wider text-ink-soft mb-1">Current-period ESP capacity</p>
      <div className="inline-flex items-center gap-3 text-xs font-mono">
        <span className="inline-flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-sm bg-sky" aria-hidden="true" />
          Entra {entraPct.toFixed(0)}%
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-sm bg-moss" aria-hidden="true" />
          Google {googlePct.toFixed(0)}%
        </span>
      </div>
    </div>
  );
}

function PackageGap({ inventory }: { inventory: InventoryOverview }) {
  const target = inventory.deployedTarget || 0;
  const deployed = inventory.deployedCount;
  const gap = Math.max(0, target - deployed);
  const reserve = inventory.reserveCount;
  const reserveCovers = gap === 0 ? "covered" : reserve >= gap ? `reserve covers (${reserve} ≥ ${gap})` : `short ${gap - reserve}`;
  return (
    <div className="text-right text-xs font-mono">
      {gap === 0 ? (
        <span className="text-moss inline-flex items-center gap-1">
          <CheckCircle2 className="h-3 w-3" aria-hidden="true" />
          at target
        </span>
      ) : (
        <>
          <span className="text-honey">{gap} below target</span>
          <span className="text-ink-soft"> · {reserveCovers}</span>
        </>
      )}
    </div>
  );
}

// ─── Pool view toggle ────────────────────────────────────────────────────────

function PoolViewToggle({
  value,
  onChange,
}: {
  value: "cards" | "table";
  onChange: (v: "cards" | "table") => void;
}) {
  return (
    <div className="inline-flex items-center gap-0.5 rounded-md border-[1.5px] border-border bg-card p-0.5">
      {(["cards", "table"] as const).map((v) => (
        <button
          key={v}
          type="button"
          onClick={() => onChange(v)}
          className={cn(
            "h-7 px-2.5 rounded-sm text-xs font-medium transition-colors capitalize",
            value === v
              ? "bg-amber text-ink border border-ink"
              : "text-ink-soft hover:text-foreground hover:bg-muted"
          )}
        >
          {v === "cards" ? "Cards" : "Domains table"}
        </button>
      ))}
    </div>
  );
}

// ─── Pool card ───────────────────────────────────────────────────────────────

function PoolCard({
  label,
  sub,
  value,
  target,
  tone,
  loading,
}: {
  label: string;
  sub: string;
  value: number;
  target?: number;
  tone: "moss" | "honey" | "sky" | "ink" | "ink-soft";
  loading?: boolean;
}) {
  const toneClass = {
    moss: "text-moss",
    honey: "text-honey",
    sky: "text-sky",
    ink: "text-foreground",
    "ink-soft": "text-ink-soft",
  }[tone];
  const pct = target && target > 0 ? Math.min(100, (value / target) * 100) : null;
  return (
    <div className="rounded-lg border-[1.5px] border-border-bold bg-card p-4 space-y-2">
      <div className="flex items-baseline justify-between gap-2">
        <p className="text-xs uppercase tracking-wider text-ink-soft">{label}</p>
        {target ? <p className="text-[10px] font-mono text-ink-soft">/ {target.toLocaleString()}</p> : null}
      </div>
      <p className={cn("text-3xl font-mono", toneClass, loading && "opacity-40")}>
        {value.toLocaleString()}
      </p>
      {pct !== null && (
        <div className="h-1.5 rounded-full bg-muted overflow-hidden border border-border">
          <div
            className={cn(
              "h-full",
              tone === "moss" && "bg-moss",
              tone === "sky" && "bg-sky",
            )}
            style={{ width: `${pct}%` }}
          />
        </div>
      )}
      <p className="text-[10px] text-ink-soft truncate" title={sub}>{sub}</p>
    </div>
  );
}

// ─── Provider locator row ────────────────────────────────────────────────────

function ProviderRow({
  connected,
  providerLabel,
  workspaceLabel,
  inboxCount,
  note,
  loading,
}: {
  connected: boolean;
  providerLabel: string;
  workspaceLabel: string;
  inboxCount?: number;
  note?: string;
  loading?: boolean;
}) {
  return (
    <div className="flex items-center gap-3 px-4 py-3">
      <span
        className={cn(
          "h-2.5 w-2.5 rounded-full shrink-0",
          connected ? "bg-moss" : "bg-ink-soft opacity-40"
        )}
        aria-hidden="true"
      />
      <div className="flex-1 min-w-0">
        <p className="text-sm">
          <span className="font-medium">{providerLabel}</span>
          <span className="text-ink-soft"> · {workspaceLabel}</span>
        </p>
        {note && <p className="text-[11px] text-ink-soft italic mt-0.5">{note}</p>}
      </div>
      {connected && inboxCount != null && (
        <span className="text-xs font-mono text-ink-soft shrink-0">
          {loading ? "…" : `${inboxCount.toLocaleString()} inboxes`}
        </span>
      )}
    </div>
  );
}

// ─── Event panels ────────────────────────────────────────────────────────────

function KillsPanel({ rows, loading }: { rows: KillRow[]; loading: boolean }) {
  return (
    <Panel title="Recent kills" icon={Skull} iconTone="text-rust" count={rows.length}>
      {loading ? (
        <PanelLoading />
      ) : rows.length === 0 ? (
        <PanelEmpty message="No kills in this window." />
      ) : (
        <ul className="divide-y divide-border max-h-80 overflow-y-auto custom-scrollbar">
          {rows.slice(0, 12).map((row, i) => (
            <li key={`${row.email_address ?? "?"}-${i}`} className="px-3 py-2 text-xs">
              <div className="flex items-center justify-between gap-2 min-w-0">
                <span className="font-mono truncate min-w-0">{row.email_address}</span>
                <span className={cn(
                  "shrink-0 inline-flex items-center px-1.5 h-4 rounded-sm border text-[10px] font-medium",
                  row.esp === "microsoft" ? "border-sky text-sky" : "border-moss text-moss"
                )}>
                  {row.esp}
                </span>
              </div>
              <div className="flex items-center justify-between gap-2 mt-0.5 text-ink-soft">
                <span className="font-mono truncate min-w-0">{row.kill_trigger}</span>
                <span className="shrink-0 font-mono">{row.killed_at ? formatDistanceToNowStrict(new Date(row.killed_at), { addSuffix: true }) : ""}</span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

function DisconnectsPanel({ rows, loading }: { rows: DisconnectRow[]; loading: boolean }) {
  const attentionRows = rows.filter((r) => r.needs_attention !== false);
  return (
    <Panel title="Disconnects" icon={Plug} iconTone="text-honey" count={attentionRows.length}>
      {loading ? (
        <PanelLoading />
      ) : attentionRows.length === 0 ? (
        <PanelEmpty message="All inboxes operational." />
      ) : (
        <ul className="divide-y divide-border max-h-80 overflow-y-auto custom-scrollbar">
          {attentionRows.slice(0, 12).map((row, i) => (
            <li key={`${row.email_address ?? "?"}-${i}`} className="px-3 py-2 text-xs">
              <div className="flex items-center justify-between gap-2 min-w-0">
                <span className="font-mono truncate min-w-0">{row.email_address}</span>
                <span className={cn(
                  "shrink-0 inline-flex items-center px-1.5 h-4 rounded-sm border text-[10px] font-medium",
                  row.esp === "microsoft" ? "border-sky text-sky" : "border-moss text-moss"
                )}>
                  {row.esp}
                </span>
              </div>
              <div className="flex items-center justify-between gap-2 mt-0.5 text-ink-soft">
                <span className="font-mono">pool: {row.pool_status ?? "—"} · daily: {row.daily_limit?.toLocaleString() ?? 0}</span>
                <span className="shrink-0 font-mono text-rust">
                  {row.hours_disconnected ? `${Math.round(row.hours_disconnected)}h` : ""}
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

function RotationPanel({ rows, loading }: { rows: RotationRow[]; loading: boolean }) {
  return (
    <Panel title="Rotation candidates" icon={RotateCw} iconTone="text-amber" count={rows.length}>
      {loading ? (
        <PanelLoading />
      ) : rows.length === 0 ? (
        <PanelEmpty message="No domains need rotation." />
      ) : (
        <ul className="divide-y divide-border max-h-80 overflow-y-auto custom-scrollbar">
          {rows.slice(0, 12).map((row, i) => (
            <li key={`${row.domain_name ?? "?"}-${i}`} className="px-3 py-2 text-xs">
              <div className="flex items-center justify-between gap-2 min-w-0">
                <span className="font-mono truncate min-w-0">{row.domain_name}</span>
                <span className="shrink-0 font-mono text-rust">
                  {row.death_rate_pct != null ? `${row.death_rate_pct.toFixed(0)}%` : ""}
                </span>
              </div>
              <div className="flex items-center justify-between gap-2 mt-0.5 text-ink-soft">
                <span className="truncate min-w-0">
                  {row.rotation_reason.replace(/_/g, " ")}
                  {(row.spam_complaints > 0 || row.provider_blocks > 0) && (
                    <span className="font-mono ml-1.5">
                      ({row.spam_complaints > 0 && `${row.spam_complaints} spam`}
                      {row.spam_complaints > 0 && row.provider_blocks > 0 && " · "}
                      {row.provider_blocks > 0 && `${row.provider_blocks} block`})
                    </span>
                  )}
                </span>
                {row.most_recent_kill && (
                  <span className="shrink-0 font-mono">
                    {formatDistanceToNowStrict(new Date(row.most_recent_kill), { addSuffix: true })}
                  </span>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

function Panel({
  title,
  icon: Icon,
  iconTone,
  count,
  children,
}: {
  title: string;
  icon: React.ComponentType<{ className?: string }>;
  iconTone: string;
  count: number;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-lg border-[1.5px] border-border-bold bg-card">
      <header className="px-3 py-2.5 border-b border-border flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold inline-flex items-center gap-2">
          <Icon className={cn("h-4 w-4", iconTone)} aria-hidden="true" />
          {title}
        </h3>
        <span className="text-xs font-mono text-ink-soft">{count}</span>
      </header>
      {children}
    </section>
  );
}

function PanelLoading() {
  return <div className="px-3 py-6 text-center text-xs text-ink-soft animate-pulse">Loading…</div>;
}

function PanelEmpty({ message }: { message: string }) {
  return (
    <div className="px-3 py-6 text-center text-xs text-ink-soft inline-flex items-center justify-center gap-1.5 w-full">
      <CheckCircle2 className="h-3.5 w-3.5 text-moss" aria-hidden="true" />
      {message}
    </div>
  );
}
