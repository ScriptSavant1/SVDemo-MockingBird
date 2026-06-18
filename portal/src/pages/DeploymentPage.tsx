import { useParams, Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { projectsApi } from "@/api/projects";
import { useMetricsWS } from "@/hooks/useMetricsWS";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { StatusBadge } from "@/components/StatusBadge";
import { TpsChart } from "@/components/TpsChart";
import { formatTps, formatLatency, formatErrorRate } from "@/utils/formatters";

export function DeploymentPage() {
  const { projectId, stubId } = useParams<{ projectId: string; stubId: string }>();
  const qc = useQueryClient();

  const { data: deployments = [] } = useQuery({
    queryKey: ["deployments", projectId],
    queryFn: () => projectsApi.listDeployments(projectId!),
    enabled: !!projectId,
    refetchInterval: 10_000,
  });

  const activeDeployment = deployments.find(
    (d) => d.stub_id === stubId && (d.status === "LIVE" || d.status === "SUSPENDED"),
  );

  const { latest, connected, history } = useMetricsWS(
    activeDeployment?.status === "LIVE" ? (activeDeployment.id ?? null) : null,
  );

  const suspendMutation = useMutation({
    mutationFn: () => projectsApi.suspend(projectId!, activeDeployment!.id),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["deployments", projectId] }),
  });

  const redeployMutation = useMutation({
    mutationFn: () => projectsApi.redeploy(projectId!, activeDeployment!.id),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["deployments", projectId] }),
  });

  const reportMutation = useMutation({
    mutationFn: () => projectsApi.requestReport(projectId!, activeDeployment!.id),
  });

  if (!activeDeployment) {
    return (
      <div className="py-12 text-center text-gray-500">
        No active deployment found.{" "}
        <Link to={`/projects/${projectId}`} className="text-[#00A9E0] hover:underline">
          Back to project
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <Link to={`/projects/${projectId}`} className="text-sm text-[#00A9E0] hover:underline">
            ← Back to project
          </Link>
          <div className="mt-2 flex items-center gap-3">
            <h1 className="text-2xl font-bold text-gray-900">Stub Deployment</h1>
            <StatusBadge status={activeDeployment.status} />
          </div>
          {activeDeployment.stub_url && (
            <p className="mt-1 font-mono text-sm text-gray-500">{activeDeployment.stub_url}</p>
          )}
        </div>

        <div className="flex gap-2">
          {activeDeployment.status === "LIVE" && (
            <>
              <Button
                variant="secondary"
                size="sm"
                loading={reportMutation.isPending}
                onClick={() => reportMutation.mutate()}
              >
                Generate Report
              </Button>
              <Button
                variant="danger"
                size="sm"
                loading={suspendMutation.isPending}
                onClick={() => suspendMutation.mutate()}
              >
                Suspend
              </Button>
            </>
          )}
          {activeDeployment.status === "SUSPENDED" && (
            <Button
              size="sm"
              loading={redeployMutation.isPending}
              onClick={() => redeployMutation.mutate()}
            >
              Redeploy
            </Button>
          )}
        </div>
      </div>

      {activeDeployment.status === "LIVE" && (
        <Card>
          <CardHeader>
            <CardTitle>Live Metrics</CardTitle>
            <span className={`flex items-center gap-1.5 text-xs ${connected ? "text-green-600" : "text-gray-400"}`}>
              <span className={`h-2 w-2 rounded-full ${connected ? "bg-green-500 animate-pulse" : "bg-gray-300"}`} />
              {connected ? "Live" : "Connecting…"}
            </span>
          </CardHeader>

          {latest && (
            <div className="mb-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
              {[
                { label: "TPS", value: formatTps(latest.tps) },
                { label: "Avg Latency", value: formatLatency(latest.avg_latency_ms) },
                { label: "p95 Latency", value: formatLatency(latest.p95_latency_ms) },
                { label: "Error Rate", value: formatErrorRate(latest.error_rate) },
              ].map(({ label, value }) => (
                <div key={label} className="rounded bg-gray-50 p-3 text-center">
                  <div className="text-xl font-bold text-[#003875]">{value}</div>
                  <div className="text-xs text-gray-500">{label}</div>
                </div>
              ))}
            </div>
          )}

          <TpsChart snapshots={history} />
        </Card>
      )}

      {reportMutation.isSuccess && (
        <div className="rounded bg-green-50 px-4 py-3 text-sm text-green-700">
          Report queued — job ID: {reportMutation.data?.job_id}
        </div>
      )}
    </div>
  );
}
