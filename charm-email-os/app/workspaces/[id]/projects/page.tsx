/**
 * Screen: Workspace Projects
 * Projects scoped to THIS workspace. NewProjectModal pre-filled with workspaceId.
 * Top-level /projects remains the cross-workspace roll-up.
 */
"use client";

import * as React from "react";
import { useParams } from "next/navigation";
import { Plus, FolderKanban } from "lucide-react";
import { projectApi } from "@/lib/api";
import { PageHeader, ProjectCard, NewProjectModal } from "@/components/charm";
import type { Project } from "@/lib/types";

export default function WorkspaceProjectsPage() {
  const { id } = useParams<{ id: string }>();
  const [projects, setProjects] = React.useState<Project[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [modalOpen, setModalOpen] = React.useState(false);

  const refetch = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await projectApi.list({ workspaceId: id, includeClosed: true });
      setProjects(res.items);
    } catch (err) {
      console.error(err);
      setError("Failed to load projects");
    } finally {
      setLoading(false);
    }
  }, [id]);

  React.useEffect(() => {
    refetch();
  }, [refetch]);

  const grouped = React.useMemo(() => {
    const active: Project[] = [];
    const closed: Project[] = [];
    for (const p of projects) {
      if (p.status === "done" || p.status === "cancelled") closed.push(p);
      else active.push(p);
    }
    return { active, closed };
  }, [projects]);

  return (
    <div>
      <PageHeader
        kicker="Workspace projects"
        title="Projects"
        subtitle={
          projects.length === 0
            ? "No projects in this workspace yet. Create one to plan multi-task work."
            : `${grouped.active.length} active · ${grouped.closed.length} closed`
        }
        actions={
          <button
            type="button"
            onClick={() => setModalOpen(true)}
            className="inline-flex items-center gap-1.5 h-9 px-4 rounded-md text-sm font-medium bg-amber text-ink border-[1.5px] border-border-bold hover:shadow-flat-sm transition-shadow"
          >
            <Plus className="h-4 w-4" aria-hidden="true" />
            New project
          </button>
        }
      />

      {error && (
        <div className="mb-4 p-3 rounded-md border-[1.5px] border-rust bg-rust/10 text-rust text-sm">
          {error}
        </div>
      )}

      {loading && projects.length === 0 ? (
        <div className="text-sm text-ink-soft py-12 text-center">Loading projects…</div>
      ) : projects.length === 0 ? (
        <div className="flex flex-col items-center justify-center text-center gap-3 py-16 px-6 rounded-xl border border-dashed border-border bg-muted/30">
          <span className="inline-flex items-center justify-center h-12 w-12 rounded-md bg-amber/15 text-amber border-[1.5px] border-amber">
            <FolderKanban className="h-6 w-6" aria-hidden="true" />
          </span>
          <h3 className="text-xl">No projects yet</h3>
          <p className="text-sm text-ink-soft max-w-md">
            Create the first project for this workspace. Group related tasks
            together — both AEs and agents contribute, progress rolls up.
          </p>
          <button
            type="button"
            onClick={() => setModalOpen(true)}
            className="mt-2 inline-flex items-center gap-1.5 h-9 px-4 rounded-md text-sm font-medium bg-amber text-ink border-[1.5px] border-border-bold hover:shadow-flat-sm transition-shadow"
          >
            <Plus className="h-4 w-4" aria-hidden="true" />
            New project
          </button>
        </div>
      ) : (
        <div className="space-y-8">
          {grouped.active.length > 0 && (
            <section aria-labelledby="active-projects">
              <h2
                id="active-projects"
                className="text-xs font-medium uppercase tracking-wider text-ink-soft mb-3"
              >
                Active · {grouped.active.length}
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {grouped.active.map((p) => (
                  <ProjectCard key={p.id} project={p} href={`/projects/${p.id}`} />
                ))}
              </div>
            </section>
          )}
          {grouped.closed.length > 0 && (
            <section aria-labelledby="closed-projects">
              <h2
                id="closed-projects"
                className="text-xs font-medium uppercase tracking-wider text-ink-soft mb-3"
              >
                Closed · {grouped.closed.length}
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {grouped.closed.map((p) => (
                  <ProjectCard key={p.id} project={p} href={`/projects/${p.id}`} />
                ))}
              </div>
            </section>
          )}
        </div>
      )}

      <NewProjectModal
        open={modalOpen}
        onOpenChange={setModalOpen}
        defaultWorkspaceId={id}
        onCreated={() => refetch()}
      />
    </div>
  );
}
