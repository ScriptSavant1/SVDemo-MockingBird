import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { uploadSpec, type UploadSpecTlsOptions } from "@/api/ingestion";
import { projectsApi } from "@/api/projects";
import { ApiError } from "@/api/client";
import { UploadZone } from "@/components/UploadZone";
import { BatchUploadZone, type BatchFile } from "@/components/BatchUploadZone";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { IssueList } from "@/components/IssueList";
import { pairHttpCaptureFiles, mergeHttpCaptureFiles } from "@/lib/httpCapturePairing";
import { zipHttpCaptureFiles } from "@/lib/zipHttpCaptureFiles";
import type { IngestionResult, Protocol } from "@/api/types";

type BatchStatus = "pending" | "uploading" | "generating" | "done" | "error";
type BatchGroupMode = "combined" | "separate";

interface BatchRow {
  key: string;
  name: string;
  status: BatchStatus;
  /** One line, e.g. "MB-UPL-004 · Referenced file is missing from the upload: a.xml". */
  error?: string;
  /** Every validation error behind `error`, when there is more than one. */
  errorDetails?: string[];
  warnings?: string[];
}

/** The coded one-liner for a failed validation, falling back to the first raw error. */
function failureLine(result: IngestionResult): string {
  if (result.error_code && result.error_summary) return `${result.error_code} · ${result.error_summary}`;
  return result.errors[0] ?? "File failed validation.";
}

function stripExtension(filename: string): string {
  return filename.replace(/\.[^.]+$/, "");
}

export function UploadPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();

  // Protocol/TLS is chosen once here and applies to every stub this upload
  // action creates (single file, or every item in a batch) — each stub is
  // its own deployable unit, so this is no longer a project-level setting.
  const [protocol, setProtocol] = useState<Protocol>("HTTP");
  const [certSource, setCertSource] = useState<"AUTO_GENERATED" | "UPLOADED">("AUTO_GENERATED");
  const [mtlsEnabled, setMtlsEnabled] = useState(false);
  const [tlsCertFiles, setTlsCertFiles] = useState<{
    server_cert: File | null;
    server_key: File | null;
    ca_bundle: File | null;
  }>({ server_cert: null, server_key: null, ca_bundle: null });

  function setProtocolValue(value: Protocol) {
    setProtocol(value);
    if (value === "HTTP") {
      setMtlsEnabled(false);
      setCertSource("AUTO_GENERATED");
      setTlsCertFiles({ server_cert: null, server_key: null, ca_bundle: null });
    }
  }

  // Never let the UI submit mtls_enabled: true without a CA bundle actually
  // attached in this same upload — the ingestion endpoint returns
  // valid: false otherwise, and the checkbox above is disabled to match.
  function buildTlsOptions(): UploadSpecTlsOptions {
    if (protocol === "HTTP") return { protocol: "HTTP" };
    return {
      protocol,
      mtls_enabled: mtlsEnabled && !!tlsCertFiles.ca_bundle,
      server_cert: certSource === "UPLOADED" ? tlsCertFiles.server_cert ?? undefined : undefined,
      server_key: certSource === "UPLOADED" ? tlsCertFiles.server_key ?? undefined : undefined,
      ca_bundle: tlsCertFiles.ca_bundle ?? undefined,
    };
  }

  const [batchMode, setBatchMode] = useState(false);

  // Single-file mode
  const [stubName, setStubName] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [errorLine, setErrorLine] = useState<string | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const [warnings, setWarnings] = useState<string[]>([]);

  // Batch mode — many files at once.
  const [batchFiles, setBatchFiles] = useState<BatchFile[]>([]);
  const [batchRunning, setBatchRunning] = useState(false);
  const [batchRows, setBatchRows] = useState<BatchRow[]>([]);
  // "combined" (default): all files describe one downstream system (e.g. several
  // operations of the same client's API) — bundled into ONE stub, mirroring how
  // the real service they're standing in for actually works (one base URL, many
  // endpoints). "separate": files are genuinely unrelated, independently
  // deployable services — one stub per file/pair, each its own EC2 when deployed.
  const [groupMode, setGroupMode] = useState<BatchGroupMode>("combined");
  const [combinedStubName, setCombinedStubName] = useState("");

  // Content of each batch file, read once files change — pairing checks
  // content before filename (a capture tool doesn't always name a file
  // consistently with what it contains; seen live with a file named
  // "..._Request.txt" that was pure response data). Read here rather than
  // inside pairHttpCaptureFiles because file reads are async and that
  // function stays a plain synchronous classifier.
  const [batchFileContents, setBatchFileContents] = useState<Map<string, string>>(new Map());
  useEffect(() => {
    let cancelled = false;
    void Promise.all(
      batchFiles.map(async ({ file, key }) => [key, await file.text()] as const),
    ).then((entries) => {
      if (!cancelled) setBatchFileContents(new Map(entries));
    });
    return () => {
      cancelled = true;
    };
  }, [batchFiles]);

  // Request/response halves (e.g. CA LISA *_Request_*.txt / *_Response_*.txt)
  // are auto-paired and combined into one upload per pair — mirrors the same
  // timestamp/filename-prefix matching the backend already uses for ZIP
  // uploads (see parser-worker/detector.py's _pair_files). Anything else
  // (Postman, OpenAPI, an already-combined .txt) passes through standalone.
  const batchPairing = useMemo(
    () =>
      pairHttpCaptureFiles(
        batchFiles.map(({ file, key }) => ({
          name: file.name,
          key,
          content: batchFileContents.get(key),
        })),
      ),
    [batchFiles, batchFileContents],
  );
  const batchFileByKey = useMemo(
    () => new Map(batchFiles.map((f) => [f.key, f.file])),
    [batchFiles],
  );
  const batchUploadCount = batchPairing.pairs.length + batchPairing.unpaired.length;

  // A Mockingbird xlsx stub template (+ its data/ folder of response/lookup
  // files) has nothing in common with CA LISA request/response pairing — one
  // workbook defines many stubs by name already, so "combined vs separate"
  // and per-file pairing preview don't apply. Detected purely by extension
  // here (a client-side UX hint only); the server always decides the real
  // format from content, same as every other upload path.
  const isXlsxMode = useMemo(
    () => batchFiles.some(({ file }) => /\.(xlsx|xlsm)$/i.test(file.name)),
    [batchFiles],
  );

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!file || !projectId) return;
    setErrorLine(null);
    setErrors([]);
    setWarnings([]);
    setUploading(true);

    try {
      const result = await uploadSpec(projectId, stubName || file.name, file, buildTlsOptions());

      if (!result.valid || !result.stub_id) {
        setErrorLine(failureLine(result));
        setErrors(result.errors);
        setWarnings(result.warnings);
        return;
      }

      if (result.warnings.length > 0) setWarnings(result.warnings);

      const { job_id } = await projectsApi.generate(projectId, result.stub_id);
      void navigate(`/jobs/${job_id}?projectId=${projectId}`);
    } catch (err) {
      setErrorLine(err instanceof ApiError ? err.userMessage : "Upload failed. Please try again.");
    } finally {
      setUploading(false);
    }
  }

  async function handleBatchSubmit(e: FormEvent) {
    e.preventDefault();
    if (batchFiles.length === 0 || !projectId) return;

    setBatchRunning(true);

    let items: { key: string; name: string; file: File }[];

    if (groupMode === "combined" || isXlsxMode) {
      // One upload for the whole batch: zip every raw file as-is and let the
      // backend's existing ZIP-upload dispatch (parser-worker's
      // _detect_and_parse_zip) sniff the xlsx shape first, or otherwise fall
      // back to CA LISA request/response pairing — same zip-building call
      // either way, zipHttpCaptureFiles is grouping-agnostic. For xlsx mode
      // this "name" becomes the overall Stub record's display name only —
      // the workbook's own "Stub Name" column supplies each individual
      // operation's real name (see upload.py's override-skip for this format).
      const name = combinedStubName.trim() || (isXlsxMode ? "Xlsx Stub Package" : "Combined Spec");
      const zip = await zipHttpCaptureFiles(
        batchFiles.map((f) => f.file),
        name,
      );
      items = [{ key: "combined", name, file: zip }];
    } else {
      // One stub per file (or per matched request/response pair) — resolve
      // pairs into merged combined files first, so the upload list below is
      // items to upload (a pair counts as one), not raw selected files.
      items = [];
      for (const { request, response } of batchPairing.pairs) {
        const reqFile = batchFileByKey.get(request.key);
        const respFile = batchFileByKey.get(response.key);
        if (!reqFile || !respFile) continue;
        const merged = await mergeHttpCaptureFiles(reqFile, respFile);
        // The merged File keeps both names (needed for the backend's CA LISA
        // status-code inference — see mergeHttpCaptureFiles) but the stub name
        // shown to the user and sent as stub_name is just the request's name.
        items.push({ key: `${request.key}::${response.key}`, name: stripExtension(reqFile.name), file: merged });
      }
      for (const { key } of batchPairing.unpaired) {
        const f = batchFileByKey.get(key);
        if (!f) continue;
        items.push({ key, name: stripExtension(f.name), file: f });
      }
    }

    setBatchRows(items.map(({ key, name }) => ({ key, name, status: "pending" })));

    // Sequential, per-item error isolation — one bad item doesn't block the rest.
    for (const { file: f, key, name: stubNameForFile } of items) {
      setBatchRows((rows) =>
        rows.map((r) => (r.key === key ? { ...r, status: "uploading" } : r)),
      );

      try {
        const result = await uploadSpec(projectId, stubNameForFile, f, buildTlsOptions());
        if (!result.valid || !result.stub_id) {
          const msg = failureLine(result);
          setBatchRows((rows) =>
            rows.map((r) =>
              r.key === key
                ? { ...r, status: "error", error: msg, errorDetails: result.errors, warnings: result.warnings }
                : r,
            ),
          );
          continue;
        }

        setBatchRows((rows) =>
          rows.map((r) => (r.key === key ? { ...r, status: "generating", warnings: result.warnings } : r)),
        );
        await projectsApi.generate(projectId, result.stub_id);
        setBatchRows((rows) =>
          rows.map((r) => (r.key === key ? { ...r, status: "done" } : r)),
        );
      } catch (err) {
        const msg = err instanceof ApiError ? err.userMessage : "Upload failed.";
        setBatchRows((rows) =>
          rows.map((r) => (r.key === key ? { ...r, status: "error", error: msg } : r)),
        );
      }
    }

    setBatchRunning(false);
  }

  const batchDone = batchRows.length > 0 && batchRows.every((r) => r.status === "done" || r.status === "error");
  const batchSucceeded = batchRows.filter((r) => r.status === "done").length;
  const batchFailed = batchRows.filter((r) => r.status === "error").length;

  return (
    <div className="max-w-2xl">
      <div className="mb-6">
        <Link to={`/projects/${projectId}`} className="text-sm text-[#00A9E0] hover:underline">
          ← Back to project
        </Link>
        <h1 className="mt-2 text-2xl font-bold text-gray-900">
          {batchMode ? "Upload Multiple Spec Files" : "Upload Spec File"}
        </h1>
        <p className="mt-1 text-sm text-gray-500">
          {batchMode
            ? "Upload several .txt / .json files at once — combine them into one stub, or keep each as its own. Or drop a Mockingbird xlsx stub template + its data files to generate every stub it defines."
            : "Upload a .txt (raw HTTP pairs) or .json (Postman v2.1) spec to generate stubs."}
        </p>
      </div>

      <div className="mb-5 rounded border border-gray-200 p-4" data-testid="upload-protocol-panel">
        <label htmlFor="upload-protocol-select" className="block text-sm font-medium text-gray-700">
          Stub Protocol
        </label>
        <p className="mt-0.5 text-xs text-gray-500">
          Applies to every stub created by this upload.
        </p>
        <select
          id="upload-protocol-select"
          data-testid="upload-protocol-select"
          value={protocol}
          onChange={(e) => setProtocolValue(e.target.value as Protocol)}
          disabled={uploading || batchRunning}
          className="mt-2 block w-full max-w-xs rounded border border-gray-300 px-3 py-2 text-sm
                     focus:border-[#003875] focus:outline-none focus:ring-1 focus:ring-[#003875]
                     disabled:bg-gray-50"
        >
          <option value="HTTP">HTTP</option>
          <option value="HTTPS">HTTPS</option>
          <option value="BOTH">HTTP + HTTPS</option>
        </select>

        {protocol !== "HTTP" && (
          <div className="mt-4 space-y-3 rounded border border-gray-200 p-4" data-testid="upload-tls-panel">
            <p className="text-sm font-medium text-gray-700">TLS Certificate</p>

            <div className="flex gap-4">
              <label className="flex items-center gap-2 text-sm text-gray-700">
                <input
                  type="radio"
                  name="upload-cert-source"
                  data-testid="upload-cert-source-auto-radio"
                  checked={certSource === "AUTO_GENERATED"}
                  onChange={() => setCertSource("AUTO_GENERATED")}
                  disabled={uploading || batchRunning}
                />
                Auto-generate (recommended)
              </label>
              <label className="flex items-center gap-2 text-sm text-gray-700">
                <input
                  type="radio"
                  name="upload-cert-source"
                  data-testid="upload-cert-source-upload-radio"
                  checked={certSource === "UPLOADED"}
                  onChange={() => setCertSource("UPLOADED")}
                  disabled={uploading || batchRunning}
                />
                Upload your own
              </label>
            </div>

            {certSource === "AUTO_GENERATED" && (
              <p className="text-xs text-gray-500">
                A self-signed certificate will be auto-generated for each stub created by this upload.
              </p>
            )}

            {certSource === "UPLOADED" && (
              <div className="space-y-2 rounded bg-gray-50 p-3">
                <div>
                  <label className="block text-xs font-medium text-gray-700">
                    Server certificate (.crt/.pem)
                  </label>
                  <input
                    data-testid="upload-tls-cert-file-input"
                    type="file"
                    accept=".crt,.pem"
                    disabled={uploading || batchRunning}
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
                    data-testid="upload-tls-key-file-input"
                    type="file"
                    accept=".key,.pem"
                    disabled={uploading || batchRunning}
                    onChange={(e) =>
                      setTlsCertFiles((prev) => ({ ...prev, server_key: e.target.files?.[0] ?? null }))
                    }
                    className="mt-1 block w-full text-sm"
                  />
                </div>
              </div>
            )}

            <div>
              <label className="block text-xs font-medium text-gray-700">
                CA bundle (.pem/.crt) — required to enable mutual TLS below
              </label>
              <input
                data-testid="upload-tls-ca-bundle-file-input"
                type="file"
                accept=".pem,.crt"
                disabled={uploading || batchRunning}
                onChange={(e) =>
                  setTlsCertFiles((prev) => ({ ...prev, ca_bundle: e.target.files?.[0] ?? null }))
                }
                className="mt-1 block w-full text-sm"
              />
            </div>

            <label
              className="flex items-center gap-2 text-sm text-gray-700"
              title={!tlsCertFiles.ca_bundle ? "Upload a CA bundle above to enable mutual TLS" : undefined}
            >
              <input
                data-testid="upload-mtls-checkbox"
                type="checkbox"
                checked={mtlsEnabled}
                disabled={!tlsCertFiles.ca_bundle || uploading || batchRunning}
                onChange={(e) => setMtlsEnabled(e.target.checked)}
              />
              Require client certificate (mutual TLS)
            </label>
            {!tlsCertFiles.ca_bundle && (
              <p className="text-xs text-gray-500">
                Upload a CA bundle above to enable mutual TLS.
              </p>
            )}
          </div>
        )}
      </div>

      <div className="mb-4 flex gap-2">
        <button
          type="button"
          data-testid="mode-single"
          onClick={() => setBatchMode(false)}
          disabled={uploading || batchRunning}
          className={`rounded px-3 py-1.5 text-sm font-medium ${
            !batchMode ? "bg-[#003875] text-white" : "bg-gray-100 text-gray-600 hover:bg-gray-200"
          }`}
        >
          Single spec
        </button>
        <button
          type="button"
          data-testid="mode-batch"
          onClick={() => setBatchMode(true)}
          disabled={uploading || batchRunning}
          className={`rounded px-3 py-1.5 text-sm font-medium ${
            batchMode ? "bg-[#003875] text-white" : "bg-gray-100 text-gray-600 hover:bg-gray-200"
          }`}
        >
          Multiple files (batch)
        </button>
      </div>

      {!batchMode ? (
        <form onSubmit={(e) => void handleSubmit(e)}>
          <Card>
            <CardHeader>
              <CardTitle>Spec details</CardTitle>
            </CardHeader>

            <div className="space-y-5">
              <div>
                <label htmlFor="stub-name" className="block text-sm font-medium text-gray-700">
                  Stub name{" "}
                  <span className="font-normal text-gray-400">(optional — defaults to filename)</span>
                </label>
                <input
                  id="stub-name"
                  type="text"
                  placeholder="e.g. Payment API stub"
                  value={stubName}
                  onChange={(e) => setStubName(e.target.value)}
                  disabled={uploading}
                  className="mt-1 block w-full rounded border border-gray-300 px-3 py-2 text-sm
                             focus:border-[#003875] focus:outline-none focus:ring-1 focus:ring-[#003875]
                             disabled:bg-gray-50"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700">Spec file</label>
                <div className="mt-1">
                  <UploadZone file={file} onChange={setFile} disabled={uploading} />
                </div>
              </div>

              {errorLine && (
                <div className="space-y-2 rounded bg-red-50 p-3" role="alert">
                  <p className="text-sm font-medium text-red-700" data-testid="upload-error-line">{errorLine}</p>
                  {errors.length > 1 && (
                    <IssueList label={`Details (${errors.length})`} items={errors} tone="error" />
                  )}
                </div>
              )}

              <IssueList label={`Warnings (${warnings.length})`} items={warnings} tone="warning" testId="upload-warnings" />

              <div className="flex justify-end gap-3 pt-2">
                <Link to={`/projects/${projectId}`}>
                  <Button type="button" variant="ghost" disabled={uploading}>Cancel</Button>
                </Link>
                <Button
                  type="submit"
                  loading={uploading}
                  disabled={!file}
                >
                  Upload &amp; Generate
                </Button>
              </div>
            </div>
          </Card>
        </form>
      ) : (
        <form onSubmit={(e) => void handleBatchSubmit(e)}>
          <Card>
            <CardHeader>
              <CardTitle>Spec files</CardTitle>
            </CardHeader>

            <div className="space-y-5">
              {isXlsxMode ? (
                <div className="rounded border border-blue-200 bg-blue-50 p-3 text-xs text-blue-700" data-testid="xlsx-mode-banner">
                  <span className="font-medium">Mockingbird xlsx stub template detected.</span>{" "}
                  Every stub defined in the workbook's "Stubs" tab is created automatically, using
                  its own name from the sheet — the grouping choice below doesn't apply and is hidden.
                </div>
              ) : (
                <div>
                  <label className="block text-sm font-medium text-gray-700">
                    How should these files become stubs?
                  </label>
                  <div className="mt-2 space-y-2">
                    <label className="flex cursor-pointer items-start gap-2 rounded border border-gray-200 p-3 text-sm has-[:checked]:border-[#003875] has-[:checked]:bg-blue-50">
                      <input
                        type="radio"
                        name="group-mode"
                        value="combined"
                        checked={groupMode === "combined"}
                        onChange={() => setGroupMode("combined")}
                        disabled={batchRunning}
                        className="mt-0.5"
                      />
                      <span>
                        <span className="font-medium text-gray-800">One stub for all files</span>{" "}
                        <span className="text-xs text-gray-500">(recommended)</span>
                        <p className="mt-0.5 text-xs text-gray-500">
                          Use this when the files describe one downstream system with several
                          operations — e.g. a client's CreateAdviser and GetAdvisers endpoints.
                          They deploy together as one virtual service with one URL, matching how
                          the real service actually works.
                        </p>
                      </span>
                    </label>
                    <label className="flex cursor-pointer items-start gap-2 rounded border border-gray-200 p-3 text-sm has-[:checked]:border-[#003875] has-[:checked]:bg-blue-50">
                      <input
                        type="radio"
                        name="group-mode"
                        value="separate"
                        checked={groupMode === "separate"}
                        onChange={() => setGroupMode("separate")}
                        disabled={batchRunning}
                        className="mt-0.5"
                      />
                      <span>
                        <span className="font-medium text-gray-800">One stub per file</span>
                        <p className="mt-0.5 text-xs text-gray-500">
                          Use this when the files are genuinely unrelated, independently
                          deployable services — each gets its own stub and its own URL when deployed.
                        </p>
                      </span>
                    </label>
                  </div>
                </div>
              )}

              <div>
                <label className="block text-sm font-medium text-gray-700">Spec files</label>
                <div className="mt-1">
                  <BatchUploadZone
                    files={batchFiles}
                    onChange={setBatchFiles}
                    disabled={batchRunning}
                  />
                </div>
              </div>

              {(groupMode === "combined" || isXlsxMode) && batchFiles.length > 0 && (
                <div>
                  <label htmlFor="combined-stub-name" className="block text-sm font-medium text-gray-700">
                    {isXlsxMode ? "Package name" : "Stub name"}{" "}
                    <span className="font-normal text-gray-400">
                      {isXlsxMode
                        ? "(optional — defaults to \"Xlsx Stub Package\"; individual stub names come from the sheet)"
                        : "(optional — defaults to \"Combined Spec\")"}
                    </span>
                  </label>
                  <input
                    id="combined-stub-name"
                    type="text"
                    placeholder={isXlsxMode ? "e.g. Payments SV Project" : "e.g. Payments Client API"}
                    value={combinedStubName}
                    onChange={(e) => setCombinedStubName(e.target.value)}
                    disabled={batchRunning}
                    className="mt-1 block w-full rounded border border-gray-300 px-3 py-2 text-sm
                               focus:border-[#003875] focus:outline-none focus:ring-1 focus:ring-[#003875]
                               disabled:bg-gray-50"
                  />
                </div>
              )}

              {!isXlsxMode && groupMode === "separate" && batchRows.length === 0 && batchPairing.pairs.length > 0 && (
                <div className="rounded bg-blue-50 p-3 text-xs text-blue-700" data-testid="batch-pairing-preview">
                  Detected {batchPairing.pairs.length} request/response pair
                  {batchPairing.pairs.length === 1 ? "" : "s"} — each will be combined
                  automatically into its own stub:
                  <ul className="mt-1 list-inside list-disc space-y-0.5">
                    {batchPairing.pairs.map(({ request, response }) => (
                      <li key={`${request.key}::${response.key}`}>
                        {request.name} + {response.name}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {batchRows.length > 0 && (
                <ul className="divide-y divide-gray-100 rounded-lg border border-gray-200">
                  {batchRows.map((row) => (
                    <li key={row.key} className="space-y-1.5 px-3 py-2 text-sm">
                      <div className="flex items-center justify-between gap-3">
                        <span className="truncate font-medium text-gray-800">{row.name}</span>
                        <BatchStatusBadge row={row} />
                      </div>
                      {row.error && (
                        <p className="text-xs text-red-600" data-testid="batch-row-error">{row.error}</p>
                      )}
                      {row.errorDetails && row.errorDetails.length > 1 && (
                        <IssueList label={`Details (${row.errorDetails.length})`} items={row.errorDetails} tone="error" />
                      )}
                      {row.warnings && (
                        <IssueList
                          label={`Warnings (${row.warnings.length})`}
                          items={row.warnings}
                          tone="warning"
                          testId="batch-row-warnings"
                        />
                      )}
                    </li>
                  ))}
                </ul>
              )}

              {batchDone && (
                <div
                  className={`rounded p-3 text-sm ${batchFailed > 0 ? "bg-yellow-50 text-yellow-700" : "bg-green-50 text-green-700"}`}
                  role="status"
                >
                  {batchSucceeded} of {batchRows.length} stub{batchRows.length === 1 ? "" : "s"} created successfully
                  {batchFailed > 0 && `, ${batchFailed} failed`}.
                </div>
              )}

              <div className="flex justify-end gap-3 pt-2">
                {batchDone ? (
                  <Button type="button" onClick={() => void navigate(`/projects/${projectId}`)}>
                    Go to project
                  </Button>
                ) : (
                  <>
                    <Link to={`/projects/${projectId}`}>
                      <Button type="button" variant="ghost" disabled={batchRunning}>Cancel</Button>
                    </Link>
                    <Button type="submit" loading={batchRunning} disabled={batchFiles.length === 0}>
                      {isXlsxMode
                        ? "Upload & Generate"
                        : groupMode === "combined"
                          ? "Upload & Generate (1 stub)"
                          : `Upload & Generate ${batchUploadCount > 0 ? `(${batchUploadCount})` : ""}`}
                    </Button>
                  </>
                )}
              </div>
            </div>
          </Card>
        </form>
      )}
    </div>
  );
}

function BatchStatusBadge({ row }: { row: BatchRow }) {
  const labels: Record<BatchStatus, string> = {
    pending: "Pending",
    uploading: "Uploading…",
    generating: "Generating…",
    done: "Done",
    error: "Failed",
  };
  const colors: Record<BatchStatus, string> = {
    pending: "text-gray-400",
    uploading: "text-blue-600",
    generating: "text-blue-600",
    done: "text-green-600",
    error: "text-red-600",
  };
  return (
    <span className={`shrink-0 text-xs font-medium ${colors[row.status]}`} title={row.error}>
      {labels[row.status]}
    </span>
  );
}
