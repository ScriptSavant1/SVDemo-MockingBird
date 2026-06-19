import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { projectsApi } from "@/api/projects";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { ApiError } from "@/api/client";

const ENVIRONMENTS = ["TEST", "STAGING", "PROD"] as const;

interface FormState {
  name: string;
  team: string;
  environment: string;
  expected_tps: string;
  description: string;
}

const EMPTY: FormState = {
  name: "",
  team: "",
  environment: "TEST",
  expected_tps: "1000",
  description: "",
};

export function CreateProjectPage() {
  const navigate = useNavigate();
  const [form, setForm] = useState<FormState>(EMPTY);
  const [errors, setErrors] = useState<Partial<FormState>>({});

  const mutation = useMutation({
    mutationFn: () =>
      projectsApi.create({
        name: form.name.trim(),
        team: form.team.trim(),
        environment: form.environment,
        expected_tps: parseInt(form.expected_tps, 10),
        description: form.description.trim() || undefined,
      }),
    onSuccess: (project) => void navigate(`/projects/${project.id}`),
  });

  function set(field: keyof FormState, value: string) {
    setForm((prev) => ({ ...prev, [field]: value }));
    setErrors((prev) => ({ ...prev, [field]: undefined }));
  }

  function validate(): boolean {
    const errs: Partial<FormState> = {};
    if (!form.name.trim()) errs.name = "Name is required";
    if (!form.team.trim()) errs.team = "Team is required";
    const tps = parseInt(form.expected_tps, 10);
    if (isNaN(tps) || tps < 1 || tps > 100000) errs.expected_tps = "Must be 1 – 100,000";
    setErrors(errs);
    return Object.keys(errs).length === 0;
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!validate()) return;
    mutation.mutate();
  }

  const apiError =
    mutation.error instanceof ApiError ? mutation.error.detail : null;

  return (
    <div>
      <div className="mb-6">
        <Link to="/" className="text-sm text-[#00A9E0] hover:underline">
          ← All projects
        </Link>
        <h1 className="mt-2 text-2xl font-bold text-gray-900">New Project</h1>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Project Details</CardTitle>
        </CardHeader>

        <form onSubmit={handleSubmit} noValidate className="space-y-5 px-6 pb-6">
          {apiError && (
            <div
              data-testid="create-error"
              className="rounded bg-red-50 px-4 py-2 text-sm text-red-700"
            >
              {apiError}
            </div>
          )}

          <div>
            <label className="block text-sm font-medium text-gray-700">
              Project name <span className="text-red-500">*</span>
            </label>
            <input
              data-testid="name-input"
              type="text"
              value={form.name}
              onChange={(e) => set("name", e.target.value)}
              placeholder="e.g. Payments API Stub"
              className="mt-1 block w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-[#00A9E0] focus:outline-none focus:ring-1 focus:ring-[#00A9E0]"
            />
            {errors.name && (
              <p className="mt-1 text-xs text-red-600">{errors.name}</p>
            )}
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700">
              Team <span className="text-red-500">*</span>
            </label>
            <input
              data-testid="team-input"
              type="text"
              value={form.team}
              onChange={(e) => set("team", e.target.value)}
              placeholder="e.g. Core Banking"
              className="mt-1 block w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-[#00A9E0] focus:outline-none focus:ring-1 focus:ring-[#00A9E0]"
            />
            {errors.team && (
              <p className="mt-1 text-xs text-red-600">{errors.team}</p>
            )}
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="block text-sm font-medium text-gray-700">
                Environment
              </label>
              <select
                data-testid="environment-select"
                value={form.environment}
                onChange={(e) => set("environment", e.target.value)}
                className="mt-1 block w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-[#00A9E0] focus:outline-none focus:ring-1 focus:ring-[#00A9E0]"
              >
                {ENVIRONMENTS.map((env) => (
                  <option key={env} value={env}>
                    {env}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700">
                Expected TPS
              </label>
              <input
                data-testid="tps-input"
                type="number"
                min={1}
                max={100000}
                value={form.expected_tps}
                onChange={(e) => set("expected_tps", e.target.value)}
                className="mt-1 block w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-[#00A9E0] focus:outline-none focus:ring-1 focus:ring-[#00A9E0]"
              />
              {errors.expected_tps && (
                <p className="mt-1 text-xs text-red-600">{errors.expected_tps}</p>
              )}
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700">
              Description
            </label>
            <textarea
              data-testid="description-textarea"
              value={form.description}
              onChange={(e) => set("description", e.target.value)}
              rows={3}
              placeholder="Optional — what does this stub replace?"
              className="mt-1 block w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-[#00A9E0] focus:outline-none focus:ring-1 focus:ring-[#00A9E0]"
            />
          </div>

          <div className="flex justify-end gap-3 pt-2">
            <Link to="/">
              <Button type="button" variant="secondary">
                Cancel
              </Button>
            </Link>
            <Button
              type="submit"
              loading={mutation.isPending}
              data-testid="create-submit-button"
            >
              Create Project
            </Button>
          </div>
        </form>
      </Card>
    </div>
  );
}
