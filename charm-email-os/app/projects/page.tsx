/**
 * Screen: Projects
 * List view grouped by workspace, with attention markers (overdue, blocked).
 */
"use client";

import * as React from "react";
import { Plus, FolderKanban } from "lucide-react";
import { projectApi } from "@/lib/api";
import { PageHeader, ProjectCard, NewProjectModal } from "@/components/charm";
import type { Project } from "@/lib/types";

export default function ProjectsPage() {
  const [projects, setProjects] = React.useState<Project[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [modalOpen, setModalOpen] = React.useState(false);

  const refetch = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await projectApi.list({ includeClosed: true });
      setProjects(res.items);
    } catch (err) {
      console.error(err);
      setError("Failed to load projects");
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    refetch();
  }, [refetch]);

  const byWorkspace = React.useMemo(() => {
    const map = new Map<string, { name: string; projects: Project[] }>();
    for (const p of projects) {
      const key = p.workspaceId ?? "_cross";
      const label = p.workspaceName ?? "Cross-workspace";
      if (!map.has(key)) map.set(key, { name: label, projects: [] });
      map.get(key)!.projects.push(p);
    }
    return Array.from(map.entries());
  }, [projects]);

  const activeCount = projects.filter((p) => p.status === "active").length;

  return (
    <div className="px-8 py-8 max-w-7xl w-full mx-auto">
      <PageHeader
        kicker="Long-term initiatives"
        title="Projects"
        subtitle={
          projects.length === 0
            ? "No projects yet. Create one to plan multi-task work for a client."
            : `${projects.length} project${projects.length === 1 ? "" : "s"} · ${activeCount} active`
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
        <div className="flex flex-col items-center justify-center text-center gap-3 py-20 px-6 rounded-xl border border-dashed border-border bg-muted/30">
          <span className="inline-flex items-center justify-center h-12 w-12 rounded-md bg-amber/15 text-amber border-[1.5px] border-amber">
            <FolderKanban className="h-6 w-6" aria-hidden="true" />
          </span>
          <h3 className="text-xl">No projects yet</h3>
          <p className="text-sm text-ink-soft max-w-md">
            Create the first project. Group related tasks together — agents and AEs both contribute, progress rolls up to the project.
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
          {byWorkspace.map(([key, group]) => (
            <section key={key} aria-labelledby={`group-${key}`}>
              <h2
                id={`group-${key}`}
                className="text-base font-medium uppercase tracking-wider text-ink-soft mb-3"
              >
                {group.name} · {group.projects.length}
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {group.projects.map((p) => (
                  <ProjectCard
                    key={p.id}
                    project={p}
                    href={`/projects/${p.id}`}
                  />
                ))}
              </div>
            </section>
          ))}
        </div>
      )}

      <NewProjectModal
        open={modalOpen}
        onOpenChange={setModalOpen}
        onCreated={() => refetch()}
      />
    </div>
  );
}
