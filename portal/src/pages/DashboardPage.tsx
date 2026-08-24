import { useState, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { LayoutGrid, List, FolderPlus, Search, Trash2 } from "lucide-react";
import { projectsApi } from "@/api/projects";
import { useAuthStore } from "@/store/auth";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { StatusBadge } from "@/components/StatusBadge";
import { formatDate } from "@/utils/formatters";
import { cn } from "@/lib/utils";
import { ApiError } from "@/api/client";
import type { Project } from "@/api/types";

const STATUS_OPTIONS = ["ALL", "DRAFT", "READY", "DEPLOYING", "LIVE", "SUSPENDED"] as const;
type StatusFilter = (typeof STATUS_OPTIONS)[number];

const DRAFT_HINT = "Upload a spec file to generate stubs, then deploy.";

export function DashboardPage() {
  const role = useAuthStore((s) => s.user?.role);
  const canCreate = role === "ADMIN" || role === "SV_TEAM";
  const canDelete = role === "ADMIN";
  const qc = useQueryClient();

  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("ALL");
  const [listView, setListView] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Project | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const { data: projects = [], isPending, isError } = useQuery({
    queryKey: ["projects"],
    queryFn: projectsApi.list,
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => projectsApi.delete(id),
    onSuccess: () => {
      setDeleteTarget(null);
      setDeleteError(null);
      void qc.invalidateQueries({ queryKey: ["projects"] });
    },
    onError: (err: unknown) => {
      setDeleteError(err instanceof ApiError ? err.detail : "Delete failed. Please try again.");
    },
  });

  const visible = useMemo(() => {
    const all = (projects as Project[]).filter((p) => p.status !== "ARCHIVED");
    const byStatus = statusFilter === "ALL" ? all : all.filter((p) => p.status === statusFilter);
    const q = search.trim().toLowerCase();
    return q ? byStatus.filter((p) => p.name.toLowerCase().includes(q) || p.team?.toLowerCase().includes(q)) : byStatus;
  }, [projects, statusFilter, search]);

  const counts = useMemo(() => {
    const all = (projects as Project[]).filter((p) => p.status !== "ARCHIVED");
    return STATUS_OPTIONS.reduce<Record<string, number>>((acc, s) => {
      acc[s] = s === "ALL" ? all.length : all.filter((p) => p.status === s).length;
      return acc;
    }, {});
  }, [projects]);

  if (isPending) {
    return <div className="py-12 text-center text-muted-foreground">Loading projects…</div>;
  }

  if (isError) {
    return (
      <div className="rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive">
        Failed to load projects.
      </div>
    );
  }

  return (
    <div>
      {/* Header */}
      <div className="mb-5 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Projects</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            {counts.ALL} project{counts.ALL === 1 ? "" : "s"} · {counts.LIVE} live
          </p>
        </div>
        {canCreate && (
          <Link to="/projects/new">
            <Button data-testid="new-project-button" className="gap-1.5">
              <FolderPlus size={15} />
              New Project
            </Button>
          </Link>
        )}
      </div>

      {/* Search + view toggle */}
      <div className="mb-3 flex items-center gap-3">
        <div className="relative w-72">
          <Search size={14} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            type="search"
            placeholder="Search by name or team…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full rounded-md border border-input bg-background py-1.5 pl-8 pr-3 text-sm text-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </div>
        <div className="ml-auto flex items-center gap-1 rounded-md border border-border p-0.5">
          <button
            title="Grid view"
            onClick={() => setListView(false)}
            className={cn(
              "rounded p-1.5 transition-colors",
              !listView ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground",
            )}
          >
            <LayoutGrid size={14} />
          </button>
          <button
            title="List view"
            onClick={() => setListView(true)}
            className={cn(
              "rounded p-1.5 transition-colors",
              listView ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground",
            )}
          >
            <List size={14} />
          </button>
        </div>
      </div>

      {/* Status filter pills */}
      <div className="mb-5 flex flex-wrap gap-2">
        {STATUS_OPTIONS.filter((s) => s === "ALL" || counts[s] > 0).map((s) => (
          <button
            key={s}
            onClick={() => setStatusFilter(s)}
            className={cn(
              "rounded-full px-3 py-1 text-xs font-medium transition-colors",
              statusFilter === s
                ? "bg-primary text-primary-foreground"
                : "bg-muted text-muted-foreground hover:bg-muted/70",
            )}
          >
            {s} <span className="ml-1 opacity-70">{counts[s]}</span>
          </button>
        ))}
      </div>

      {/* Empty state */}
      {visible.length === 0 && (
        <Card className="py-4">
          <div className="flex flex-col items-center gap-2 py-8 text-center">
            <FolderPlus size={28} className="mb-1 text-muted-foreground/50" />
            <p className="text-muted-foreground">
              {search || statusFilter !== "ALL"
                ? "No projects match your filter."
                : <>No projects yet.{" "}{canCreate && <Link to="/projects/new" className="text-secondary hover:underline">Create your first project.</Link>}</>
              }
            </p>
          </div>
        </Card>
      )}

      {/* Grid view */}
      {!listView && visible.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {visible.map((p: Project) => (
            <div key={p.id} className="group relative" data-testid="project-card-wrapper">
              <Link to={`/projects/${p.id}`}>
                <Card
                  data-testid="project-card"
                  className="h-full cursor-pointer transition-all hover:border-primary hover:shadow-md"
                >
                  <CardHeader>
                    <CardTitle className="truncate pr-6">{p.name}</CardTitle>
                    <StatusBadge status={p.status} />
                  </CardHeader>
                  {p.status === "DRAFT" && (
                    <p className="mt-1 text-xs text-warning">{DRAFT_HINT}</p>
                  )}
                  {p.description && (
                    <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">{p.description}</p>
                  )}
                  <p className="mt-3 text-xs text-muted-foreground">Updated {formatDate(p.updated_at)}</p>
                </Card>
              </Link>
              {canDelete && (
                <button
                  type="button"
                  title="Delete project"
                  data-testid="delete-project-button"
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    setDeleteError(null);
                    setDeleteTarget(p);
                  }}
                  className="absolute right-3 top-3 rounded p-1 text-muted-foreground opacity-0 transition-opacity hover:bg-destructive/10 hover:text-destructive group-hover:opacity-100 focus-visible:opacity-100"
                >
                  <Trash2 size={14} />
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {/* List view */}
      {listView && visible.length > 0 && (
        <div className="overflow-hidden rounded-lg border border-border bg-card">
          <table className="w-full text-sm">
            <thead className="bg-muted text-xs uppercase tracking-wide text-muted-foreground">
              <tr>
                <th className="px-4 py-3 text-left">Name</th>
                <th className="px-4 py-3 text-left">Team</th>
                <th className="px-4 py-3 text-left">Status</th>
                <th className="px-4 py-3 text-left">Updated</th>
                {canDelete && <th className="px-4 py-3" />}
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {visible.map((p: Project) => (
                <tr
                  key={p.id}
                  className="cursor-pointer transition-colors hover:bg-muted/50"
                  onClick={() => window.location.assign(`/projects/${p.id}`)}
                >
                  <td className="px-4 py-3 font-medium text-foreground">{p.name}</td>
                  <td className="px-4 py-3 text-muted-foreground">{p.team ?? "—"}</td>
                  <td className="px-4 py-3"><StatusBadge status={p.status} /></td>
                  <td className="px-4 py-3 text-muted-foreground">{formatDate(p.updated_at)}</td>
                  {canDelete && (
                    <td className="px-4 py-3 text-right">
                      <button
                        type="button"
                        title="Delete project"
                        data-testid="delete-project-button"
                        onClick={(e) => {
                          e.stopPropagation();
                          setDeleteError(null);
                          setDeleteTarget(p);
                        }}
                        className="rounded p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                      >
                        <Trash2 size={14} />
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {deleteTarget && (
        <Modal
          open={!!deleteTarget}
          title="Delete project"
          onClose={() => { setDeleteTarget(null); setDeleteError(null); }}
        >
          <p className="text-sm text-muted-foreground">
            Permanently delete <strong className="text-foreground">{deleteTarget.name}</strong>?
            This deletes all of its stubs, deployments, and job history. Any live AWS
            deployment is <strong>not</strong> automatically suspended first — suspend it
            separately if it's currently deployed.
          </p>
          <p className="mt-2 text-sm text-muted-foreground">
            This cannot be undone. A record of this deletion is kept in the audit log.
          </p>

          {deleteError && (
            <div className="mt-3 rounded bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">
              {deleteError}
            </div>
          )}

          <div className="mt-5 flex justify-end gap-3">
            <Button
              type="button"
              variant="secondary"
              onClick={() => { setDeleteTarget(null); setDeleteError(null); }}
              disabled={deleteMutation.isPending}
            >
              Cancel
            </Button>
            <Button
              type="button"
              variant="danger"
              loading={deleteMutation.isPending}
              data-testid="confirm-delete-project-button"
              onClick={() => deleteMutation.mutate(deleteTarget.id)}
            >
              Delete permanently
            </Button>
          </div>
        </Modal>
      )}
    </div>
  );
}
