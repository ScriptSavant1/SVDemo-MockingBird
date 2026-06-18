import { useState } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { aiApi } from "@/api/ai";
import type { GenerateResponse } from "@/api/ai";
import { uploadSpec } from "@/api/ingestion";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { ApiError } from "@/api/client";

const MIN_DESCRIPTION_LENGTH = 10;
const MAX_DESCRIPTION_LENGTH = 2000;

export function AiGeneratePage() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();

  const [description, setDescription] = useState("");
  const [result, setResult] = useState<GenerateResponse | null>(null);
  const [stubName, setStubName] = useState("");
  const [apiError, setApiError] = useState<string | null>(null);

  const generateMutation = useMutation({
    mutationFn: () =>
      aiApi.generate({ description: description.trim(), project_id: projectId }),
    onSuccess: (data) => {
      setResult(data);
      setStubName(data.suggested_stub_name);
      setApiError(null);
    },
    onError: (err) => {
      if (err instanceof ApiError && err.status === 429) {
        setApiError("Rate limit reached — you can generate up to 10 specs per hour.");
      } else if (err instanceof ApiError) {
        setApiError(err.detail);
      } else {
        setApiError("Generation failed. Please try again.");
      }
    },
  });

  const createMutation = useMutation({
    mutationFn: async () => {
      if (!result || !projectId) throw new Error("No result to create stub from");
      const blob = new Blob([result.spec_content], { type: "application/json" });
      const file = new File([blob], `${stubName || result.suggested_stub_name}.postman_collection.json`, {
        type: "application/json",
      });
      return uploadSpec(projectId, stubName || result.suggested_stub_name, file);
    },
    onSuccess: () => {
      navigate(`/projects/${projectId}/upload?uploaded=ai`);
    },
    onError: (err) => {
      if (err instanceof ApiError) {
        setApiError(err.detail);
      } else {
        setApiError("Failed to create stubs. Please try again.");
      }
    },
  });

  const descriptionTooShort = description.trim().length < MIN_DESCRIPTION_LENGTH;
  const descriptionTooLong = description.trim().length > MAX_DESCRIPTION_LENGTH;
  const canGenerate = !descriptionTooShort && !descriptionTooLong && !generateMutation.isPending;
  const canCreate = !!result && !createMutation.isPending;

  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-6">
        <Link
          to={`/projects/${projectId}`}
          className="text-sm text-[#00A9E0] hover:underline"
        >
          ← Back to project
        </Link>
        <h1 className="mt-2 text-2xl font-bold text-gray-900">Generate Stubs with AI</h1>
        <p className="mt-1 text-sm text-gray-500">
          Describe your API in plain English. Claude will generate a Postman collection that
          Mockingbird can deploy as live stubs.
        </p>
      </div>

      <Card className="mb-6">
        <CardHeader>
          <CardTitle>Describe your API</CardTitle>
        </CardHeader>
        <div className="px-6 pb-6">
          <textarea
            data-testid="description-input"
            className="w-full rounded-md border border-gray-300 p-3 text-sm text-gray-900 placeholder-gray-400 focus:border-[#00A9E0] focus:outline-none focus:ring-1 focus:ring-[#00A9E0] disabled:bg-gray-50"
            rows={8}
            maxLength={MAX_DESCRIPTION_LENGTH}
            placeholder={
              "Example:\n" +
              "A payment processing REST API with three endpoints:\n" +
              "1. POST /payments — creates a payment, returns {id, status: 'created'}\n" +
              "2. GET /payments/{id} — returns payment details\n" +
              "3. POST /payments/{id}/refund — initiates a refund\n\n" +
              "Return 400 for invalid amounts, 404 if the payment is not found."
            }
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            disabled={generateMutation.isPending}
            aria-label="API description"
          />
          <div className="mt-1 flex items-center justify-between">
            <span
              className={`text-xs ${descriptionTooLong ? "text-red-500" : "text-gray-400"}`}
            >
              {description.trim().length}/{MAX_DESCRIPTION_LENGTH} characters
            </span>
            {descriptionTooShort && description.length > 0 && (
              <span className="text-xs text-red-500">
                Description must be at least {MIN_DESCRIPTION_LENGTH} characters
              </span>
            )}
          </div>

          {apiError && (
            <div
              data-testid="error-message"
              className="mt-3 rounded-md bg-red-50 p-3 text-sm text-red-700"
            >
              {apiError}
            </div>
          )}

          <div className="mt-4 flex justify-end">
            <Button
              data-testid="generate-button"
              onClick={() => generateMutation.mutate()}
              disabled={!canGenerate}
              loading={generateMutation.isPending}
            >
              {generateMutation.isPending ? "Generating…" : "Generate Spec"}
            </Button>
          </div>
        </div>
      </Card>

      {result && (
        <Card data-testid="spec-preview">
          <CardHeader>
            <CardTitle>Generated Spec</CardTitle>
          </CardHeader>
          <div className="px-6 pb-6">
            <dl className="mb-4 grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
              <div>
                <dt className="font-medium text-gray-500">Intent detected</dt>
                <dd className="mt-0.5 text-gray-900">{result.detected_intent}</dd>
              </div>
              <div>
                <dt className="font-medium text-gray-500">Estimated stubs</dt>
                <dd className="mt-0.5 text-gray-900">{result.estimated_stub_count}</dd>
              </div>
              <div>
                <dt className="font-medium text-gray-500">Model used</dt>
                <dd className="mt-0.5 font-mono text-gray-900">{result.model_used}</dd>
              </div>
              <div>
                <dt className="font-medium text-gray-500">Tokens used</dt>
                <dd className="mt-0.5 text-gray-900">
                  {result.input_tokens} in / {result.output_tokens} out
                </dd>
              </div>
            </dl>

            <div className="mb-4">
              <label className="mb-1 block text-sm font-medium text-gray-700">
                Stub name
              </label>
              <input
                data-testid="stub-name-input"
                type="text"
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-[#00A9E0] focus:outline-none focus:ring-1 focus:ring-[#00A9E0]"
                value={stubName}
                onChange={(e) => setStubName(e.target.value)}
              />
            </div>

            <details className="mb-4">
              <summary className="cursor-pointer text-sm font-medium text-[#00A9E0] hover:underline">
                View raw Postman collection JSON
              </summary>
              <pre
                data-testid="spec-json"
                className="mt-2 max-h-64 overflow-auto rounded-md bg-gray-50 p-3 text-xs text-gray-700"
              >
                {JSON.stringify(JSON.parse(result.spec_content), null, 2)}
              </pre>
            </details>

            <div className="flex justify-end gap-3">
              <Button
                variant="secondary"
                onClick={() => {
                  setResult(null);
                  setApiError(null);
                }}
              >
                Regenerate
              </Button>
              <Button
                data-testid="create-stubs-button"
                onClick={() => createMutation.mutate()}
                disabled={!canCreate}
                loading={createMutation.isPending}
              >
                {createMutation.isPending ? "Creating…" : "Create Stubs"}
              </Button>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}
