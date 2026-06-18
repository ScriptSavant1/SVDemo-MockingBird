import { useState, type FormEvent } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { uploadSpec } from "@/api/ingestion";
import { projectsApi } from "@/api/projects";
import { ApiError } from "@/api/client";
import { UploadZone } from "@/components/UploadZone";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";

export function UploadPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();

  const [stubName, setStubName] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);
  const [warnings, setWarnings] = useState<string[]>([]);

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

  return (
    <div className="max-w-2xl">
      <div className="mb-6">
        <Link to={`/projects/${projectId}`} className="text-sm text-[#00A9E0] hover:underline">
          ← Back to project
        </Link>
        <h1 className="mt-2 text-2xl font-bold text-gray-900">Upload Spec File</h1>
        <p className="mt-1 text-sm text-gray-500">
          Upload a .txt (raw HTTP pairs) or .json (Postman v2.1) spec to generate stubs.
        </p>
      </div>

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
    </div>
  );
}
