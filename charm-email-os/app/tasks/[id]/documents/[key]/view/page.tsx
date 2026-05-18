/**
 * Screen: JIT Report Viewer
 * Full-screen reading mode for a single task_document. Print-styled — operator
 * can ctrl-P → save as PDF → email to client. Also supports .md download.
 *
 * Standalone layout (no Village sidebar) so print captures only the content.
 */
"use client";

import * as React from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { format } from "date-fns";
import { ChevronLeft, Download, Printer, Loader2 } from "lucide-react";
import { taskApi } from "@/lib/api";
import { MarkdownView } from "@/components/charm";
import type { TaskDetail, TaskDocument } from "@/lib/types";
import { cn } from "@/lib/utils";

export default function ReportViewerPage() {
  const params = useParams<{ id: string; key: string }>();
  const taskId = params.id;
  const docKey = params.key;

  const [task, setTask] = React.useState<TaskDetail | null>(null);
  const [doc, setDoc] = React.useState<TaskDocument | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const t = await taskApi.get(taskId);
        if (cancelled) return;
        setTask(t);
        const d = t.documents.find((doc) => doc.docKey === docKey);
        if (!d) {
          setError(`No document with key "${docKey}" on this task`);
        } else {
          setDoc(d);
        }
      } catch (err) {
        console.error(err);
        if (!cancelled) setError("Failed to load report");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [taskId, docKey]);

  const handleDownload = () => {
    if (!doc) return;
    const filename = `${docKey}-${doc.id.slice(0, 8)}.md`;
    const titleHeader = doc.title ? `# ${doc.title}\n\n` : "";
    const blob = new Blob([titleHeader + doc.body], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const handlePrint = () => window.print();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background text-sm text-ink-soft">
        <Loader2 className="h-4 w-4 animate-spin mr-2" aria-hidden="true" />
        Loading report…
      </div>
    );
  }

  if (error || !doc || !task) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-background gap-3">
        <p className="text-rust">{error ?? "Document not found"}</p>
        <Link href={`/tasks/${taskId}`} className="text-copper hover:underline text-sm">
          ← Back to task
        </Link>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      {/* Toolbar — hidden on print */}
      <div className="report-toolbar sticky top-0 z-10 bg-card border-b border-border print:hidden">
        <div className="max-w-3xl mx-auto px-6 py-3 flex items-center justify-between gap-3">
          <Link
            href={`/tasks/${taskId}`}
            className="inline-flex items-center gap-1 text-xs text-ink-soft hover:text-foreground transition-colors"
          >
            <ChevronLeft className="h-3 w-3" aria-hidden="true" />
            Back to task
          </Link>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleDownload}
              className={cn(
                "inline-flex items-center gap-1.5 h-8 px-3 rounded-sm text-xs font-medium",
                "bg-transparent text-ink border-[1.5px] border-border-bold hover:bg-muted transition-colors"
              )}
            >
              <Download className="h-3 w-3" aria-hidden="true" />
              Download .md
            </button>
            <button
              type="button"
              onClick={handlePrint}
              className={cn(
                "inline-flex items-center gap-1.5 h-8 px-3 rounded-sm text-xs font-medium",
                "bg-amber text-ink border-[1.5px] border-border-bold hover:shadow-flat-sm transition-shadow"
              )}
            >
              <Printer className="h-3 w-3" aria-hidden="true" />
              Print / Save PDF
            </button>
          </div>
        </div>
      </div>

      {/* Document */}
      <article className="report-article max-w-3xl mx-auto px-8 py-12">
        {/* Branded header — visible on print */}
        <header className="mb-8 pb-6 border-b-[1.5px] border-border-bold">
          <p className="text-xs font-mono uppercase tracking-wider text-ink-soft">
            {docKey.replace("_", " ")}
            {task.workspaceName && <span> · {task.workspaceName}</span>}
          </p>
          <h1 className="text-4xl mt-2">{doc.title ?? task.title}</h1>
          {!doc.title && (
            <p className="text-sm text-ink-soft mt-1">Task: {task.title}</p>
          )}
          <p className="text-xs text-ink-soft mt-3 font-mono">
            Last updated {format(new Date(doc.updatedAt), "yyyy-MM-dd HH:mm")}
            {" · "}revision {doc.latestRevisionNumber}
          </p>
        </header>

        <MarkdownView body={doc.body} variant="article" />

        {/* Cited context — visible on print */}
        {doc.citedContext && doc.citedContext.length > 0 && (
          <section className="mt-10 pt-6 border-t border-border">
            <h2 className="font-heading text-xl mb-3">Sources</h2>
            <ul className="space-y-1.5 text-sm">
              {doc.citedContext.map((c) => (
                <li key={`${c.path}-${c.commitSha ?? "x"}`} className="flex items-start gap-2">
                  <span className="font-mono text-ink">{c.path}</span>
                  {c.commitSha && (
                    <span className="font-mono text-xs text-ink-soft">@{c.commitSha.slice(0, 7)}</span>
                  )}
                  {c.relevance && <span className="text-ink-soft">— {c.relevance}</span>}
                </li>
              ))}
            </ul>
          </section>
        )}

        {/* Footer — visible on print */}
        <footer className="mt-12 pt-4 border-t border-border text-xs text-ink-soft font-mono flex flex-wrap items-center justify-between gap-2">
          <span>Charm · {task.workspaceName ?? "Workspace"}</span>
          <span>Document ID: {doc.id}</span>
        </footer>
      </article>

      {/* Print stylesheet — clean, white, no colors-as-info */}
      <style jsx global>{`
        @media print {
          body {
            background: white !important;
            color: #1a1a1a !important;
          }
          .report-toolbar {
            display: none !important;
          }
          .report-article {
            max-width: 100% !important;
            padding: 0 !important;
          }
          @page {
            margin: 1in;
          }
        }
      `}</style>
    </div>
  );
}
