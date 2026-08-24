import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { projectsApi } from "@/api/projects";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { StatusBadge } from "@/components/StatusBadge";
import { formatDate } from "@/utils/formatters";
import type { Project } from "@/api/types";

export function ReportsHubPage() {
  const [search, setSearch] = useState("");

  const { data: projects = [], isPending } = useQuery({
    queryKey: ["projects"],
    queryFn: projectsApi.list,
  });

  const deployed = useMemo(() => {
    const live = (projects as Project[]).filter(
      (p) => p.status === "LIVE" || p.status === "SUSPENDED",
    );
    const q = search.trim().toLowerCase();
    return q ? live.filter((p) => p.name.toLowerCase().includes(q) || p.team?.toLowerCase().includes(q)) : live;
  }, [projects, search]);

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-foreground">Reports</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          PDF, Excel, and PowerPoint usage reports are generated per deployment.
          Open a project below to generate or download its reports.
        </p>
      </div>

      <input
        type="search"
        placeholder="Search by project or team…"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        className="mb-5 w-72 rounded border border-input bg-background px-3 py-1.5 text-sm text-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
      />

      {isPending ? (
        <div className="py-12 text-center text-muted-foreground">Loading…</div>
      ) : deployed.length === 0 ? (
        <Card>
          <p className="py-8 text-center text-muted-foreground">
            No deployed projects yet. Reports become available once a stub is deployed.
          </p>
        </Card>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {deployed.map((p) => (
            <Link key={p.id} to={`/projects/${p.id}`}>
              <Card
                data-testid="reports-project-card"
                className="h-full cursor-pointer transition-all hover:border-primary hover:shadow-md"
              >
                <CardHeader>
                  <CardTitle className="truncate">{p.name}</CardTitle>
                  <StatusBadge status={p.status} />
                </CardHeader>
                <p className="text-sm text-muted-foreground">{p.team}</p>
                <p className="mt-3 text-xs text-muted-foreground">Updated {formatDate(p.updated_at)}</p>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
