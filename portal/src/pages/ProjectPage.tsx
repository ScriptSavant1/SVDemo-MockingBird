import { useState } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Trash2, ShieldCheck } from "lucide-react";
import { projectsApi, type UpdateProjectBody } from "@/api/projects";
import { ingestionApi } from "@/api/ingestion";
import { useAuthStore } from "@/store/auth";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { StatusBadge } from "@/components/StatusBadge";
import { formatDate } from "@/utils/formatters";
import { ApiError } from "@/api/client";
import type { Project, Stub, Protocol } from "@/api/types";

const UNDEPLOYABLE_STATUSES = new Set(["LIVE", "DEPLOYING"]);

const ENVIRONMENTS = ["TEST", "STAGING", "PROD"] as const;

export function ProjectPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const role = useAuthStore((s) => s.user?.role);
  const canEdit = role === "ADMIN" || role === "SV_TEAM";

  const [deployingId, setDeployingId] = useState<string | null>(null);
  const [generatingId, setGeneratingId] = useState<string | null>(null);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [jmeterDownloadingId, setJmeterDownloadingId] = useState<string | null>(null);
  const [deployError, setDeployError] = useState<string | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [showEdit, setShowEdit] = useState(false);
  const [showArchiveConfirm, setShowArchiveConfirm] = useState(false);
  const [editForm, setEditForm] = useState<UpdateProjectBody>({});
  const [editError, setEditError] = useState<string | null>(null);
  const [selectedStubIds, setSelectedStubIds] = useState<Set<string>>(new Set());
  const [stubDeleteTarget, setStubDeleteTarget] = useState<Stub | null>(null);
  const [showBulkStubDeleteConfirm, setShowBulkStubDeleteConfirm] = useState(false);
  const [stubDeleteError, setStubDeleteError] = useState<string | null>(null);

  // Per-stub TLS settings modal — protocol/mTLS/cert are set per stub (each
  // stub deploys as its own Docker image + EC2 instance), not per project.
  const [tlsStubTarget, setTlsStubTarget] = useState<Stub | null>(null);
  const [tlsProtocol, setTlsProtocol] = useState<Protocol>("HTTP");
  const [tlsMtlsEnabled, setTlsMtlsEnabled] = useState(false);
  const [tlsCertFiles, setTlsCertFiles] = useState<{
    server_cert: File | null;
    server_key: File | null;
    ca_bundle: File | null;
  }>({ server_cert: null, server_key: null, ca_bundle: null });
  const [tlsSaving, setTlsSaving] = useState(false);
  const [tlsError, setTlsError] = useState<string | null>(null);

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

  const generateMutation = useMutation({
    mutationFn: (stubId: string) => projectsApi.generate(projectId!, stubId),
    onMutate: (stubId) => {
      setGeneratingId(stubId);
      setDeployError(null);
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["stubs", projectId] });
    },
    onError: (err: Error) => setDeployError(err.message),
    onSettled: () => setGeneratingId(null),
  });

  const deployMutation = useMutation({
    mutationFn: (stubId: string) => projectsApi.deploy(projectId!, stubId),
    onMutate: (stubId) => {
      setDeployingId(stubId);
      setDeployError(null);
    },
    onSuccess: (_data, stubId) => {
      void navigate(`/projects/${projectId}/stubs/${stubId}`);
    },
    onError: (err: Error) => setDeployError(err.message),
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

  const deleteStubMutation = useMutation({
    mutationFn: (stubId: string) => projectsApi.deleteStub(projectId!, stubId),
    onSuccess: (_data, stubId) => {
      setStubDeleteTarget(null);
      setStubDeleteError(null);
      setSelectedStubIds((prev) => {
        const next = new Set(prev);
        next.delete(stubId);
        return next;
      });
      void qc.invalidateQueries({ queryKey: ["stubs", projectId] });
    },
    onError: (err: unknown) => {
      setStubDeleteError(err instanceof ApiError ? err.detail : "Delete failed. Please try again.");
    },
  });

  const bulkDeleteStubsMutation = useMutation({
    mutationFn: async (stubIds: string[]) => {
      const results = await Promise.allSettled(
        stubIds.map((id) => projectsApi.deleteStub(projectId!, id)),
      );
      const failed = results.filter((r) => r.status === "rejected").length;
      if (failed > 0) {
        throw new Error(`${failed} of ${stubIds.length} stub(s) failed to delete.`);
      }
    },
    onSuccess: () => {
      setShowBulkStubDeleteConfirm(false);
      setStubDeleteError(null);
      setSelectedStubIds(new Set());
      void qc.invalidateQueries({ queryKey: ["stubs", projectId] });
    },
    onError: (err: Error) => {
      setStubDeleteError(err.message);
      void qc.invalidateQueries({ queryKey: ["stubs", projectId] });
    },
  });

  function toggleStubSelected(stubId: string) {
    setSelectedStubIds((prev) => {
      const next = new Set(prev);
      if (next.has(stubId)) {
        next.delete(stubId);
      } else {
        next.add(stubId);
      }
      return next;
    });
  }

  function toggleSelectAllStubs(deletableStubs: Stub[]) {
    setSelectedStubIds((prev) =>
      prev.size === deletableStubs.length ? new Set() : new Set(deletableStubs.map((s) => s.id)),
    );
  }

  async function handleDownloadStubProject(stubId: string) {
    setDownloadingId(stubId);
    setDownloadError(null);
    try {
      const blob = await ingestionApi.downloadStubEngineZip(projectId!, stubId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "stub-engine.zip";
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setDownloadError(err instanceof Error ? err.message : "Download failed");
    } finally {
      setDownloadingId(null);
    }
  }

  async function handleDownloadNftScripts(stubId: string) {
    setJmeterDownloadingId(stubId);
    setDownloadError(null);
    try {
      const blob = await ingestionApi.downloadNftScriptsZip(projectId!, stubId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "nft-scripts.zip";
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setDownloadError(err instanceof Error ? err.message : "Download failed");
    } finally {
      setJmeterDownloadingId(null);
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

  function setEditField(k: keyof UpdateProjectBody, v: string | number | boolean) {
    setEditForm((prev) => ({ ...prev, [k]: v }));
    setEditError(null);
  }

  function handleEditSave(e: React.FormEvent) {
    e.preventDefault();
    setEditError(null);
    updateMutation.mutate(editForm);
  }

  function openTlsSettings(stub: Stub) {
    setTlsStubTarget(stub);
    setTlsProtocol(stub.protocol);
    setTlsMtlsEnabled(stub.mtls_enabled);
    setTlsCertFiles({ server_cert: null, server_key: null, ca_bundle: null });
    setTlsError(null);
  }

  // Switching back to HTTP silently drops mTLS intent client-side too — the
  // backend clears all TLS fields server-side when protocol -> HTTP.
  function setTlsProtocolValue(value: Protocol) {
    setTlsProtocol(value);
    if (value === "HTTP") setTlsMtlsEnabled(false);
    setTlsError(null);
  }

  async function handleTlsSave(e: React.FormEvent) {
    e.preventDefault();
    if (!tlsStubTarget || !projectId) return;
    setTlsError(null);

    const hasCertFiles = !!tlsCertFiles.server_cert || !!tlsCertFiles.server_key;
    if (hasCertFiles && (!tlsCertFiles.server_cert || !tlsCertFiles.server_key)) {
      setTlsError("Both a server certificate and a private key file are required to upload a certificate.");
      return;
    }

    setTlsSaving(true);
    try {
      let caBundleAvailableAfterSave = tlsStubTarget.has_ca_bundle;
      if (hasCertFiles && tlsCertFiles.server_cert && tlsCertFiles.server_key) {
        // Persists the cert + sets tls_cert_source=UPLOADED server-side — no
        // separate tls-config call needed just to record the upload.
        const result = await ingestionApi.uploadTlsCert(projectId, tlsStubTarget.id, {
          server_cert: tlsCertFiles.server_cert,
          server_key: tlsCertFiles.server_key,
          ca_bundle: tlsCertFiles.ca_bundle ?? undefined,
        });
        caBundleAvailableAfterSave = caBundleAvailableAfterSave || !!result.tls_ca_bundle_s3_key;
      }

      // Never send mtls_enabled: true unless a CA bundle actually exists —
      // the backend 422s otherwise.
      const safeMtlsEnabled = tlsMtlsEnabled && caBundleAvailableAfterSave;
      const protocolChanged = tlsProtocol !== tlsStubTarget.protocol;
      const mtlsChanged = safeMtlsEnabled !== tlsStubTarget.mtls_enabled;

      if (protocolChanged || mtlsChanged) {
        await projectsApi.updateStubTlsConfig(projectId, tlsStubTarget.id, {
          protocol: tlsProtocol,
          mtls_enabled: safeMtlsEnabled,
        });
      }

      void qc.invalidateQueries({ queryKey: ["stubs", projectId] });
      setTlsStubTarget(null);
    } catch (err) {
      setTlsError(err instanceof ApiError ? err.detail : "Failed to save TLS settings. Please try again.");
    } finally {
      setTlsSaving(false);
    }
  }

  if (isPending) {
    return <div className="py-12 text-center text-gray-500">Loading…</div>;
  }

  const tlsShowPanel = tlsProtocol === "HTTPS" || tlsProtocol === "BOTH";
  const tlsCaBundleAvailable = !!tlsStubTarget?.has_ca_bundle || !!tlsCertFiles.ca_bundle;

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
          <div className="flex items-center justify-between">
            <CardTitle>Stubs</CardTitle>
            {canEdit && selectedStubIds.size > 0 && (
              <Button
                size="sm"
                variant="danger"
                data-testid="bulk-delete-stubs-button"
                onClick={() => { setStubDeleteError(null); setShowBulkStubDeleteConfirm(true); }}
              >
                Delete Selected ({selectedStubIds.size})
              </Button>
            )}
          </div>
        </CardHeader>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200 text-left text-xs font-medium uppercase text-gray-500">
              {canEdit && (
                <th className="pb-2 pr-2 w-8">
                  <input
                    type="checkbox"
                    aria-label="Select all deletable stubs"
                    checked={
                      selectedStubIds.size > 0 &&
                      selectedStubIds.size === (stubs as Stub[]).filter((s) => !UNDEPLOYABLE_STATUSES.has(s.status)).length
                    }
                    onChange={() =>
                      toggleSelectAllStubs((stubs as Stub[]).filter((s) => !UNDEPLOYABLE_STATUSES.has(s.status)))
                    }
                  />
                </th>
              )}
              <th className="pb-2 pr-4">Name</th>
              <th className="pb-2 pr-4">Type</th>
              <th className="pb-2 pr-4">Status</th>
              <th className="pb-2 pr-4">Updated</th>
              <th className="pb-2" />
            </tr>
          </thead>
          <tbody>
            {(stubs as Stub[]).map((stub) => {
              const isUndeletable = UNDEPLOYABLE_STATUSES.has(stub.status);
              return (
              <tr key={stub.id} className="border-b border-gray-100 last:border-0">
                {canEdit && (
                  <td className="py-3 pr-2">
                    <input
                      type="checkbox"
                      aria-label={`Select ${stub.name}`}
                      checked={selectedStubIds.has(stub.id)}
                      disabled={isUndeletable}
                      onChange={() => toggleStubSelected(stub.id)}
                    />
                  </td>
                )}
                <td className="py-3 pr-4 font-medium text-gray-900">{stub.name}</td>
                <td className="py-3 pr-4 text-gray-500">{stub.stub_type}</td>
                <td className="py-3 pr-4">
                  <StatusBadge status={stub.status} />
                </td>
                <td className="py-3 pr-4 text-gray-400">{formatDate(stub.updated_at)}</td>
                <td className="py-3">
                  <div className="flex gap-2 flex-wrap items-center">
                    {stub.status === "READY" && !stub.generated_at && (
                      <Button
                        size="sm"
                        variant="secondary"
                        loading={generatingId === stub.id}
                        onClick={() => generateMutation.mutate(stub.id)}
                        title="Pre-generate WireMock mapping files before deploying"
                      >
                        Generate
                      </Button>
                    )}
                    {stub.status === "READY" && !!stub.generated_at && (
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
                          onClick={() => void handleDownloadStubProject(stub.id)}
                          title="Download the complete Spring Boot + WireMock project (pom.xml, Dockerfile, Java source, mappings). Run with: mvn spring-boot:run"
                        >
                          Download Stub Project
                        </Button>
                        <Button
                          size="sm"
                          variant="secondary"
                          loading={jmeterDownloadingId === stub.id}
                          onClick={() => void handleDownloadNftScripts(stub.id)}
                          title="Download auto-generated, ready-to-run NFT scripts for this stub: a JMeter test plan and a LoadRunner DevWeb (VuGen) project, in one zip"
                        >
                          Download NFT Scripts
                        </Button>
                      </>
                    )}
                    {(stub.status === "LIVE" || stub.status === "SUSPENDED" || stub.status === "DEPLOYING") && (
                      <Link to={`/projects/${projectId}/stubs/${stub.id}`}>
                        <Button size="sm" variant="secondary">View</Button>
                      </Link>
                    )}
                    {canEdit && (
                      <button
                        type="button"
                        title="TLS settings"
                        data-testid="stub-tls-settings-button"
                        onClick={() => openTlsSettings(stub)}
                        className="rounded p-1.5 text-gray-400 hover:bg-blue-50 hover:text-blue-600"
                      >
                        <ShieldCheck size={14} />
                      </button>
                    )}
                    {canEdit && (
                      <button
                        type="button"
                        title={isUndeletable ? "Suspend this stub's deployment before deleting" : "Delete stub"}
                        data-testid="delete-stub-button"
                        disabled={isUndeletable}
                        onClick={() => { setStubDeleteError(null); setStubDeleteTarget(stub); }}
                        className="rounded p-1.5 text-gray-400 hover:bg-red-50 hover:text-red-600 disabled:cursor-not-allowed disabled:opacity-30 disabled:hover:bg-transparent disabled:hover:text-gray-400"
                      >
                        <Trash2 size={14} />
                      </button>
                    )}
                  </div>
                </td>
              </tr>
              );
            })}
            {stubs.length === 0 && (
              <tr>
                <td colSpan={canEdit ? 6 : 5} className="py-8 text-center text-gray-400">No stubs yet.</td>
              </tr>
            )}
          </tbody>
        </table>
      </Card>

      {deployError && (
        <div className="mt-3 rounded bg-red-50 px-3 py-2 text-sm text-red-700">
          <strong>Action failed:</strong> {deployError}
        </div>
      )}
      {downloadError && (
        <div className="mt-3 rounded bg-red-50 px-3 py-2 text-sm text-red-700">
          <strong>Download failed:</strong> {downloadError}
        </div>
      )}
      {stubDeleteError && (
        <div className="mt-3 rounded bg-red-50 px-3 py-2 text-sm text-red-700">
          <strong>Delete failed:</strong> {stubDeleteError}
        </div>
      )}

      {/* Edit project modal */}
      {project && (
        <Modal open={showEdit} title="Edit Project" onClose={() => setShowEdit(false)}>
          <form
            data-testid="edit-project-form"
            onSubmit={(e) => void handleEditSave(e)}
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

      {/* Per-stub TLS settings modal */}
      {tlsStubTarget && (
        <Modal
          open={!!tlsStubTarget}
          title={`TLS Settings — ${tlsStubTarget.name}`}
          onClose={() => { setTlsStubTarget(null); setTlsError(null); }}
        >
          <form
            data-testid="stub-tls-form"
            onSubmit={(e) => void handleTlsSave(e)}
            className="space-y-4"
          >
            {tlsError && (
              <div
                data-testid="stub-tls-error"
                className="rounded bg-red-50 px-3 py-2 text-sm text-red-700"
              >
                {tlsError}
              </div>
            )}

            <p className="text-xs text-gray-500">
              {tlsStubTarget.has_uploaded_cert ? "Custom certificate on file." : "Auto-generated certificate in use."}
              {tlsStubTarget.has_ca_bundle ? " CA bundle on file." : ""}
            </p>

            <div>
              <label className="block text-sm font-medium text-gray-700">Stub Protocol</label>
              <select
                data-testid="stub-tls-protocol-select"
                value={tlsProtocol}
                onChange={(e) => setTlsProtocolValue(e.target.value as Protocol)}
                className="mt-1 block w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-[#00A9E0] focus:outline-none"
              >
                <option value="HTTP">HTTP</option>
                <option value="HTTPS">HTTPS</option>
                <option value="BOTH">HTTP + HTTPS</option>
              </select>
            </div>

            {tlsShowPanel && (
              <div className="space-y-3 rounded border border-gray-200 p-4" data-testid="stub-tls-cert-panel">
                <p className="text-sm font-medium text-gray-700">TLS Certificate</p>

                <div className="space-y-2 rounded bg-gray-50 p-3">
                  <div>
                    <label className="block text-xs font-medium text-gray-700">
                      Server certificate (.crt/.pem)
                    </label>
                    <input
                      data-testid="stub-tls-cert-file-input"
                      type="file"
                      accept=".crt,.pem"
                      onChange={(e) =>
                        setTlsCertFiles((prev) => ({ ...prev, server_cert: e.target.files?.[0] ?? null }))
                      }
                      className="mt-1 block w-full text-sm"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-700">
                      Private key (.key/.pem)
                    </label>
                    <input
                      data-testid="stub-tls-key-file-input"
                      type="file"
                      accept=".key,.pem"
                      onChange={(e) =>
                        setTlsCertFiles((prev) => ({ ...prev, server_key: e.target.files?.[0] ?? null }))
                      }
                      className="mt-1 block w-full text-sm"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-700">
                      CA bundle (.pem/.crt) — required to enable mutual TLS below
                    </label>
                    <input
                      data-testid="stub-tls-ca-bundle-file-input"
                      type="file"
                      accept=".pem,.crt"
                      onChange={(e) =>
                        setTlsCertFiles((prev) => ({ ...prev, ca_bundle: e.target.files?.[0] ?? null }))
                      }
                      className="mt-1 block w-full text-sm"
                    />
                  </div>
                </div>

                <label
                  className="flex items-center gap-2 text-sm text-gray-700"
                  title={!tlsCaBundleAvailable ? "Upload a CA bundle above to enable mutual TLS" : undefined}
                >
                  <input
                    data-testid="stub-tls-mtls-checkbox"
                    type="checkbox"
                    checked={tlsMtlsEnabled}
                    disabled={!tlsCaBundleAvailable}
                    onChange={(e) => setTlsMtlsEnabled(e.target.checked)}
                  />
                  Require client certificate (mutual TLS)
                </label>
                {!tlsCaBundleAvailable && (
                  <p className="text-xs text-gray-500">
                    Upload a CA bundle above to enable mutual TLS.
                  </p>
                )}
              </div>
            )}

            <div className="flex justify-end gap-3 pt-2">
              <Button
                type="button"
                variant="secondary"
                onClick={() => { setTlsStubTarget(null); setTlsError(null); }}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                loading={tlsSaving}
                data-testid="stub-tls-save-button"
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

      {/* Single stub delete confirm modal */}
      <Modal
        open={!!stubDeleteTarget}
        title="Delete Stub"
        onClose={() => { setStubDeleteTarget(null); setStubDeleteError(null); }}
      >
        <p className="mb-6 text-sm text-gray-600">
          Permanently delete <strong>{stubDeleteTarget?.name}</strong>? This cannot be undone.
        </p>
        <div className="flex justify-end gap-3">
          <Button variant="secondary" onClick={() => { setStubDeleteTarget(null); setStubDeleteError(null); }}>
            Cancel
          </Button>
          <Button
            variant="danger"
            loading={deleteStubMutation.isPending}
            data-testid="confirm-delete-stub-button"
            onClick={() => stubDeleteTarget && deleteStubMutation.mutate(stubDeleteTarget.id)}
          >
            Delete
          </Button>
        </div>
      </Modal>

      {/* Bulk stub delete confirm modal */}
      <Modal
        open={showBulkStubDeleteConfirm}
        title="Delete Selected Stubs"
        onClose={() => setShowBulkStubDeleteConfirm(false)}
      >
        <p className="mb-6 text-sm text-gray-600">
          Permanently delete <strong>{selectedStubIds.size}</strong> selected stub
          {selectedStubIds.size === 1 ? "" : "s"}? This cannot be undone.
        </p>
        <div className="flex justify-end gap-3">
          <Button variant="secondary" onClick={() => setShowBulkStubDeleteConfirm(false)}>
            Cancel
          </Button>
          <Button
            variant="danger"
            loading={bulkDeleteStubsMutation.isPending}
            data-testid="confirm-bulk-delete-stubs-button"
            onClick={() => bulkDeleteStubsMutation.mutate(Array.from(selectedStubIds))}
          >
            Delete
          </Button>
        </div>
      </Modal>
    </div>
  );
}
