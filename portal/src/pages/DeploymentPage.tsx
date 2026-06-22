import { useState } from "react";
import { useParams, Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { projectsApi } from "@/api/projects";
import { metricsApi } from "@/api/metrics";
import { useMetricsWS } from "@/hooks/useMetricsWS";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Tabs } from "@/components/ui/Tabs";
import { StatusBadge } from "@/components/StatusBadge";
import { TpsChart } from "@/components/TpsChart";
import { MetricsHistoryChart } from "@/components/MetricsHistoryChart";
import { formatTps, formatLatency, formatErrorRate, formatDate } from "@/utils/formatters";
import { ApiError } from "@/api/client";
import type { ReportJob } from "@/api/types";

const TABS = [
  { id: "overview", label: "Overview" },
  { id: "history", label: "Metrics History" },
  { id: "reports", label: "Reports" },
];

const RANGE_OPTIONS: { label: string; minutes: number }[] = [
  { label: "1h", minutes: 60 },
  { label: "6h", minutes: 360 },
  { label: "24h", minutes: 1440 },
];

type DownloadFormat = "pdf" | "excel" | "ppt";

export function DeploymentPage() {
  const { projectId, stubId } = useParams<{ projectId: string; stubId: string }>();
  const qc = useQueryClient();

  const [activeTab, setActiveTab] = useState("overview");
  const [historyMinutes, setHistoryMinutes] = useState(60);
  const [downloadingJob, setDownloadingJob] = useState<string | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);

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

  const { data: historyData, isFetching: historyLoading } = useQuery({
    queryKey: ["metrics-history", activeDeployment?.id, historyMinutes],
    queryFn: () => metricsApi.history(activeDeployment!.id, historyMinutes),
    enabled: activeTab === "history" && !!activeDeployment,
    staleTime: 60_000,
  });

  const { data: reportJobs = [], refetch: refetchReports } = useQuery({
    queryKey: ["reports", activeDeployment?.id],
    queryFn: () => projectsApi.listReports(projectId!, activeDeployment!.id),
    enabled: activeTab === "reports" && !!activeDeployment,
    staleTime: 10_000,
  });

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
    onSuccess: () => void refetchReports(),
  });

  async function handleDownload(jobId: string, format: DownloadFormat) {
    setDownloadingJob(`${jobId}-${format}`);
    setDownloadError(null);
    try {
      const { url } = await projectsApi.downloadReport(jobId, format);
      window.open(url, "_blank", "noopener,noreferrer");
    } catch (err) {
      setDownloadError(err instanceof ApiError ? err.detail : "Download failed");
    } finally {
      setDownloadingJob(null);
    }
  }

  if (!activeDeployment) {
    return (
      <div className="max-w-lg mx-auto mt-12">
        <Link to={`/projects/${projectId}`} className="text-sm text-[#00A9E0] hover:underline">
          ← Back to project
        </Link>
        <div className="mt-6 rounded-lg border border-amber-200 bg-amber-50 p-6 text-center">
          <p className="text-lg font-semibold text-amber-800">Stub not yet deployed</p>
          <p className="mt-2 text-sm text-amber-700">
            This stub is <strong>READY</strong> — stubs are generated and waiting for deployment.
            Click <strong>Deploy</strong> on the project page to provision an EC2 and go live.
          </p>
          <p className="mt-3 text-sm text-amber-700">
            Live metrics, Reports (PDF / Excel / PPT), Suspend and Redeploy are all available
            once the stub is deployed and <strong>LIVE</strong>.
          </p>
          <div className="mt-5">
            <Link to={`/projects/${projectId}`}>
              <Button variant="primary">Go to project → Deploy</Button>
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
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
            <Button
              variant="danger"
              size="sm"
              loading={suspendMutation.isPending}
              onClick={() => suspendMutation.mutate()}
            >
              Suspend
            </Button>
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

      {/* Tabs */}
      <Tabs tabs={TABS} active={activeTab} onChange={setActiveTab} />

      {/* Overview tab */}
      {activeTab === "overview" && (
        <Card>
          <CardHeader>
            <CardTitle>Live Metrics</CardTitle>
            <span
              className={`flex items-center gap-1.5 text-xs ${
                connected ? "text-green-600" : "text-gray-400"
              }`}
            >
              <span
                className={`h-2 w-2 rounded-full ${
                  connected ? "animate-pulse bg-green-500" : "bg-gray-300"
                }`}
              />
              {connected ? "Live" : activeDeployment.status === "LIVE" ? "Connecting…" : "Offline"}
            </span>
          </CardHeader>

          {latest && (
            <div className="mb-4 grid grid-cols-2 gap-4 px-6 sm:grid-cols-4">
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

          {!latest && activeDeployment.status === "LIVE" && (
            <p className="px-6 pb-4 text-sm text-gray-400">Waiting for first metrics scrape (every 30 s)…</p>
          )}

          <div className="px-6 pb-6">
            <TpsChart snapshots={history} />
          </div>
        </Card>
      )}

      {/* History tab */}
      {activeTab === "history" && (
        <Card>
          <CardHeader>
            <CardTitle>Metrics History</CardTitle>
            <div className="flex gap-1">
              {RANGE_OPTIONS.map(({ label, minutes }) => (
                <button
                  key={minutes}
                  data-testid={`range-${label}`}
                  onClick={() => setHistoryMinutes(minutes)}
                  className={[
                    "rounded px-2 py-1 text-xs font-medium transition-colors",
                    historyMinutes === minutes
                      ? "bg-[#003875] text-white"
                      : "bg-gray-100 text-gray-600 hover:bg-gray-200",
                  ].join(" ")}
                >
                  {label}
                </button>
              ))}
            </div>
          </CardHeader>

          <div className="px-6 pb-6">
            {historyLoading && (
              <p className="py-8 text-center text-sm text-gray-400">Loading history…</p>
            )}
            {!historyLoading && (!historyData || historyData.points.length === 0) && (
              <p className="py-8 text-center text-sm text-gray-400">
                No metrics recorded in the last {historyMinutes < 60 ? `${historyMinutes}m` : `${historyMinutes / 60}h`}.
              </p>
            )}
            {!historyLoading && historyData && historyData.points.length > 0 && (
              <MetricsHistoryChart points={historyData.points} />
            )}
          </div>
        </Card>
      )}

      {/* Reports tab */}
      {activeTab === "reports" && (
        <Card>
          <CardHeader>
            <CardTitle>Reports</CardTitle>
            {activeDeployment.status === "LIVE" && (
              <Button
                size="sm"
                variant="secondary"
                data-testid="generate-report-button"
                loading={reportMutation.isPending}
                onClick={() => reportMutation.mutate()}
              >
                Generate Report
              </Button>
            )}
          </CardHeader>

          <div className="px-6 pb-6">
            {downloadError && (
              <div
                data-testid="download-error"
                className="mb-4 rounded bg-red-50 px-4 py-2 text-sm text-red-700"
              >
                {downloadError}
              </div>
            )}

            {reportMutation.isSuccess && (
              <div className="mb-4 rounded bg-green-50 px-4 py-2 text-sm text-green-700">
                Report queued — generating PDF, Excel and PowerPoint…
              </div>
            )}

            {(reportJobs as ReportJob[]).length === 0 ? (
              <p className="py-6 text-center text-sm text-gray-400">
                No reports yet.{" "}
                {activeDeployment.status === "LIVE" && "Click Generate Report to create one."}
              </p>
            ) : (
              <table className="w-full text-sm" data-testid="reports-table">
                <thead>
                  <tr className="border-b border-gray-200 text-left text-xs font-medium uppercase text-gray-500">
                    <th className="pb-2 pr-4">Generated</th>
                    <th className="pb-2 pr-4">Status</th>
                    <th className="pb-2">Downloads</th>
                  </tr>
                </thead>
                <tbody>
                  {(reportJobs as ReportJob[]).map((job) => (
                    <tr key={job.id} className="border-b border-gray-100 last:border-0">
                      <td className="py-3 pr-4 text-gray-600">{formatDate(job.created_at)}</td>
                      <td className="py-3 pr-4">
                        <StatusBadge status={job.status} />
                      </td>
                      <td className="py-3">
                        {job.status === "DONE" ? (
                          <div className="flex gap-2">
                            {(["pdf", "excel", "ppt"] as DownloadFormat[]).map((fmt) => {
                              const key = `${fmt}_key` as keyof typeof job.result;
                              if (!job.result?.[key]) return null;
                              const busy = downloadingJob === `${job.id}-${fmt}`;
                              return (
                                <Button
                                  key={fmt}
                                  size="sm"
                                  variant="secondary"
                                  loading={busy}
                                  data-testid={`download-${fmt}-${job.id}`}
                                  onClick={() => void handleDownload(job.id, fmt)}
                                >
                                  {fmt.toUpperCase()}
                                </Button>
                              );
                            })}
                          </div>
                        ) : job.status === "FAILED" ? (
                          <span className="text-xs text-red-500">{job.error_message ?? "Failed"}</span>
                        ) : (
                          <span className="text-xs text-gray-400">Processing…</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </Card>
      )}
    </div>
  );
}
