/**
 * Screen: Task detail
 * Conversation (comments) · Documents (keyed reports) · Activity (lifecycle).
 */
"use client";

import * as React from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { format, formatDistanceToNowStrict } from "date-fns";
import { toast } from "sonner";
import {
  ChevronLeft,
  MessageSquare,
  FileText,
  ScrollText,
  Send,
  Bot,
  User,
  Plus,
  Flame,
  ChevronUp,
  Minus,
  ChevronDown,
} from "lucide-react";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PageHeader, StatusPill, type StatusKind } from "@/components/charm";
import { taskApi, agentApi } from "@/lib/api";
import type {
  Agent,
  Task,
  TaskComment,
  TaskDetail,
  TaskDocument,
  TaskPriority,
  TaskStatus,
} from "@/lib/types";
import { cn } from "@/lib/utils";

const STATUSES: { value: TaskStatus; label: string }[] = [
  { value: "backlog", label: "Backlog" },
  { value: "todo", label: "Todo" },
  { value: "in_progress", label: "In progress" },
  { value: "in_review", label: "In review" },
  { value: "done", label: "Done" },
  { value: "blocked", label: "Blocked" },
];

const PRIORITIES: { value: TaskPriority; label: string; Icon: React.ComponentType<{ className?: string }>; color: string }[] = [
  { value: "urgent", label: "Urgent", Icon: Flame, color: "text-rust" },
  { value: "high", label: "High", Icon: ChevronUp, color: "text-honey" },
  { value: "medium", label: "Medium", Icon: Minus, color: "text-ink-soft" },
  { value: "low", label: "Low", Icon: ChevronDown, color: "text-ink-soft" },
];

const STATUS_PILL_MAP: Record<TaskStatus, StatusKind> = {
  backlog: "dead",
  todo: "incubating",
  in_progress: "live",
  in_review: "drift",
  done: "live",
  blocked: "burned",
};

type Tab = "conversation" | "documents" | "activity";

export default function TaskDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [detail, setDetail] = React.useState<TaskDetail | null>(null);
  const [agents, setAgents] = React.useState<Agent[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [tab, setTab] = React.useState<Tab>("conversation");

  const refetch = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [d, ag] = await Promise.all([
        taskApi.get(id),
        agentApi.list({ activeOnly: true }).then((r) => r.items),
      ]);
      setDetail(d);
      setAgents(ag);
    } catch (err) {
      console.error(err);
      setError("Failed to load task");
    } finally {
      setLoading(false);
    }
  }, [id]);

  React.useEffect(() => {
    refetch();
  }, [refetch]);

  if (loading && !detail) {
    return (
      <div className="px-8 py-8 max-w-6xl mx-auto text-sm text-ink-soft">
        Loading task…
      </div>
    );
  }

  if (error || !detail) {
    return (
      <div className="px-8 py-8 max-w-6xl mx-auto">
        <p className="text-rust">{error ?? "Task not found"}</p>
        <Link href="/tasks" className="text-copper hover:underline text-sm mt-2 inline-block">
          ← Back to tasks
        </Link>
      </div>
    );
  }

  const priorityMeta = PRIORITIES.find((p) => p.value === detail.priority)!;
  const pillKind = STATUS_PILL_MAP[detail.status];

  const handleStatusChange = async (newStatus: TaskStatus) => {
    try {
      await taskApi.update(detail.id, { status: newStatus, actorLabel: "admin" });
      toast.success(`Status → ${newStatus.replace("_", " ")}`);
      refetch();
    } catch {
      toast.error("Failed to update status");
    }
  };

  const handleAssign = async (agentId: string) => {
    try {
      await taskApi.update(detail.id, {
        assigneeAgentId: agentId || null,
        actorLabel: "admin",
      });
      toast.success(agentId ? "Reassigned" : "Unassigned");
      refetch();
    } catch {
      toast.error("Failed to update assignee");
    }
  };

  const handlePriorityChange = async (priority: TaskPriority) => {
    try {
      await taskApi.update(detail.id, { priority, actorLabel: "admin" });
      toast.success(`Priority → ${priority}`);
      refetch();
    } catch {
      toast.error("Failed to update priority");
    }
  };

  return (
    <div className="px-8 py-8 max-w-6xl mx-auto">
      <Link
        href="/tasks"
        className="inline-flex items-center gap-1 text-xs text-ink-soft hover:text-foreground mb-3 transition-colors"
      >
        <ChevronLeft className="h-3 w-3" aria-hidden="true" />
        All tasks
      </Link>

      <PageHeader
        kicker={
          detail.workspaceName ? `Workspace · ${detail.workspaceName}` : "Cross-workspace task"
        }
        title={detail.title}
        subtitle={detail.description ?? undefined}
        actions={
          <div className="flex items-center gap-2">
            <StatusPill kind={pillKind} label={detail.status.replace("_", " ")} />
            <span className={cn("inline-flex items-center gap-1 text-sm font-medium", priorityMeta.color)}>
              <priorityMeta.Icon className="h-4 w-4" aria-hidden="true" />
              {priorityMeta.label}
            </span>
          </div>
        }
      />

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-6">
        {/* Main column — tabs */}
        <div className="min-w-0">
          <div className="flex items-center gap-1 mb-4 border-b border-border">
            {(
              [
                { id: "conversation", label: "Conversation", Icon: MessageSquare, count: detail.comments.length },
                { id: "documents", label: "Documents", Icon: FileText, count: detail.documents.length },
                { id: "activity", label: "Activity", Icon: ScrollText },
              ] as const
            ).map((t) => {
              const active = tab === t.id;
              return (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => setTab(t.id as Tab)}
                  className={cn(
                    "inline-flex items-center gap-1.5 px-3 py-2 text-sm font-medium transition-colors border-b-[1.5px]",
                    active
                      ? "border-amber text-foreground"
                      : "border-transparent text-ink-soft hover:text-foreground"
                  )}
                >
                  <t.Icon className="h-4 w-4" aria-hidden="true" />
                  {t.label}
                  {"count" in t && t.count !== undefined && (
                    <span className="font-mono text-xs text-ink-soft">{t.count}</span>
                  )}
                </button>
              );
            })}
          </div>

          {tab === "conversation" && (
            <ConversationTab
              taskId={detail.id}
              comments={detail.comments}
              onPosted={refetch}
            />
          )}
          {tab === "documents" && (
            <DocumentsTab
              taskId={detail.id}
              documents={detail.documents}
              onChanged={refetch}
            />
          )}
          {tab === "activity" && <ActivityTab task={detail} />}
        </div>

        {/* Right rail — meta + actions */}
        <aside className="space-y-4">
          <div className="rounded-lg border-[1.5px] border-border-bold bg-card p-4 space-y-3">
            <RailField label="Status">
              <select
                value={detail.status}
                onChange={(e) => handleStatusChange(e.target.value as TaskStatus)}
                className={cn(
                  "w-full h-9 rounded-md border-[1.5px] border-border bg-background px-3 text-sm",
                  "focus-visible:border-ring focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
                )}
              >
                {STATUSES.map((s) => (
                  <option key={s.value} value={s.value}>
                    {s.label}
                  </option>
                ))}
              </select>
            </RailField>

            <RailField label="Priority">
              <select
                value={detail.priority}
                onChange={(e) => handlePriorityChange(e.target.value as TaskPriority)}
                className={cn(
                  "w-full h-9 rounded-md border-[1.5px] border-border bg-background px-3 text-sm",
                  "focus-visible:border-ring focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
                )}
              >
                {PRIORITIES.map((p) => (
                  <option key={p.value} value={p.value}>
                    {p.label}
                  </option>
                ))}
              </select>
            </RailField>

            <RailField label="Assignee">
              <select
                value={detail.assigneeAgentId ?? ""}
                onChange={(e) => handleAssign(e.target.value)}
                className={cn(
                  "w-full h-9 rounded-md border-[1.5px] border-border bg-background px-3 text-sm",
                  "focus-visible:border-ring focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
                )}
              >
                <option value="">— Unassigned —</option>
                {agents.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.title} ({a.name})
                  </option>
                ))}
              </select>
            </RailField>

            {detail.dueAt && (
              <RailField label="Due">
                <p className="text-sm font-mono">{format(new Date(detail.dueAt), "yyyy-MM-dd HH:mm")}</p>
              </RailField>
            )}

            <RailField label="Source">
              <p className="text-sm capitalize">
                {detail.source}
                {detail.inboundOrigin && (
                  <span className="block text-xs text-ink-soft mt-0.5">{detail.inboundOrigin}</span>
                )}
              </p>
            </RailField>

            <RailField label="Created">
              <p className="text-xs text-ink-soft font-mono" title={format(new Date(detail.createdAt), "yyyy-MM-dd HH:mm:ss")}>
                {formatDistanceToNowStrict(new Date(detail.createdAt), { addSuffix: true })}
              </p>
            </RailField>
          </div>

          {detail.children.length > 0 && (
            <div className="rounded-lg border-[1.5px] border-border bg-card p-4">
              <h4 className="text-sm font-medium mb-2">Child tasks ({detail.children.length})</h4>
              <ul className="space-y-1">
                {detail.children.map((c) => (
                  <li key={c.id}>
                    <Link
                      href={`/tasks/${c.id}`}
                      className="text-xs text-copper hover:underline"
                    >
                      {c.title}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}

function RailField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <Label className="text-xs uppercase tracking-wider text-ink-soft">{label}</Label>
      {children}
    </div>
  );
}

// ─── Conversation tab ────────────────────────────────────────────────────────

function ConversationTab({
  taskId,
  comments,
  onPosted,
}: {
  taskId: string;
  comments: TaskComment[];
  onPosted: () => void;
}) {
  const [body, setBody] = React.useState("");
  const [posting, setPosting] = React.useState(false);

  const handlePost = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!body.trim()) return;
    setPosting(true);
    try {
      await taskApi.addComment(taskId, { bodyMarkdown: body.trim(), actorLabel: "admin" });
      setBody("");
      toast.success("Comment posted");
      onPosted();
    } catch {
      toast.error("Failed to post comment");
    } finally {
      setPosting(false);
    }
  };

  return (
    <div className="space-y-4">
      {comments.length === 0 ? (
        <div className="text-sm text-ink-soft text-center py-10 border border-dashed border-border rounded-md">
          No comments yet. Start the conversation — use @AgentName to mention an agent.
        </div>
      ) : (
        <ul className="space-y-3">
          {comments.map((c) => (
            <CommentRow key={c.id} comment={c} />
          ))}
        </ul>
      )}

      <form onSubmit={handlePost} className="space-y-2 pt-4 border-t border-border">
        <Label htmlFor="new-comment">Add comment</Label>
        <Textarea
          id="new-comment"
          rows={3}
          value={body}
          onChange={(e) => setBody(e.target.value)}
          placeholder="Markdown. @DataAnalyst @Researcher @DayAIReviewer @GitHubAdmin to mention."
        />
        <div className="flex justify-end">
          <button
            type="submit"
            disabled={posting || !body.trim()}
            className={cn(
              "inline-flex items-center gap-1.5 h-9 px-4 rounded-md text-sm font-medium",
              "bg-amber text-ink border-[1.5px] border-border-bold hover:shadow-flat-sm transition-shadow",
              "disabled:opacity-50 disabled:cursor-not-allowed"
            )}
          >
            <Send className="h-4 w-4" aria-hidden="true" />
            {posting ? "Posting…" : "Post comment"}
          </button>
        </div>
      </form>
    </div>
  );
}

function CommentRow({ comment }: { comment: TaskComment }) {
  const isAgent = comment.actorType === "agent";
  const Icon = isAgent ? Bot : User;
  return (
    <li className="rounded-md border border-border bg-muted/20 p-3">
      <div className="flex items-center gap-2 text-xs text-ink-soft mb-2">
        <span className={cn("inline-flex items-center justify-center h-5 w-5 rounded-sm border", isAgent ? "bg-copper text-cream-light border-copper" : "border-border text-ink")}>
          <Icon className="h-3 w-3" aria-hidden="true" />
        </span>
        <span className="font-medium text-foreground">{comment.actorDisplay ?? "Unknown"}</span>
        <span title={format(new Date(comment.createdAt), "yyyy-MM-dd HH:mm:ss")}>
          {formatDistanceToNowStrict(new Date(comment.createdAt), { addSuffix: true })}
        </span>
      </div>
      <div className="text-sm whitespace-pre-wrap">{comment.bodyMarkdown}</div>
    </li>
  );
}

// ─── Documents tab ───────────────────────────────────────────────────────────

const DEFAULT_DOC_KEYS = [
  { key: "analysis", label: "Analysis" },
  { key: "research_report", label: "Research report" },
  { key: "review_summary", label: "Review summary" },
  { key: "repo_op", label: "Repo op log" },
  { key: "plan", label: "Plan" },
  { key: "notes", label: "Notes" },
];

function DocumentsTab({
  taskId,
  documents,
  onChanged,
}: {
  taskId: string;
  documents: TaskDocument[];
  onChanged: () => void;
}) {
  const [editingKey, setEditingKey] = React.useState<string | null>(null);
  const [draftKey, setDraftKey] = React.useState("");
  const [draftTitle, setDraftTitle] = React.useState("");
  const [draftBody, setDraftBody] = React.useState("");
  const [draftSummary, setDraftSummary] = React.useState("");
  const [saving, setSaving] = React.useState(false);
  const [newOpen, setNewOpen] = React.useState(false);

  const startEdit = (doc: TaskDocument) => {
    setEditingKey(doc.docKey);
    setDraftKey(doc.docKey);
    setDraftTitle(doc.title ?? "");
    setDraftBody(doc.body);
    setDraftSummary("");
    setNewOpen(false);
  };

  const startNew = () => {
    setEditingKey(null);
    setNewOpen(true);
    setDraftKey("");
    setDraftTitle("");
    setDraftBody("");
    setDraftSummary("");
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    const targetKey = editingKey ?? draftKey.trim();
    if (!targetKey || !draftBody.trim()) return;
    setSaving(true);
    try {
      await taskApi.upsertDocument(taskId, targetKey, {
        title: draftTitle || undefined,
        body: draftBody,
        changeSummary: draftSummary || undefined,
      });
      toast.success(editingKey ? "Document updated" : "Document created");
      setEditingKey(null);
      setNewOpen(false);
      setDraftKey("");
      setDraftBody("");
      setDraftSummary("");
      onChanged();
    } catch {
      toast.error("Failed to save document");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-4">
      {documents.length === 0 && !newOpen && (
        <div className="text-sm text-ink-soft text-center py-10 border border-dashed border-border rounded-md">
          No documents yet. Reports go here — keyed by purpose (analysis, research_report,
          review_summary, repo_op).
        </div>
      )}

      <ul className="space-y-3">
        {documents.map((doc) => {
          const isEditing = editingKey === doc.docKey;
          return (
            <li key={doc.id} className="rounded-lg border-[1.5px] border-border-bold bg-card overflow-hidden">
              <div className="flex items-center justify-between gap-2 px-4 py-2.5 border-b border-border bg-muted/30">
                <div className="min-w-0">
                  <p className="text-sm font-medium truncate">
                    {doc.title ?? doc.docKey}
                  </p>
                  <p className="font-mono text-xs text-ink-soft truncate">
                    {doc.docKey} · rev {doc.latestRevisionNumber}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => (isEditing ? setEditingKey(null) : startEdit(doc))}
                  className="inline-flex items-center gap-1 px-2 py-1 text-xs font-medium rounded-sm border border-border-bold hover:bg-muted transition-colors"
                >
                  {isEditing ? "Cancel" : "Edit"}
                </button>
              </div>
              {isEditing ? (
                <DocumentEditor
                  title={draftTitle}
                  body={draftBody}
                  summary={draftSummary}
                  onTitleChange={setDraftTitle}
                  onBodyChange={setDraftBody}
                  onSummaryChange={setDraftSummary}
                  onSubmit={handleSave}
                  submitting={saving}
                  submitLabel="Save revision"
                />
              ) : (
                <div className="p-4 text-sm whitespace-pre-wrap font-mono leading-relaxed bg-card">
                  {doc.body || <em className="text-ink-soft">Empty</em>}
                </div>
              )}
            </li>
          );
        })}
      </ul>

      {newOpen ? (
        <div className="rounded-lg border-[1.5px] border-border-bold bg-card overflow-hidden">
          <div className="flex items-center justify-between gap-2 px-4 py-2.5 border-b border-border bg-muted/30">
            <p className="text-sm font-medium">New document</p>
            <button
              type="button"
              onClick={() => setNewOpen(false)}
              className="text-xs text-ink-soft hover:text-foreground"
            >
              Cancel
            </button>
          </div>
          <DocumentEditor
            keyValue={draftKey}
            onKeyChange={setDraftKey}
            title={draftTitle}
            body={draftBody}
            summary={draftSummary}
            onTitleChange={setDraftTitle}
            onBodyChange={setDraftBody}
            onSummaryChange={setDraftSummary}
            onSubmit={handleSave}
            submitting={saving}
            submitLabel="Create document"
            keyOptions={DEFAULT_DOC_KEYS}
            existingKeys={documents.map((d) => d.docKey)}
          />
        </div>
      ) : (
        <button
          type="button"
          onClick={startNew}
          className={cn(
            "w-full inline-flex items-center justify-center gap-1.5 h-9 px-4 rounded-md text-sm font-medium",
            "border-[1.5px] border-dashed border-border hover:border-border-bold hover:bg-muted transition-colors"
          )}
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
          New document
        </button>
      )}
    </div>
  );
}

function DocumentEditor({
  keyValue,
  onKeyChange,
  title,
  body,
  summary,
  onTitleChange,
  onBodyChange,
  onSummaryChange,
  onSubmit,
  submitting,
  submitLabel,
  keyOptions,
  existingKeys = [],
}: {
  keyValue?: string;
  onKeyChange?: (v: string) => void;
  title: string;
  body: string;
  summary: string;
  onTitleChange: (v: string) => void;
  onBodyChange: (v: string) => void;
  onSummaryChange: (v: string) => void;
  onSubmit: (e: React.FormEvent) => void;
  submitting: boolean;
  submitLabel: string;
  keyOptions?: { key: string; label: string }[];
  existingKeys?: string[];
}) {
  const availableOptions = keyOptions?.filter((o) => !existingKeys.includes(o.key)) ?? [];

  return (
    <form onSubmit={onSubmit} className="p-4 space-y-3">
      {onKeyChange !== undefined && (
        <div className="space-y-1.5">
          <Label htmlFor="doc-key">Document key</Label>
          <div className="flex gap-2">
            <Input
              id="doc-key"
              value={keyValue ?? ""}
              onChange={(e) => onKeyChange(e.target.value)}
              placeholder="analysis | research_report | review_summary | repo_op | plan | notes"
              required
              className="flex-1"
            />
            {availableOptions.length > 0 && (
              <select
                onChange={(e) => onKeyChange(e.target.value)}
                value=""
                className={cn(
                  "h-9 rounded-md border-[1.5px] border-border bg-background px-2 text-sm w-32",
                  "focus-visible:border-ring focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
                )}
              >
                <option value="">Suggest…</option>
                {availableOptions.map((o) => (
                  <option key={o.key} value={o.key}>
                    {o.label}
                  </option>
                ))}
              </select>
            )}
          </div>
        </div>
      )}
      <div className="space-y-1.5">
        <Label htmlFor="doc-title">Title (optional)</Label>
        <Input
          id="doc-title"
          value={title}
          onChange={(e) => onTitleChange(e.target.value)}
          placeholder="e.g. Burn velocity analysis — Hypertide Q2"
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="doc-body">Body (markdown)</Label>
        <Textarea
          id="doc-body"
          value={body}
          onChange={(e) => onBodyChange(e.target.value)}
          rows={10}
          required
          className="font-mono text-sm"
          placeholder="# Findings&#10;&#10;..."
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="doc-summary">Change summary (optional)</Label>
        <Input
          id="doc-summary"
          value={summary}
          onChange={(e) => onSummaryChange(e.target.value)}
          placeholder="What changed in this revision?"
        />
      </div>
      <div className="flex justify-end">
        <button
          type="submit"
          disabled={submitting}
          className={cn(
            "inline-flex items-center gap-1.5 h-9 px-4 rounded-md text-sm font-medium",
            "bg-amber text-ink border-[1.5px] border-border-bold hover:shadow-flat-sm transition-shadow",
            "disabled:opacity-50 disabled:cursor-not-allowed"
          )}
        >
          {submitting ? "Saving…" : submitLabel}
        </button>
      </div>
    </form>
  );
}

// ─── Activity tab ────────────────────────────────────────────────────────────

function ActivityTab({ task }: { task: Task }) {
  type Event = { id: string; ts: Date; label: string; detail?: string };
  const events: Event[] = [];
  events.push({
    id: "created",
    ts: new Date(task.createdAt),
    label: "Task created",
    detail: task.source === "inbound" ? `inbound · ${task.inboundOrigin ?? ""}` : task.source,
  });
  if (task.startedAt) {
    events.push({
      id: "started",
      ts: new Date(task.startedAt),
      label: "Started",
    });
  }
  if (task.checkoutAt) {
    events.push({
      id: "checkout",
      ts: new Date(task.checkoutAt),
      label: "Checked out",
    });
  }
  if (task.closedAt) {
    events.push({
      id: "closed",
      ts: new Date(task.closedAt),
      label: task.status === "done" ? "Completed" : "Blocked",
    });
  }
  if (
    task.updatedAt !== task.createdAt &&
    task.updatedAt !== task.startedAt &&
    task.updatedAt !== task.closedAt
  ) {
    events.push({
      id: "updated",
      ts: new Date(task.updatedAt),
      label: "Updated",
    });
  }
  events.sort((a, b) => b.ts.getTime() - a.ts.getTime());

  return (
    <ul className="rounded-lg border-[1.5px] border-border-bold bg-card overflow-hidden">
      {events.map((e) => (
        <li
          key={e.id}
          className="grid grid-cols-[140px_1fr] gap-3 px-3 py-2.5 border-b border-border last:border-b-0 text-sm"
        >
          <time
            dateTime={e.ts.toISOString()}
            className="font-mono text-xs text-ink-soft whitespace-nowrap"
          >
            {format(e.ts, "yyyy-MM-dd HH:mm")}
          </time>
          <div className="min-w-0">
            <p className="text-foreground">{e.label}</p>
            {e.detail && <p className="text-xs text-ink-soft">{e.detail}</p>}
          </div>
        </li>
      ))}
    </ul>
  );
}
