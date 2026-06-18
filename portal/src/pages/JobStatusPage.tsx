import { useParams, Link, useSearchParams } from "react-router-dom";
import { useJobPoller } from "@/hooks/useJobPoller";
import { JobProgress, buildJobSteps } from "@/components/JobProgress";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";

export function JobStatusPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const [searchParams] = useSearchParams();
  const projectId = searchParams.get("projectId");

  const { data: job, isPending, isError } = useJobPoller(jobId ?? null);

  if (isPending) {
    return <div className="py-12 text-center text-gray-400">Starting…</div>;
  }

  if (isError) {
    return (
      <div className="rounded bg-red-50 px-4 py-3 text-sm text-red-700">
        Could not load job status.{" "}
        {projectId && (
          <Link to={`/projects/${projectId}`} className="underline">
            Return to project
          </Link>
        )}
      </div>
    );
  }

  const steps = buildJobSteps(job?.status, job?.type);
  const isDone = job?.status === "DONE";
  const isFailed = job?.status === "FAILED";

  return (
    <div className="max-w-xl">
      <div className="mb-6">
        {projectId && (
          <Link to={`/projects/${projectId}`} className="text-sm text-[#00A9E0] hover:underline">
            ← Back to project
          </Link>
        )}
        <h1 className="mt-2 text-2xl font-bold text-gray-900">
          {isDone ? "Stubs generated" : isFailed ? "Generation failed" : "Generating stubs…"}
        </h1>
        <p className="mt-1 text-sm text-gray-500">
          Job <span className="font-mono text-xs">{jobId}</span>
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Progress</CardTitle>
          <StatusChip status={job?.status} />
        </CardHeader>

        <JobProgress steps={steps} />

        {isFailed && job?.error_message && (
          <div className="mt-4 rounded bg-red-50 p-3 text-sm text-red-700" role="alert">
            {job.error_message}
          </div>
        )}

        {isDone && projectId && (
          <div className="mt-6 flex items-center gap-3">
            <Link to={`/projects/${projectId}`}>
              <Button variant="primary">View project &amp; deploy</Button>
            </Link>
          </div>
        )}

        {isFailed && projectId && (
          <div className="mt-6">
            <Link to={`/projects/${projectId}/upload`}>
              <Button variant="ghost">Try uploading again</Button>
            </Link>
          </div>
        )}
      </Card>
    </div>
  );
}

function StatusChip({ status }: { status?: string }) {
  const map: Record<string, string> = {
    QUEUED: "bg-yellow-100 text-yellow-700",
    RUNNING: "bg-blue-100 text-blue-700",
    DONE: "bg-green-100 text-green-700",
    FAILED: "bg-red-100 text-red-700",
  };
  return (
    <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${map[status ?? ""] ?? "bg-gray-100 text-gray-600"}`}>
      {status ?? "…"}
    </span>
  );
}
