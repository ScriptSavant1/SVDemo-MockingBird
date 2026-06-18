import { useState } from "react";
import { useParams, Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { projectsApi } from "@/api/projects";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { StatusBadge } from "@/components/StatusBadge";
import { formatDate } from "@/utils/formatters";
import type { Stub } from "@/api/types";

export function ProjectPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const qc = useQueryClient();
  const [deployingId, setDeployingId] = useState<string | null>(null);

  const { data: project } = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => projectsApi.get(projectId!),
    enabled: !!projectId,
  });

  const { data: stubs = [], isPending } = useQuery({
    queryKey: ["stubs", projectId],
    queryFn: () => projectsApi.listStubs(projectId!),
    enabled: !!projectId,
  });

  const deployMutation = useMutation({
    mutationFn: (stubId: string) => projectsApi.deploy(projectId!, stubId),
    onMutate: (stubId) => setDeployingId(stubId),
    onSettled: () => {
      setDeployingId(null);
      void qc.invalidateQueries({ queryKey: ["stubs", projectId] });
    },
  });

  if (isPending) {
    return <div className="py-12 text-center text-gray-500">Loading…</div>;
  }

  return (
    <div>
      <div className="mb-6">
        <Link to="/" className="text-sm text-[#00A9E0] hover:underline">← All projects</Link>
        <h1 className="mt-2 text-2xl font-bold text-gray-900">{project?.name ?? "Project"}</h1>
        <p className="text-sm text-gray-500">{project?.description}</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Stubs</CardTitle>
        </CardHeader>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200 text-left text-xs font-medium uppercase text-gray-500">
              <th className="pb-2 pr-4">Name</th>
              <th className="pb-2 pr-4">Type</th>
              <th className="pb-2 pr-4">Status</th>
              <th className="pb-2 pr-4">Updated</th>
              <th className="pb-2" />
            </tr>
          </thead>
          <tbody>
            {(stubs as Stub[]).map((stub) => (
              <tr key={stub.id} className="border-b border-gray-100 last:border-0">
                <td className="py-3 pr-4 font-medium text-gray-900">{stub.name}</td>
                <td className="py-3 pr-4 text-gray-500">{stub.stub_type}</td>
                <td className="py-3 pr-4">
                  <StatusBadge status={stub.status} />
                </td>
                <td className="py-3 pr-4 text-gray-400">{formatDate(stub.updated_at)}</td>
                <td className="py-3">
                  <div className="flex gap-2">
                    {stub.status === "READY" && (
                      <Button
                        size="sm"
                        loading={deployingId === stub.id}
                        onClick={() => deployMutation.mutate(stub.id)}
                      >
                        Deploy
                      </Button>
                    )}
                    {(stub.status === "LIVE" || stub.status === "SUSPENDED") && (
                      <Link to={`/projects/${projectId}/stubs/${stub.id}`}>
                        <Button size="sm" variant="secondary">View</Button>
                      </Link>
                    )}
                  </div>
                </td>
              </tr>
            ))}
            {stubs.length === 0 && (
              <tr>
                <td colSpan={5} className="py-8 text-center text-gray-400">No stubs yet.</td>
              </tr>
            )}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
