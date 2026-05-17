/**
 * NewProjectModal — admin creates a project for a workspace (or cross-client).
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
import { projectApi } from "@/lib/api";
import { getWorkspaces } from "@/lib/data/charm";
import type {
  ProjectCreate,
  ProjectPriority,
  ProjectStatus,
} from "@/lib/types";
import type { WorkspaceCardData } from "@/components/charm";
import { cn } from "@/lib/utils";

const STATUSES: { value: ProjectStatus; label: string }[] = [
  { value: "planning", label: "Planning" },
  { value: "active", label: "Active" },
  { value: "paused", label: "Paused" },
];

const PRIORITIES: { value: ProjectPriority; label: string }[] = [
  { value: "low", label: "Low" },
  { value: "medium", label: "Medium" },
  { value: "high", label: "High" },
  { value: "urgent", label: "Urgent" },
];

export interface NewProjectModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  defaultWorkspaceId?: string;
  onCreated?: (projectId: string) => void;
}

export function NewProjectModal({
  open,
  onOpenChange,
  defaultWorkspaceId,
  onCreated,
}: NewProjectModalProps) {
  const router = useRouter();
  const [name, setName] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [workspaceId, setWorkspaceId] = React.useState<string>(defaultWorkspaceId ?? "");
  const [status, setStatus] = React.useState<ProjectStatus>("planning");
  const [priority, setPriority] = React.useState<ProjectPriority>("medium");
  const [startAt, setStartAt] = React.useState("");
  const [targetEndAt, setTargetEndAt] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);

  const [workspaces, setWorkspaces] = React.useState<{ id: string; name: string }[]>([]);

  React.useEffect(() => {
    if (!open) return;
    let cancelled = false;
    (getWorkspaces() as Promise<WorkspaceCardData[]>)
      .then((ws) => {
        if (cancelled) return;
        setWorkspaces(ws.map((w) => ({ id: w.id, name: w.name })));
      })
      .catch((err) => console.error("Failed to load workspaces", err));
    return () => {
      cancelled = true;
    };
  }, [open]);

  const reset = () => {
    setName("");
    setDescription("");
    setWorkspaceId(defaultWorkspaceId ?? "");
    setStatus("planning");
    setPriority("medium");
    setStartAt("");
    setTargetEndAt("");
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    setSubmitting(true);
    try {
      const payload: ProjectCreate = {
        name: name.trim(),
        description: description.trim() || undefined,
        workspaceId: workspaceId || undefined,
        status,
        priority,
        startAt: startAt ? new Date(startAt).toISOString() : undefined,
        targetEndAt: targetEndAt ? new Date(targetEndAt).toISOString() : undefined,
        createdByLabel: "admin",
      };
      const created = await projectApi.create(payload);
      toast.success(`Project created: ${created.name}`);
      reset();
      onOpenChange(false);
      if (onCreated) onCreated(created.id);
      else router.refresh();
    } catch (err) {
      console.error(err);
      toast.error("Failed to create project");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle className="text-2xl">New project</DialogTitle>
          <DialogDescription>
            Long-term initiative. Group related tasks under it; agents and AEs both contribute.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="project-name">Name</Label>
            <Input
              id="project-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              autoFocus
              placeholder="e.g. Hypertide Q3 capacity ramp"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="project-description">Description</Label>
            <Textarea
              id="project-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              placeholder="Markdown. Brief, success criteria, why it matters."
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="project-workspace">Workspace</Label>
              <select
                id="project-workspace"
                value={workspaceId}
                onChange={(e) => setWorkspaceId(e.target.value)}
                className={cn(
                  "w-full h-9 rounded-md border-[1.5px] border-border bg-background px-3 text-sm",
                  "focus-visible:border-ring focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
                )}
              >
                <option value="">— Cross-workspace —</option>
                {workspaces.map((ws) => (
                  <option key={ws.id} value={ws.id}>{ws.name}</option>
                ))}
              </select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="project-priority">Priority</Label>
              <select
                id="project-priority"
                value={priority}
                onChange={(e) => setPriority(e.target.value as ProjectPriority)}
                className={cn(
                  "w-full h-9 rounded-md border-[1.5px] border-border bg-background px-3 text-sm",
                  "focus-visible:border-ring focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
                )}
              >
                {PRIORITIES.map((p) => (
                  <option key={p.value} value={p.value}>{p.label}</option>
                ))}
              </select>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="project-start">Start date</Label>
              <Input
                id="project-start"
                type="date"
                value={startAt}
                onChange={(e) => setStartAt(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="project-end">Target end date</Label>
              <Input
                id="project-end"
                type="date"
                value={targetEndAt}
                onChange={(e) => setTargetEndAt(e.target.value)}
              />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="project-status">Initial status</Label>
            <select
              id="project-status"
              value={status}
              onChange={(e) => setStatus(e.target.value as ProjectStatus)}
              className={cn(
                "w-full h-9 rounded-md border-[1.5px] border-border bg-background px-3 text-sm",
                "focus-visible:border-ring focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
              )}
            >
              {STATUSES.map((s) => (
                <option key={s.value} value={s.value}>{s.label}</option>
              ))}
            </select>
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
              disabled={submitting || !name.trim()}
              className={cn(
                "inline-flex items-center justify-center gap-1.5 h-9 px-4 rounded-md text-sm font-medium",
                "bg-amber text-ink border-[1.5px] border-border-bold",
                "hover:shadow-flat-sm focus-visible:shadow-flat-sm transition-shadow",
                "disabled:opacity-50 disabled:cursor-not-allowed"
              )}
            >
              {submitting ? "Creating…" : "Create project"}
            </button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
