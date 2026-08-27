import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { uploadSpec } from "@/api/ingestion";
import { projectsApi } from "@/api/projects";
import { ApiError } from "@/api/client";
import { UploadZone } from "@/components/UploadZone";
import { BatchUploadZone, type BatchFile } from "@/components/BatchUploadZone";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { pairHttpCaptureFiles, mergeHttpCaptureFiles } from "@/lib/httpCapturePairing";
import { zipHttpCaptureFiles } from "@/lib/zipHttpCaptureFiles";

type BatchStatus = "pending" | "uploading" | "generating" | "done" | "error";
type BatchGroupMode = "combined" | "separate";

interface BatchRow {
  key: string;
  name: string;
  status: BatchStatus;
  error?: string;
}

function stripExtension(filename: string): string {
  return filename.replace(/\.[^.]+$/, "");
}

export function UploadPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();

  const [batchMode, setBatchMode] = useState(false);

  // Single-file mode
  const [stubName, setStubName] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
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

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!file || !projectId) return;
    setErrors([]);
    setWarnings([]);
    setUploading(true);

    try {
      const result = await uploadSpec(projectId, stubName || file.name, file);

      if (!result.valid || !result.stub_id) {
        setErrors(result.errors.length > 0 ? result.errors : ["File failed validation."]);
        setWarnings(result.warnings);
        return;
      }

      if (result.warnings.length > 0) setWarnings(result.warnings);

      const { job_id } = await projectsApi.generate(projectId, result.stub_id);
      void navigate(`/jobs/${job_id}?projectId=${projectId}`);
    } catch (err) {
      setErrors([err instanceof ApiError ? err.detail : "Upload failed. Please try again."]);
    } finally {
      setUploading(false);
    }
  }

  async function handleBatchSubmit(e: FormEvent) {
    e.preventDefault();
    if (batchFiles.length === 0 || !projectId) return;

    setBatchRunning(true);

    let items: { key: string; name: string; file: File }[];

    if (groupMode === "combined") {
      // One stub for the whole batch: zip every raw file as-is and let the
      // backend's existing ZIP-upload pairing (parser-worker's
      // _detect_and_parse_zip / _pair_files) match request/response halves
      // and fold every endpoint into one Stub record with multiple WireMock
      // mappings — the same mechanism a manually-zipped upload already uses.
      const name = combinedStubName.trim() || "Combined Spec";
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
        const result = await uploadSpec(projectId, stubNameForFile, f);
        if (!result.valid || !result.stub_id) {
          const msg = result.errors[0] ?? "File failed validation.";
          setBatchRows((rows) =>
            rows.map((r) => (r.key === key ? { ...r, status: "error", error: msg } : r)),
          );
          continue;
        }

        setBatchRows((rows) =>
          rows.map((r) => (r.key === key ? { ...r, status: "generating" } : r)),
        );
        await projectsApi.generate(projectId, result.stub_id);
        setBatchRows((rows) =>
          rows.map((r) => (r.key === key ? { ...r, status: "done" } : r)),
        );
      } catch (err) {
        const msg = err instanceof ApiError ? err.detail : "Upload failed.";
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
            ? "Upload several .txt / .json files at once — combine them into one stub, or keep each as its own."
            : "Upload a .txt (raw HTTP pairs) or .json (Postman v2.1) spec to generate stubs."}
        </p>
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

              {errors.length > 0 && (
                <div className="rounded bg-red-50 p-3" role="alert">
                  <p className="mb-1 text-sm font-medium text-red-700">Validation failed</p>
                  <ul className="list-inside list-disc space-y-0.5 text-xs text-red-600">
                    {errors.map((e, i) => <li key={i}>{e}</li>)}
                  </ul>
                </div>
              )}

              {warnings.length > 0 && (
                <div className="rounded bg-yellow-50 p-3">
                  <p className="mb-1 text-sm font-medium text-yellow-700">Warnings</p>
                  <ul className="list-inside list-disc space-y-0.5 text-xs text-yellow-600">
                    {warnings.map((w, i) => <li key={i}>{w}</li>)}
                  </ul>
                </div>
              )}

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

              {groupMode === "combined" && batchFiles.length > 0 && (
                <div>
                  <label htmlFor="combined-stub-name" className="block text-sm font-medium text-gray-700">
                    Stub name{" "}
                    <span className="font-normal text-gray-400">(optional — defaults to "Combined Spec")</span>
                  </label>
                  <input
                    id="combined-stub-name"
                    type="text"
                    placeholder="e.g. Payments Client API"
                    value={combinedStubName}
                    onChange={(e) => setCombinedStubName(e.target.value)}
                    disabled={batchRunning}
                    className="mt-1 block w-full rounded border border-gray-300 px-3 py-2 text-sm
                               focus:border-[#003875] focus:outline-none focus:ring-1 focus:ring-[#003875]
                               disabled:bg-gray-50"
                  />
                </div>
              )}

              {groupMode === "separate" && batchRows.length === 0 && batchPairing.pairs.length > 0 && (
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
                    <li key={row.key} className="flex items-center justify-between gap-3 px-3 py-2 text-sm">
                      <span className="truncate font-medium text-gray-800">{row.name}</span>
                      <BatchStatusBadge row={row} />
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
                      {groupMode === "combined"
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
