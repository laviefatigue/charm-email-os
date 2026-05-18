/**
 * Screen: Workspace Assets
 * Every task_document produced for this workspace. Filterable by doc_key.
 * Click → opens the JIT report viewer (/tasks/[id]/documents/[key]/view).
 * Each row has inline export (.md download).
 */
"use client";

import * as React from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { format, formatDistanceToNowStrict } from "date-fns";
import { FileText, Download, ExternalLink } from "lucide-react";
import { taskApi } from "@/lib/api";
import { PageHeader } from "@/components/charm";
import type { TaskDocument } from "@/lib/types";
import { cn } from "@/lib/utils";

type DocumentRow = TaskDocument & { taskTitle?: string };

const DOC_KEY_LABELS: Record<string, string> = {
  analysis: "Analysis",
  research_report: "Research report",
  review_summary: "Review summary",
  repo_op: "Repo op",
  plan: "Plan",
  notes: "Notes",
};

const DOC_KEY_TONE: Record<string, string> = {
  analysis: "border-amber text-amber",
  research_report: "border-sky text-sky",
  review_summary: "border-sage text-sage",
  repo_op: "border-copper text-copper",
  plan: "border-honey text-honey",
  notes: "border-ink-soft text-ink-soft",
};

export default function WorkspaceAssetsPage() {
  const { id } = useParams<{ id: string }>();
  const [docs, setDocs] = React.useState<DocumentRow[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [filterKey, setFilterKey] = React.useState<string>("all");

  React.useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const all = await taskApi.listAllDocuments({ workspaceId: id, limit: 300 });
        if (cancelled) return;
        setDocs(all as DocumentRow[]);
      } catch (err) {
        console.error(err);
        if (!cancelled) setError("Failed to load assets");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id]);

  const filtered = filterKey === "all" ? docs : docs.filter((d) => d.docKey === filterKey);
  const keyCounts = React.useMemo(() => {
    const c: Record<string, number> = { all: docs.length };
    for (const d of docs) c[d.docKey] = (c[d.docKey] ?? 0) + 1;
    return c;
  }, [docs]);

  const handleDownload = (d: DocumentRow) => {
    const filename = `${d.docKey}-${d.id.slice(0, 8)}.md`;
    const titleHeader = d.title ? `# ${d.title}\n\n` : "";
    const blob = new Blob([titleHeader + d.body], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <div>
      <PageHeader
        kicker="Workspace assets"
        title="Generated reports"
        subtitle={
          loading
            ? "Loading…"
            : `${docs.length} document${docs.length === 1 ? "" : "s"} across all tasks. Click to view, download .md, or open in print view for PDF.`
        }
      />

      {error && (
        <div className="mb-4 p-3 rounded-md border-[1.5px] border-rust bg-rust/10 text-rust text-sm">
          {error}
        </div>
      )}

      {/* Filter chips */}
      <div className="flex flex-wrap items-center gap-2 mb-5">
        {(["all", "analysis", "research_report", "review_summary", "repo_op", "plan", "notes"]).map((k) => {
          const count = keyCounts[k] ?? 0;
          const active = filterKey === k;
          return (
            <button
              key={k}
              type="button"
              onClick={() => setFilterKey(k)}
              className={cn(
                "inline-flex items-center gap-2 h-7 px-3 rounded-sm text-xs font-medium border-[1.5px] transition-colors",
                active
                  ? "bg-amber text-ink border-ink"
                  : "bg-transparent text-ink-soft border-border hover:border-border-bold hover:text-foreground"
              )}
            >
              {k === "all" ? "All" : DOC_KEY_LABELS[k] ?? k}
              <span className="font-mono">{count}</span>
            </button>
          );
        })}
      </div>

      {loading ? (
        <div className="text-sm text-ink-soft py-12 text-center">Loading…</div>
      ) : filtered.length === 0 ? (
        <div className="flex flex-col items-center justify-center text-center gap-3 py-16 px-6 rounded-xl border border-dashed border-border bg-muted/30">
          <span className="inline-flex items-center justify-center h-12 w-12 rounded-md bg-amber/15 text-amber border-[1.5px] border-amber">
            <FileText className="h-6 w-6" aria-hidden="true" />
          </span>
          <h3 className="text-xl">No reports yet</h3>
          <p className="text-sm text-ink-soft max-w-md">
            Once you (or an agent) save a document on a task — analysis, research
            report, review summary — it appears here. Permanent archive,
            exportable, future agent runs can cite as context.
          </p>
        </div>
      ) : (
        <ul className="space-y-3">
          {filtered.map((d) => (
            <li
              key={d.id}
              className="flex items-start gap-3 p-4 rounded-lg border-[1.5px] border-border-bold bg-card hover:shadow-flat-sm transition-shadow"
            >
              <span
                className={cn(
                  "inline-flex items-center px-2 h-5 rounded-sm border-[1.5px] text-[10px] font-medium uppercase tracking-wider shrink-0 mt-0.5",
                  DOC_KEY_TONE[d.docKey] ?? "border-border text-ink-soft"
                )}
              >
                {DOC_KEY_LABELS[d.docKey] ?? d.docKey}
              </span>
              <div className="flex-1 min-w-0">
                <Link
                  href={`/tasks/${d.taskId}/documents/${d.docKey}/view`}
                  className="text-base font-medium hover:underline focus-visible:underline truncate block"
                  title={d.title ?? d.docKey}
                >
                  {d.title ?? d.docKey}
                </Link>
                {d.taskTitle && (
                  <Link
                    href={`/tasks/${d.taskId}`}
                    className="text-xs text-copper hover:underline focus-visible:underline truncate block"
                  >
                    From task: {d.taskTitle}
                  </Link>
                )}
                <p
                  className="text-xs text-ink-soft font-mono mt-1"
                  title={format(new Date(d.updatedAt), "yyyy-MM-dd HH:mm:ss")}
                >
                  rev {d.latestRevisionNumber} · updated {formatDistanceToNowStrict(new Date(d.updatedAt), { addSuffix: true })}
                </p>
              </div>
              <div className="flex items-center gap-1.5 shrink-0">
                <Link
                  href={`/tasks/${d.taskId}/documents/${d.docKey}/view`}
                  className="inline-flex items-center gap-1 h-7 px-2 rounded-sm border-[1.5px] border-border-bold text-xs font-medium hover:bg-amber hover:text-ink transition-colors"
                  title="Open report viewer"
                >
                  <ExternalLink className="h-3 w-3" aria-hidden="true" />
                  View
                </Link>
                <button
                  type="button"
                  onClick={() => handleDownload(d)}
                  className="inline-flex items-center gap-1 h-7 px-2 rounded-sm border-[1.5px] border-border text-xs font-medium text-ink-soft hover:border-border-bold hover:text-foreground transition-colors"
                  title="Download .md"
                >
                  <Download className="h-3 w-3" aria-hidden="true" />
                  .md
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
