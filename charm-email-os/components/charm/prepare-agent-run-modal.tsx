/**
 * PrepareAgentRunModal — paperclip-methodology semi-assisted run.
 *
 * Operator clicks "Prepare agent run" on a task. We:
 *   1. Resolve the assigned agent (from agent_skill_mappings: pull the skill bodies)
 *   2. Assemble a single prompt: agent identity + role + prompt_template +
 *      concatenated skill markdown + task title/description + workspace context +
 *      explicit instruction on output shape (markdown document, what doc_key to use)
 *   3. Show in a textarea with "Copy to clipboard" button
 *   4. Operator pastes into their local Claude Code (their subscription, their machine)
 *   5. Claude works. Operator pastes the result back into the task document editor.
 *
 * No headless shim, no LLM secrets server-side, no filesystem sync. When the
 * full headless shim ships (Phase 3) this same prompt-assembly is what it uses,
 * just with stdin/stdout instead of clipboard.
 */
"use client";

import * as React from "react";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Clipboard, Check, Bot, ExternalLink, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { agentApi } from "@/lib/api";
import type { Agent, AgentSkill, Task } from "@/lib/types";

export interface PrepareAgentRunModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  task: Task;
  /** Workspace context (name, slug) for the prompt header. */
  workspaceName?: string | null;
  /** Optional extra context block (e.g., campaign metrics snapshot). */
  extraContext?: string;
}

const DOC_KEY_BY_ROLE: Record<string, string> = {
  data_analyst: "analysis",
  researcher: "research_report",
  day_ai_reviewer: "review_summary",
  github_admin: "repo_op",
  general: "notes",
};

export function PrepareAgentRunModal({
  open,
  onOpenChange,
  task,
  workspaceName,
  extraContext,
}: PrepareAgentRunModalProps) {
  const [agent, setAgent] = React.useState<Agent | null>(null);
  const [skillBodies, setSkillBodies] = React.useState<AgentSkill[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [copied, setCopied] = React.useState(false);

  React.useEffect(() => {
    if (!open || !task.assigneeAgentId) {
      setAgent(null);
      setSkillBodies([]);
      return;
    }
    let cancelled = false;
    setLoading(true);
    (async () => {
      try {
        // Fetch agent (includes skill summaries) + global skill library to look up bodies
        const [a, skills] = await Promise.all([
          agentApi.get(task.assigneeAgentId!),
          agentApi.listSkills(true),
        ]);
        if (cancelled) return;
        setAgent(a);
        const skillsBySlug = new Map(skills.map((s) => [s.slug, s]));
        setSkillBodies(
          a.skills.map((s) => skillsBySlug.get(s.slug)).filter((s): s is AgentSkill => !!s)
        );
      } catch (err) {
        console.error("Failed to load agent for prepare-run", err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open, task.assigneeAgentId]);

  const docKey = agent ? DOC_KEY_BY_ROLE[agent.role] ?? "notes" : "notes";
  const promptTemplate =
    (agent?.adapterConfig as Record<string, unknown> | undefined)?.promptTemplate ?? "";

  const assembledPrompt = React.useMemo(() => {
    if (!agent) return "";
    const parts: string[] = [];

    parts.push(`# Agent run — ${agent.title}\n`);
    parts.push(`You are **${agent.title}** (@${agent.name}). Role: ${agent.role}.\n`);
    if (typeof promptTemplate === "string" && promptTemplate.trim()) {
      parts.push("## Operating instructions\n");
      parts.push(promptTemplate.trim());
      parts.push("");
    }

    if (skillBodies.length > 0) {
      parts.push("## Available skills\n");
      parts.push(
        "You have access to the following skills. Load only those relevant to this task; quote skill names when you apply them.\n"
      );
      for (const skill of skillBodies) {
        parts.push(`### Skill: ${skill.slug}\n`);
        parts.push(`*${skill.description}*\n`);
        if (skill.bodyMarkdown.trim()) {
          parts.push(skill.bodyMarkdown.trim());
        }
        parts.push("");
      }
    }

    parts.push("## Task\n");
    parts.push(`**Title:** ${task.title}\n`);
    if (workspaceName) {
      parts.push(`**Workspace:** ${workspaceName}`);
    }
    if (task.workspaceId) {
      parts.push(`**Workspace ID:** \`${task.workspaceId}\``);
    }
    if (task.projectName) {
      parts.push(`**Project:** ${task.projectName}`);
    }
    if (task.priority !== "medium") {
      parts.push(`**Priority:** ${task.priority}`);
    }
    if (task.dueAt) {
      parts.push(`**Due:** ${new Date(task.dueAt).toLocaleDateString()}`);
    }
    parts.push("");
    if (task.description) {
      parts.push("**Description:**\n");
      parts.push(task.description.trim());
      parts.push("");
    }

    if (extraContext && extraContext.trim()) {
      parts.push("## Context\n");
      parts.push(extraContext.trim());
      parts.push("");
    }

    parts.push("## Output requirements\n");
    parts.push(
      `Produce a markdown report. When done, return the **full report body** in a single markdown block — the operator will paste it back into the task's \`${docKey}\` document.`
    );
    parts.push("");
    parts.push("Required structure:");
    parts.push("- **TL;DR** (3 sentences max)");
    parts.push("- **Findings** (numbered, evidence-backed)");
    parts.push("- **Sources / queries** (cite SQL or refs)");
    parts.push("- **Recommendations** (concrete, ranked)");
    parts.push("");
    parts.push("If you cannot complete the task with the context provided, return a TL;DR explaining what's missing and what you'd need from the operator.");

    return parts.join("\n");
  }, [agent, skillBodies, promptTemplate, task, workspaceName, extraContext]);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(assembledPrompt);
      setCopied(true);
      toast.success("Prompt copied. Paste into your local Claude Code.");
      setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error("Copy failed — select and Ctrl+C manually");
    }
  };

  if (!task.assigneeAgentId) {
    return (
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>No assignee</DialogTitle>
            <DialogDescription>
              Assign this task to an agent first. The "Prepare agent run" flow needs to know which agent persona + skills to assemble.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <button
              type="button"
              onClick={() => onOpenChange(false)}
              className="inline-flex items-center justify-center gap-1.5 h-9 px-4 rounded-md text-sm font-medium bg-amber text-ink border-[1.5px] border-border-bold hover:shadow-flat-sm transition-shadow"
            >
              Got it
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-3xl max-h-[90vh] flex flex-col">
        <DialogHeader>
          <DialogTitle className="text-2xl inline-flex items-center gap-2">
            <Bot className="h-5 w-5 text-copper" aria-hidden="true" />
            Prepare agent run
            {agent && (
              <span className="text-base font-mono text-ink-soft ml-2">
                @{agent.name}
              </span>
            )}
          </DialogTitle>
          <DialogDescription>
            Paperclip-methodology semi-assisted run: copy this prompt into your local Claude Code (your subscription, your machine).
            When Claude returns the result, paste it back into the <code className="font-mono text-xs">{docKey}</code> document on this task.
          </DialogDescription>
        </DialogHeader>

        {loading ? (
          <div className="flex items-center gap-2 text-sm text-ink-soft py-8 justify-center">
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            Assembling prompt…
          </div>
        ) : (
          <>
            <div className="flex items-center justify-between gap-2 text-xs text-ink-soft mb-2">
              <span>
                {agent?.title} · {skillBodies.length} skill{skillBodies.length === 1 ? "" : "s"} loaded
              </span>
              <span className="font-mono">{assembledPrompt.length.toLocaleString()} chars</span>
            </div>
            <div className="flex-1 min-h-0 overflow-y-auto custom-scrollbar rounded-md border-[1.5px] border-border bg-muted/40 p-3 mb-2">
              <pre className="text-xs font-mono whitespace-pre-wrap break-words">{assembledPrompt}</pre>
            </div>
            <div className="flex items-center gap-2 text-xs text-ink-soft px-1">
              <ExternalLink className="h-3 w-3" aria-hidden="true" />
              <span>
                After Claude finishes, open the task&apos;s <strong>Documents</strong> tab,
                use key <code className="font-mono">{docKey}</code>, and paste the markdown.
              </span>
            </div>
          </>
        )}

        <DialogFooter className="flex-col sm:flex-row sm:justify-between sm:items-center gap-2">
          <span className="text-xs text-ink-soft">
            Your Claude · your subscription · your machine
          </span>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => onOpenChange(false)}
              className="inline-flex items-center justify-center gap-1.5 h-9 px-4 rounded-md text-sm font-medium bg-transparent text-ink border-[1.5px] border-border-bold hover:bg-muted transition-colors"
            >
              Close
            </button>
            <button
              type="button"
              onClick={handleCopy}
              disabled={loading || !assembledPrompt}
              className={cn(
                "inline-flex items-center justify-center gap-1.5 h-9 px-4 rounded-md text-sm font-medium",
                "bg-amber text-ink border-[1.5px] border-border-bold hover:shadow-flat-sm transition-shadow",
                "disabled:opacity-50 disabled:cursor-not-allowed"
              )}
            >
              {copied ? (
                <>
                  <Check className="h-4 w-4" aria-hidden="true" />
                  Copied
                </>
              ) : (
                <>
                  <Clipboard className="h-4 w-4" aria-hidden="true" />
                  Copy prompt
                </>
              )}
            </button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
