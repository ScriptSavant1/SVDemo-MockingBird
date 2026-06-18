import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { projectsApi } from "@/api/projects";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { StatusBadge } from "@/components/StatusBadge";
import { formatDate } from "@/utils/formatters";
import type { Project } from "@/api/types";

export function DashboardPage() {
  const { data: projects = [], isPending, isError } = useQuery({
    queryKey: ["projects"],
    queryFn: projectsApi.list,
  });

  if (isPending) {
    return <div className="text-center py-12 text-gray-500">Loading projects…</div>;
  }

  if (isError) {
    return <div className="rounded bg-red-50 px-4 py-3 text-sm text-red-700">Failed to load projects.</div>;
  }

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Projects</h1>
      </div>

      {projects.length === 0 ? (
        <Card>
          <p className="text-center text-gray-500 py-8">No projects yet.</p>
        </Card>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {projects.map((p: Project) => (
            <Link key={p.id} to={`/projects/${p.id}`}>
              <Card className="hover:border-[#003875] hover:shadow-md transition-all cursor-pointer">
                <CardHeader>
                  <CardTitle className="truncate">{p.name}</CardTitle>
                  <StatusBadge status={p.status} />
                </CardHeader>
                <p className="text-sm text-gray-500 line-clamp-2">{p.description}</p>
                <p className="mt-3 text-xs text-gray-400">Updated {formatDate(p.updated_at)}</p>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
