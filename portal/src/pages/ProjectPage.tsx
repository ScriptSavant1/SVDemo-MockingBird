import { useState } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { projectsApi, type UpdateProjectBody } from "@/api/projects";
import { ingestionApi } from "@/api/ingestion";
import { useAuthStore } from "@/store/auth";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { StatusBadge } from "@/components/StatusBadge";
import { formatDate } from "@/utils/formatters";
import type { Project, Stub } from "@/api/types";

const ENVIRONMENTS = ["TEST", "STAGING", "PROD"] as const;

export function ProjectPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const role = useAuthStore((s) => s.user?.role);
  const canEdit = role === "ADMIN" || role === "SV_TEAM";

  const [deployingId, setDeployingId] = useState<string | null>(null);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [showEdit, setShowEdit] = useState(false);
  const [showArchiveConfirm, setShowArchiveConfirm] = useState(false);
  const [editForm, setEditForm] = useState<UpdateProjectBody>({});
  const [editError, setEditError] = useState<string | null>(null);

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

  const updateMutation = useMutation({
    mutationFn: (body: UpdateProjectBody) => projectsApi.update(projectId!, body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["project", projectId] });
      void qc.invalidateQueries({ queryKey: ["projects"] });
      setShowEdit(false);
      setEditError(null);
    },
    onError: (err: Error) => setEditError(err.message),
  });

  const archiveMutation = useMutation({
    mutationFn: () => projectsApi.archive(projectId!),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["projects"] });
      void navigate("/");
    },
  });

  async function handleDownloadZip(stubId: string) {
    setDownloadingId(stubId);
    try {
      const blob = await ingestionApi.downloadWiremockZip(projectId!, stubId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "wiremock.zip";
      a.click();
      URL.revokeObjectURL(url);
    } finally {
      setDownloadingId(null);
    }
  }

  function openEdit(p: Project) {
    setEditForm({
      name: p.name,
      team: p.team,
      environment: p.environment,
      expected_tps: p.expected_tps,
      description: p.description ?? "",
    });
    setEditError(null);
    setShowEdit(true);
  }

  function setEditField(k: keyof UpdateProjectBody, v: string | number) {
    setEditForm((prev) => ({ ...prev, [k]: v }));
    setEditError(null);
  }

  if (isPending) {
    return <div className="py-12 text-center text-gray-500">Loading…</div>;
  }

  return (
    <div>
      <div className="mb-6 flex items-start justify-between">
        <div>
          <Link to="/" className="text-sm text-[#00A9E0] hover:underline">← All projects</Link>
          <div className="mt-2 flex items-center gap-3">
            <h1 className="text-2xl font-bold text-gray-900">{project?.name ?? "Project"}</h1>
            {project && <StatusBadge status={project.status} />}
          </div>
          <p className="text-sm text-gray-500">{project?.description}</p>
          {project && (
            <p className="mt-1 text-xs text-gray-400">
              {project.team} · {project.environment} · {project.expected_tps.toLocaleString()} TPS target
            </p>
          )}
        </div>
        <div className="flex gap-2">
          {canEdit && project && project.status !== "ARCHIVED" && (
            <>
              <Button
                variant="secondary"
                size="sm"
                data-testid="edit-project-button"
                onClick={() => openEdit(project)}
              >
                Edit
              </Button>
              <Button
                variant="danger"
                size="sm"
                data-testid="archive-project-button"
                onClick={() => setShowArchiveConfirm(true)}
              >
                Archive
              </Button>
            </>
          )}
          <Link to={`/projects/${projectId}/ai-generate`}>
            <Button variant="secondary" size="sm">Generate with AI</Button>
          </Link>
          <Link to={`/projects/${projectId}/upload`}>
            <Button variant="secondary" size="sm">Upload Spec</Button>
          </Link>
        </div>
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
                  <div className="flex gap-2 flex-wrap">
                    {stub.status === "READY" && (
                      <>
                        <Button
                          size="sm"
                          loading={deployingId === stub.id}
                          onClick={() => deployMutation.mutate(stub.id)}
                        >
                          Deploy
                        </Button>
                        <Button
                          size="sm"
                          variant="secondary"
                          loading={downloadingId === stub.id}
                          onClick={() => void handleDownloadZip(stub.id)}
                          title="Download WireMock stub ZIP for local use"
                        >
                          Download ZIP
                        </Button>
                      </>
                    )}
                    {(stub.status === "LIVE" || stub.status === "SUSPENDED" || stub.status === "DEPLOYING") && (
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

      {/* Edit project modal */}
      {project && (
        <Modal open={showEdit} title="Edit Project" onClose={() => setShowEdit(false)}>
          <form
            data-testid="edit-project-form"
            onSubmit={(e) => {
              e.preventDefault();
              updateMutation.mutate(editForm);
            }}
            className="space-y-4"
          >
            {editError && (
              <div
                data-testid="edit-error"
                className="rounded bg-red-50 px-3 py-2 text-sm text-red-700"
              >
                {editError}
              </div>
            )}

            <div>
              <label className="block text-sm font-medium text-gray-700">Name</label>
              <input
                data-testid="edit-name-input"
                type="text"
                value={String(editForm.name ?? "")}
                onChange={(e) => setEditField("name", e.target.value)}
                required
                className="mt-1 block w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-[#00A9E0] focus:outline-none"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700">Team</label>
              <input
                data-testid="edit-team-input"
                type="text"
                value={String(editForm.team ?? "")}
                onChange={(e) => setEditField("team", e.target.value)}
                required
                className="mt-1 block w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-[#00A9E0] focus:outline-none"
              />
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className="block text-sm font-medium text-gray-700">Environment</label>
                <select
                  data-testid="edit-environment-select"
                  value={String(editForm.environment ?? "TEST")}
                  onChange={(e) => setEditField("environment", e.target.value)}
                  className="mt-1 block w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-[#00A9E0] focus:outline-none"
                >
                  {ENVIRONMENTS.map((env) => (
                    <option key={env} value={env}>{env}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700">Expected TPS</label>
                <input
                  data-testid="edit-tps-input"
                  type="number"
                  min={1}
                  max={100000}
                  value={editForm.expected_tps ?? 1000}
                  onChange={(e) => setEditField("expected_tps", parseInt(e.target.value, 10))}
                  className="mt-1 block w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-[#00A9E0] focus:outline-none"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700">Description</label>
              <textarea
                data-testid="edit-description-textarea"
                value={String(editForm.description ?? "")}
                onChange={(e) => setEditField("description", e.target.value)}
                rows={3}
                className="mt-1 block w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-[#00A9E0] focus:outline-none"
              />
            </div>

            <div className="flex justify-end gap-3 pt-2">
              <Button type="button" variant="secondary" onClick={() => setShowEdit(false)}>
                Cancel
              </Button>
              <Button
                type="submit"
                loading={updateMutation.isPending}
                data-testid="edit-submit-button"
              >
                Save
              </Button>
            </div>
          </form>
        </Modal>
      )}

      {/* Archive confirm modal */}
      <Modal
        open={showArchiveConfirm}
        title="Archive Project"
        onClose={() => setShowArchiveConfirm(false)}
      >
        <p className="mb-6 text-sm text-gray-600">
          This will archive <strong>{project?.name}</strong>. Active stubs will be suspended and
          the project will no longer appear on the dashboard. You can view it by searching for
          it directly.
        </p>
        <div className="flex justify-end gap-3">
          <Button
            variant="secondary"
            onClick={() => setShowArchiveConfirm(false)}
          >
            Cancel
          </Button>
          <Button
            variant="danger"
            loading={archiveMutation.isPending}
            data-testid="confirm-archive-button"
            onClick={() => archiveMutation.mutate()}
          >
            Archive
          </Button>
        </div>
      </Modal>
    </div>
  );
}
