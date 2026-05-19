/**
 * DomainsTable — Airtable-style sortable + expandable table of all domains
 * under a workspace, with each domain's inboxes nested inside.
 *
 * Designed for AE-driven monitoring: every column the operator might want to
 * sort by (kill triggers, complaints, dead count, capacity %, ESP, status) is
 * a clickable header. Clicking a domain row expands an inline inbox sub-table
 * showing per-inbox health, pool/lifecycle state, bounces, and warnings.
 *
 * Filter chips at the top scope by ESP and domain status so the operator can
 * focus on "all Google domains with complaints" or "Microsoft domains in
 * rotate-now state" without scrolling.
 *
 * Self-contained — no chart deps. Uses the same Village tokens as the rest of
 * the workspace pages.
 */
"use client";

import * as React from "react";
import { formatDistanceToNowStrict } from "date-fns";
import { ChevronRight, ChevronDown, ArrowUp, ArrowDown, AlertTriangle } from "lucide-react";
import type { WaterfallDomain } from "@/lib/types/infrastructure";
import type { InventoryInbox } from "@/lib/types/inventory";
import { cn } from "@/lib/utils";

export interface DomainsTableProps {
  domains: WaterfallDomain[];
  inboxes: InventoryInbox[];
  loading?: boolean;
  className?: string;
}

type SortKey =
  | "domain"
  | "esp"
  | "status"
  | "live"
  | "dead"
  | "connected"
  | "disconnected"
  | "complaints"
  | "blocks"
  | "capacity"
  | "recommendation";
type SortDir = "asc" | "desc";

const STATUS_TONE: Record<string, string> = {
  live: "border-moss text-moss",
  flagged: "border-honey text-honey",
  monitoring: "border-honey text-honey",
  quarantined: "border-rust text-rust",
  dead: "border-ink-soft text-ink-soft",
};

const REC_TONE: Record<string, string> = {
  healthy: "border-moss text-moss",
  monitor: "border-honey text-honey",
  consider_rotate: "border-rust text-rust",
  rotate_now: "border-rust text-rust bg-rust/10",
  none: "border-border text-ink-soft",
  not_applicable: "border-border text-ink-soft",
};

const ESP_TONE: Record<string, string> = {
  microsoft: "border-sky text-sky",
  google: "border-moss text-moss",
  entra: "border-sky text-sky",
};

const POOL_TONE: Record<string, string> = {
  deployed: "border-moss text-moss",
  warning: "border-honey text-honey",
  reserve: "border-sky text-sky",
};

export function DomainsTable({ domains, inboxes, loading, className }: DomainsTableProps) {
  const [sortKey, setSortKey] = React.useState<SortKey>("complaints");
  const [sortDir, setSortDir] = React.useState<SortDir>("desc");
  const [expanded, setExpanded] = React.useState<Set<string>>(new Set());
  const [espFilter, setEspFilter] = React.useState<"all" | "microsoft" | "google">("all");
  const [statusFilter, setStatusFilter] = React.useState<"all" | "live" | "flagged" | "dead">("all");

  // Group inboxes by domain_name so each row can render its nested set.
  const inboxesByDomain = React.useMemo(() => {
    const map = new Map<string, InventoryInbox[]>();
    for (const inbox of inboxes) {
      const key = inbox.domainName.toLowerCase();
      const arr = map.get(key) ?? [];
      arr.push(inbox);
      map.set(key, arr);
    }
    return map;
  }, [inboxes]);

  const filtered = React.useMemo(() => {
    let rows = domains;
    if (espFilter !== "all") {
      rows = rows.filter((d) => {
        const esp = (d.assignedProvider ?? "").toLowerCase();
        return espFilter === "microsoft"
          ? esp === "microsoft" || esp === "entra"
          : esp === "google";
      });
    }
    if (statusFilter !== "all") {
      rows = rows.filter((d) => {
        const status = (d.domainStatus ?? "").toLowerCase();
        if (statusFilter === "live") return status === "live";
        if (statusFilter === "flagged") return status === "flagged" || status === "monitoring" || status === "quarantined";
        if (statusFilter === "dead") return status === "dead";
        return true;
      });
    }
    return rows;
  }, [domains, espFilter, statusFilter]);

  const sorted = React.useMemo(() => {
    const cmp = (a: WaterfallDomain, b: WaterfallDomain): number => {
      let av: number | string = 0;
      let bv: number | string = 0;
      switch (sortKey) {
        case "domain": av = a.domainName; bv = b.domainName; break;
        case "esp": av = a.assignedProvider ?? ""; bv = b.assignedProvider ?? ""; break;
        case "status": av = a.domainStatus ?? ""; bv = b.domainStatus ?? ""; break;
        case "live": av = a.liveInboxCount; bv = b.liveInboxCount; break;
        case "dead": av = a.deadInboxCount; bv = b.deadInboxCount; break;
        case "connected": av = a.connectedInboxCount; bv = b.connectedInboxCount; break;
        case "disconnected": av = a.disconnectedInboxCount; bv = b.disconnectedInboxCount; break;
        case "complaints": av = a.inboxesWithComplaints ?? 0; bv = b.inboxesWithComplaints ?? 0; break;
        case "blocks": av = a.inboxesWithBlocks ?? 0; bv = b.inboxesWithBlocks ?? 0; break;
        case "capacity": av = a.capacityRemainingPct ?? 0; bv = b.capacityRemainingPct ?? 0; break;
        case "recommendation": av = recRank(a.rotationRecommendation); bv = recRank(b.rotationRecommendation); break;
      }
      if (typeof av === "string" && typeof bv === "string") {
        return sortDir === "asc" ? av.localeCompare(bv) : bv.localeCompare(av);
      }
      return sortDir === "asc" ? (av as number) - (bv as number) : (bv as number) - (av as number);
    };
    return [...filtered].sort(cmp);
  }, [filtered, sortKey, sortDir]);

  const toggle = (id: string) => {
    setExpanded((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const setSort = (key: SortKey) => {
    if (sortKey === key) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setSortKey(key);
      setSortDir("desc");
    }
  };

  if (loading && domains.length === 0) {
    return <div className="px-3 py-12 text-center text-sm text-ink-soft animate-pulse">Loading domains…</div>;
  }
  if (domains.length === 0) {
    return (
      <div className="px-3 py-12 text-center text-sm text-ink-soft border border-dashed border-border rounded-md">
        No domains for this workspace.
      </div>
    );
  }

  return (
    <div className={cn("space-y-3", className)}>
      {/* Filter chips */}
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <FilterGroup label="ESP">
          <Chip active={espFilter === "all"} onClick={() => setEspFilter("all")}>All ({domains.length})</Chip>
          <Chip active={espFilter === "microsoft"} onClick={() => setEspFilter("microsoft")}>
            Entra ({domains.filter((d) => {
              const e = (d.assignedProvider ?? "").toLowerCase();
              return e === "microsoft" || e === "entra";
            }).length})
          </Chip>
          <Chip active={espFilter === "google"} onClick={() => setEspFilter("google")}>
            Google ({domains.filter((d) => (d.assignedProvider ?? "").toLowerCase() === "google").length})
          </Chip>
        </FilterGroup>
        <FilterGroup label="Status">
          <Chip active={statusFilter === "all"} onClick={() => setStatusFilter("all")}>All</Chip>
          <Chip active={statusFilter === "live"} onClick={() => setStatusFilter("live")}>
            Live ({domains.filter((d) => d.domainStatus === "live").length})
          </Chip>
          <Chip active={statusFilter === "flagged"} onClick={() => setStatusFilter("flagged")}>
            Flagged ({domains.filter((d) => {
              const s = d.domainStatus;
              return s === "flagged" || s === "monitoring" || s === "quarantined";
            }).length})
          </Chip>
          <Chip active={statusFilter === "dead"} onClick={() => setStatusFilter("dead")}>
            Dead ({domains.filter((d) => d.domainStatus === "dead").length})
          </Chip>
        </FilterGroup>
        <span className="ml-auto text-ink-soft font-mono">
          {sorted.length} of {domains.length} shown
        </span>
      </div>

      {/* Table */}
      <div className="rounded-lg border-[1.5px] border-border-bold bg-card overflow-hidden">
        <div className="overflow-x-auto custom-scrollbar">
          <table className="w-full text-xs">
            <thead className="bg-muted/40 border-b border-border">
              <tr>
                <th className="w-6"></th>
                <SortableHeader k="domain" current={sortKey} dir={sortDir} onClick={setSort} className="text-left">
                  Domain
                </SortableHeader>
                <SortableHeader k="esp" current={sortKey} dir={sortDir} onClick={setSort} className="text-left">
                  ESP
                </SortableHeader>
                <SortableHeader k="status" current={sortKey} dir={sortDir} onClick={setSort} className="text-left">
                  Status
                </SortableHeader>
                <SortableHeader k="live" current={sortKey} dir={sortDir} onClick={setSort} className="text-right">
                  Live
                </SortableHeader>
                <SortableHeader k="connected" current={sortKey} dir={sortDir} onClick={setSort} className="text-right">
                  Conn
                </SortableHeader>
                <SortableHeader k="disconnected" current={sortKey} dir={sortDir} onClick={setSort} className="text-right">
                  Disc
                </SortableHeader>
                <SortableHeader k="dead" current={sortKey} dir={sortDir} onClick={setSort} className="text-right">
                  Dead
                </SortableHeader>
                <SortableHeader k="complaints" current={sortKey} dir={sortDir} onClick={setSort} className="text-right">
                  Cmplnt
                </SortableHeader>
                <SortableHeader k="blocks" current={sortKey} dir={sortDir} onClick={setSort} className="text-right">
                  Blocks
                </SortableHeader>
                <SortableHeader k="capacity" current={sortKey} dir={sortDir} onClick={setSort} className="text-right">
                  Cap %
                </SortableHeader>
                <SortableHeader k="recommendation" current={sortKey} dir={sortDir} onClick={setSort} className="text-left">
                  Action
                </SortableHeader>
              </tr>
            </thead>
            <tbody>
              {sorted.map((d) => {
                const isOpen = expanded.has(d.domainId);
                const inboxList = inboxesByDomain.get(d.domainName.toLowerCase()) ?? [];
                const esp = (d.assignedProvider ?? "").toLowerCase();
                const status = (d.domainStatus ?? "").toLowerCase();
                return (
                  <React.Fragment key={d.domainId}>
                    <tr
                      className={cn(
                        "border-b border-border cursor-pointer hover:bg-muted/40 transition-colors",
                        isOpen && "bg-amber/5"
                      )}
                      onClick={() => toggle(d.domainId)}
                    >
                      <td className="pl-2 py-2 text-ink-soft">
                        {isOpen
                          ? <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />
                          : <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />}
                      </td>
                      <td className="py-2 pr-2 font-mono text-foreground">
                        {d.domainName}
                        {d.hasCompromisedInboxes && (
                          <AlertTriangle className="inline-block ml-1.5 h-3 w-3 text-rust" aria-label="Compromised" />
                        )}
                      </td>
                      <td className="py-2 pr-2">
                        {esp && (
                          <span className={cn(
                            "inline-flex items-center px-1.5 h-4 rounded-sm border text-[10px] font-medium",
                            ESP_TONE[esp] ?? "border-border text-ink-soft"
                          )}>
                            {esp === "microsoft" ? "entra" : esp}
                          </span>
                        )}
                      </td>
                      <td className="py-2 pr-2">
                        <span className={cn(
                          "inline-flex items-center px-1.5 h-4 rounded-sm border text-[10px] font-medium",
                          STATUS_TONE[status] ?? "border-border text-ink-soft"
                        )}>
                          {status || "—"}
                        </span>
                      </td>
                      <td className="py-2 pr-3 text-right font-mono">{d.liveInboxCount}</td>
                      <td className="py-2 pr-3 text-right font-mono text-moss">{d.connectedInboxCount}</td>
                      <td className={cn("py-2 pr-3 text-right font-mono", d.disconnectedInboxCount > 0 && "text-rust")}>
                        {d.disconnectedInboxCount}
                      </td>
                      <td className={cn("py-2 pr-3 text-right font-mono", d.deadInboxCount > 0 && "text-ink-soft")}>
                        {d.deadInboxCount}
                      </td>
                      <td className={cn("py-2 pr-3 text-right font-mono", (d.inboxesWithComplaints ?? 0) > 0 && "text-rust")}>
                        {d.inboxesWithComplaints ?? 0}
                      </td>
                      <td className={cn("py-2 pr-3 text-right font-mono", (d.inboxesWithBlocks ?? 0) > 0 && "text-honey")}>
                        {d.inboxesWithBlocks ?? 0}
                      </td>
                      <td className="py-2 pr-3 text-right font-mono">
                        {d.capacityRemainingPct != null ? `${Math.round(d.capacityRemainingPct)}%` : "—"}
                      </td>
                      <td className="py-2 pr-3">
                        <span className={cn(
                          "inline-flex items-center px-1.5 h-4 rounded-sm border text-[10px] font-medium",
                          REC_TONE[d.rotationRecommendation] ?? "border-border text-ink-soft"
                        )}>
                          {d.rotationRecommendation.replace(/_/g, " ")}
                        </span>
                      </td>
                    </tr>
                    {isOpen && (
                      <tr className="border-b border-border bg-amber/5">
                        <td colSpan={12} className="px-3 py-2">
                          {inboxList.length === 0 ? (
                            <p className="text-[11px] text-ink-soft italic px-2">
                              No inbox detail loaded for this domain.
                              {d.totalInboxCount > 0 && (
                                <> The domain has {d.totalInboxCount} inboxes in CharmDB but they weren&apos;t
                                returned by <code>/api/inventory/inboxes/{`{id}`}</code> (likely past the pagination limit).</>
                              )}
                            </p>
                          ) : (
                            <table className="w-full text-[11px]">
                              <thead className="text-ink-soft">
                                <tr>
                                  <th className="text-left pb-1 pr-2">Inbox</th>
                                  <th className="text-left pb-1 pr-2">Pool</th>
                                  <th className="text-left pb-1 pr-2">Lifecycle</th>
                                  <th className="text-right pb-1 pr-2">Age</th>
                                  <th className="text-right pb-1 pr-2">Health</th>
                                  <th className="text-right pb-1 pr-2">HB 24h</th>
                                  <th className="text-right pb-1 pr-2">HB 7d</th>
                                  <th className="text-left pb-1">Warning</th>
                                </tr>
                              </thead>
                              <tbody>
                                {inboxList.map((inbox) => (
                                  <tr key={inbox.inboxId} className="border-t border-border/40">
                                    <td className="py-1.5 pr-2 font-mono truncate max-w-72">{inbox.email}</td>
                                    <td className="py-1.5 pr-2">
                                      {inbox.poolStatus && (
                                        <span className={cn(
                                          "inline-flex items-center px-1.5 h-4 rounded-sm border text-[10px] font-medium",
                                          POOL_TONE[inbox.poolStatus] ?? "border-border text-ink-soft"
                                        )}>
                                          {inbox.poolStatus}
                                        </span>
                                      )}
                                    </td>
                                    <td className="py-1.5 pr-2 capitalize text-ink-soft">{inbox.lifecycleStatus}</td>
                                    <td className="py-1.5 pr-2 text-right font-mono text-ink-soft">{inbox.ageDays}d</td>
                                    <td className="py-1.5 pr-2 text-right font-mono">
                                      {inbox.healthScore != null ? inbox.healthScore.toFixed(0) : "—"}
                                    </td>
                                    <td className={cn(
                                      "py-1.5 pr-2 text-right font-mono",
                                      inbox.hardBounces24h > 0 && "text-rust"
                                    )}>
                                      {inbox.hardBounces24h}
                                    </td>
                                    <td className={cn(
                                      "py-1.5 pr-2 text-right font-mono",
                                      inbox.hardBounces7d > 0 && "text-honey"
                                    )}>
                                      {inbox.hardBounces7d}
                                    </td>
                                    <td className="py-1.5 text-ink-soft">
                                      {inbox.warningReason ? (
                                        <span className="inline-flex items-center gap-1">
                                          {inbox.warningReason}
                                          {inbox.cooldownEndsAt && (
                                            <span className="text-[10px]">
                                              ({formatDistanceToNowStrict(new Date(inbox.cooldownEndsAt), { addSuffix: true })})
                                            </span>
                                          )}
                                        </span>
                                      ) : (
                                        <span className="text-[10px] italic">—</span>
                                      )}
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          )}
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function recRank(rec: WaterfallDomain["rotationRecommendation"]): number {
  switch (rec) {
    case "rotate_now": return 4;
    case "consider_rotate": return 3;
    case "monitor": return 2;
    case "healthy": return 1;
    default: return 0;
  }
}

function FilterGroup({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1">
      <span className="text-[10px] uppercase tracking-wider text-ink-soft mr-1">{label}</span>
      {children}
    </span>
  );
}

function Chip({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "inline-flex items-center h-6 px-2 rounded-sm text-[11px] font-medium border-[1.5px] transition-colors",
        active
          ? "bg-amber text-ink border-ink"
          : "bg-transparent text-ink-soft border-border hover:border-border-bold hover:text-foreground"
      )}
    >
      {children}
    </button>
  );
}

function SortableHeader({
  k,
  current,
  dir,
  onClick,
  className,
  children,
}: {
  k: SortKey;
  current: SortKey;
  dir: SortDir;
  onClick: (k: SortKey) => void;
  className?: string;
  children: React.ReactNode;
}) {
  const active = current === k;
  return (
    <th
      className={cn(
        "px-2 py-2 text-[10px] uppercase tracking-wider text-ink-soft font-medium cursor-pointer select-none hover:text-foreground transition-colors",
        className
      )}
      onClick={() => onClick(k)}
    >
      <span className="inline-flex items-center gap-1">
        {children}
        {active && (dir === "asc"
          ? <ArrowUp className="h-3 w-3" aria-hidden="true" />
          : <ArrowDown className="h-3 w-3" aria-hidden="true" />)}
      </span>
    </th>
  );
}
