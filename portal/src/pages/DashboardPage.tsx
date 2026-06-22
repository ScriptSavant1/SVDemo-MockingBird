import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { projectsApi } from "@/api/projects";
import { useAuthStore } from "@/store/auth";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { StatusBadge } from "@/components/StatusBadge";
import { formatDate } from "@/utils/formatters";
import type { Project } from "@/api/types";

const STATUS_OPTIONS = ["ALL", "DRAFT", "READY", "DEPLOYING", "LIVE", "SUSPENDED"] as const;
type StatusFilter = (typeof STATUS_OPTIONS)[number];

const DRAFT_HINT = "Upload a spec file to generate stubs, then deploy.";

export function DashboardPage() {
  const role = useAuthStore((s) => s.user?.role);
  const canCreate = role === "ADMIN" || role === "SV_TEAM";

  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("ALL");
  const [listView, setListView] = useState(false);

  const { data: projects = [], isPending, isError } = useQuery({
    queryKey: ["projects"],
    queryFn: projectsApi.list,
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
    return <div className="text-center py-12 text-gray-500">Loading projects…</div>;
  }

  if (isError) {
    return <div className="rounded bg-red-50 px-4 py-3 text-sm text-red-700">Failed to load projects.</div>;
  }

  return (
    <div>
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Projects</h1>
        {canCreate && (
          <Link to="/projects/new">
            <Button data-testid="new-project-button">New Project</Button>
          </Link>
        )}
      </div>

      {/* Search + view toggle */}
      <div className="mb-3 flex items-center gap-3">
        <input
          type="search"
          placeholder="Search by name or team…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-64 rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-[#003875] focus:outline-none focus:ring-1 focus:ring-[#003875]"
        />
        <div className="ml-auto flex items-center gap-1 rounded border border-gray-200 p-0.5">
          <button
            title="Grid view"
            onClick={() => setListView(false)}
            className={`rounded p-1.5 text-sm transition-colors ${!listView ? "bg-[#003875] text-white" : "text-gray-500 hover:text-gray-700"}`}
          >
            <GridIcon />
          </button>
          <button
            title="List view"
            onClick={() => setListView(true)}
            className={`rounded p-1.5 text-sm transition-colors ${listView ? "bg-[#003875] text-white" : "text-gray-500 hover:text-gray-700"}`}
          >
            <ListIcon />
          </button>
        </div>
      </div>

      {/* Status filter pills */}
      <div className="mb-5 flex flex-wrap gap-2">
        {STATUS_OPTIONS.filter((s) => s === "ALL" || counts[s] > 0).map((s) => (
          <button
            key={s}
            onClick={() => setStatusFilter(s)}
            className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
              statusFilter === s
                ? "bg-[#003875] text-white"
                : "bg-gray-100 text-gray-600 hover:bg-gray-200"
            }`}
          >
            {s} <span className="ml-1 opacity-70">{counts[s]}</span>
          </button>
        ))}
      </div>

      {/* Empty state */}
      {visible.length === 0 && (
        <Card>
          <p className="text-center text-gray-500 py-8">
            {search || statusFilter !== "ALL"
              ? "No projects match your filter."
              : <>No projects yet.{" "}{canCreate && <Link to="/projects/new" className="text-[#00A9E0] hover:underline">Create your first project.</Link>}</>
            }
          </p>
        </Card>
      )}

      {/* Grid view */}
      {!listView && visible.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {visible.map((p: Project) => (
            <Link key={p.id} to={`/projects/${p.id}`}>
              <Card
                data-testid="project-card"
                className="hover:border-[#003875] hover:shadow-md transition-all cursor-pointer h-full"
              >
                <CardHeader>
                  <CardTitle className="truncate">{p.name}</CardTitle>
                  <StatusBadge status={p.status} />
                </CardHeader>
                {p.status === "DRAFT" && (
                  <p className="mt-1 text-xs text-amber-600">{DRAFT_HINT}</p>
                )}
                {p.description && (
                  <p className="mt-1 text-sm text-gray-500 line-clamp-2">{p.description}</p>
                )}
                <p className="mt-3 text-xs text-gray-400">Updated {formatDate(p.updated_at)}</p>
              </Card>
            </Link>
          ))}
        </div>
      )}

      {/* List view */}
      {listView && visible.length > 0 && (
        <div className="rounded-lg border border-gray-200 bg-white overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-xs text-gray-500 uppercase tracking-wide">
              <tr>
                <th className="px-4 py-3 text-left">Name</th>
                <th className="px-4 py-3 text-left">Team</th>
                <th className="px-4 py-3 text-left">Status</th>
                <th className="px-4 py-3 text-left">Updated</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {visible.map((p: Project) => (
                <tr
                  key={p.id}
                  className="hover:bg-gray-50 cursor-pointer transition-colors"
                  onClick={() => window.location.assign(`/projects/${p.id}`)}
                >
                  <td className="px-4 py-3 font-medium text-gray-900">{p.name}</td>
                  <td className="px-4 py-3 text-gray-500">{p.team ?? "—"}</td>
                  <td className="px-4 py-3"><StatusBadge status={p.status} /></td>
                  <td className="px-4 py-3 text-gray-400">{formatDate(p.updated_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function GridIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor">
      <rect x="0" y="0" width="6" height="6" rx="1" />
      <rect x="8" y="0" width="6" height="6" rx="1" />
      <rect x="0" y="8" width="6" height="6" rx="1" />
      <rect x="8" y="8" width="6" height="6" rx="1" />
    </svg>
  );
}

function ListIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor">
      <rect x="0" y="1" width="14" height="2" rx="1" />
      <rect x="0" y="6" width="14" height="2" rx="1" />
      <rect x="0" y="11" width="14" height="2" rx="1" />
    </svg>
  );
}
