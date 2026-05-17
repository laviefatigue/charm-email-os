/**
 * NewTaskModal — admin creates a task, picks workspace + assignee + priority.
 * POST /api/tasks · refetch list on success.
 */
"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { taskApi, agentApi } from "@/lib/api";
import { getWorkspaces } from "@/lib/data/charm";
import type {
  Agent,
  TaskCreate,
  TaskPriority,
  TaskSource,
} from "@/lib/types";
import type { WorkspaceCardData } from "@/components/charm";
import { cn } from "@/lib/utils";

const PRIORITIES: { value: TaskPriority; label: string }[] = [
  { value: "low", label: "Low" },
  { value: "medium", label: "Medium" },
  { value: "high", label: "High" },
  { value: "urgent", label: "Urgent" },
];

const SOURCES: { value: TaskSource; label: string }[] = [
  { value: "operator", label: "Internal (AE)" },
  { value: "inbound", label: "Inbound (client)" },
];

interface WorkspaceOption {
  id: string;
  name: string;
}

export interface NewTaskModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Pre-fill workspace (e.g. when opened from a workspace detail page) */
  defaultWorkspaceId?: string;
  /** Pre-fill assignee */
  defaultAssigneeAgentId?: string;
  onCreated?: (taskId: string) => void;
}

export function NewTaskModal({
  open,
  onOpenChange,
  defaultWorkspaceId,
  defaultAssigneeAgentId,
  onCreated,
}: NewTaskModalProps) {
  const router = useRouter();
  const [title, setTitle] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [workspaceId, setWorkspaceId] = React.useState<string>(defaultWorkspaceId ?? "");
  const [assigneeAgentId, setAssigneeAgentId] = React.useState<string>(
    defaultAssigneeAgentId ?? ""
  );
  const [priority, setPriority] = React.useState<TaskPriority>("medium");
  const [source, setSource] = React.useState<TaskSource>("operator");
  const [inboundOrigin, setInboundOrigin] = React.useState("");
  const [dueAt, setDueAt] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);

  const [agents, setAgents] = React.useState<Agent[]>([]);
  const [workspaces, setWorkspaces] = React.useState<WorkspaceOption[]>([]);

  React.useEffect(() => {
    if (!open) return;
    let cancelled = false;
    Promise.all([
      agentApi.list({ activeOnly: true }).then((r) => r.items),
      getWorkspaces() as Promise<WorkspaceCardData[]>,
    ])
      .then(([ag, ws]) => {
        if (cancelled) return;
        setAgents(ag);
        setWorkspaces(ws.map((w) => ({ id: w.id, name: w.name })));
      })
      .catch((err) => {
        console.error("Failed to load options for NewTaskModal", err);
      });
    return () => {
      cancelled = true;
    };
  }, [open]);

  const reset = () => {
    setTitle("");
    setDescription("");
    setWorkspaceId(defaultWorkspaceId ?? "");
    setAssigneeAgentId(defaultAssigneeAgentId ?? "");
    setPriority("medium");
    setSource("operator");
    setInboundOrigin("");
    setDueAt("");
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;
    setSubmitting(true);
    try {
      const payload: TaskCreate = {
        title: title.trim(),
        description: description.trim() || undefined,
        priority,
        source,
        workspaceId: workspaceId || undefined,
        assigneeAgentId: assigneeAgentId || undefined,
        inboundOrigin: source === "inbound" ? inboundOrigin.trim() || undefined : undefined,
        dueAt: dueAt ? new Date(dueAt).toISOString() : undefined,
        createdByLabel: "admin",
      };
      const created = await taskApi.create(payload);
      toast.success(`Task created: ${created.title}`);
      reset();
      onOpenChange(false);
      if (onCreated) {
        onCreated(created.id);
      } else {
        router.refresh();
      }
    } catch (err) {
      console.error(err);
      toast.error("Failed to create task");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle className="text-2xl">New task</DialogTitle>
          <DialogDescription>
            Create a task and assign it to an agent — or leave unassigned for claim from the backlog.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="task-title">Title</Label>
            <Input
              id="task-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              required
              autoFocus
              placeholder="e.g. Burn analysis for Hypertide before Friday"
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="task-description">Description</Label>
            <Textarea
              id="task-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={4}
              placeholder="Markdown. Context the agent needs — what to look at, what to produce, deadline."
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="task-workspace">Workspace</Label>
              <select
                id="task-workspace"
                value={workspaceId}
                onChange={(e) => setWorkspaceId(e.target.value)}
                className={cn(
                  "w-full h-9 rounded-md border-[1.5px] border-border bg-background px-3 text-sm",
                  "focus-visible:border-ring focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
                )}
              >
                <option value="">— No workspace (cross-client) —</option>
                {workspaces.map((ws) => (
                  <option key={ws.id} value={ws.id}>
                    {ws.name}
                  </option>
                ))}
              </select>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="task-assignee">Assignee</Label>
              <select
                id="task-assignee"
                value={assigneeAgentId}
                onChange={(e) => setAssigneeAgentId(e.target.value)}
                className={cn(
                  "w-full h-9 rounded-md border-[1.5px] border-border bg-background px-3 text-sm",
                  "focus-visible:border-ring focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
                )}
              >
                <option value="">— Unassigned (backlog) —</option>
                {agents.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.title} ({a.name})
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="task-priority">Priority</Label>
              <select
                id="task-priority"
                value={priority}
                onChange={(e) => setPriority(e.target.value as TaskPriority)}
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
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="task-source">Source</Label>
              <select
                id="task-source"
                value={source}
                onChange={(e) => setSource(e.target.value as TaskSource)}
                className={cn(
                  "w-full h-9 rounded-md border-[1.5px] border-border bg-background px-3 text-sm",
                  "focus-visible:border-ring focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
                )}
              >
                {SOURCES.map((s) => (
                  <option key={s.value} value={s.value}>
                    {s.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {source === "inbound" && (
            <div className="space-y-1.5">
              <Label htmlFor="task-origin">Inbound origin</Label>
              <Input
                id="task-origin"
                value={inboundOrigin}
                onChange={(e) => setInboundOrigin(e.target.value)}
                placeholder="e.g. slack #hypertide, email from chris@..., 2026-05-16 call"
              />
            </div>
          )}

          <div className="space-y-1.5">
            <Label htmlFor="task-due">Due date (optional)</Label>
            <Input
              id="task-due"
              type="datetime-local"
              value={dueAt}
              onChange={(e) => setDueAt(e.target.value)}
            />
          </div>

          <DialogFooter>
            <button
              type="button"
              onClick={() => onOpenChange(false)}
              disabled={submitting}
              className={cn(
                "inline-flex items-center justify-center gap-1.5 h-9 px-4 rounded-md text-sm font-medium",
                "bg-transparent text-ink border-[1.5px] border-border-bold hover:bg-muted",
                "disabled:opacity-50 transition-colors"
              )}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting || !title.trim()}
              className={cn(
                "inline-flex items-center justify-center gap-1.5 h-9 px-4 rounded-md text-sm font-medium",
                "bg-amber text-ink border-[1.5px] border-border-bold",
                "hover:shadow-flat-sm focus-visible:shadow-flat-sm transition-shadow",
                "disabled:opacity-50 disabled:cursor-not-allowed"
              )}
            >
              {submitting ? "Creating…" : "Create task"}
            </button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
