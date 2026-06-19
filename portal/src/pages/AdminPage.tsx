import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { adminApi, type CreateUserBody, type PatchUserBody } from "@/api/admin";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Tabs } from "@/components/ui/Tabs";
import { Modal } from "@/components/ui/Modal";
import { formatDate } from "@/utils/formatters";
import { ApiError } from "@/api/client";
import type { User, AuditLogEntry } from "@/api/types";

const TABS = [
  { id: "users", label: "Users" },
  { id: "audit", label: "Audit Log" },
];

const ROLES = ["ADMIN", "SV_TEAM", "PROJECT_OWNER", "VIEWER"] as const;

const EMPTY_USER: CreateUserBody = {
  username: "",
  email: "",
  password: "",
  role: "VIEWER",
};

export function AdminPage() {
  const qc = useQueryClient();
  const [activeTab, setActiveTab] = useState("users");

  // Create user modal state
  const [showCreate, setShowCreate] = useState(false);
  const [createForm, setCreateForm] = useState<CreateUserBody>(EMPTY_USER);
  const [createError, setCreateError] = useState<string | null>(null);

  // Reset password modal state
  const [resetUserId, setResetUserId] = useState<string | null>(null);
  const [resetUsername, setResetUsername] = useState<string>("");
  const [newPassword, setNewPassword] = useState("");
  const [resetError, setResetError] = useState<string | null>(null);

  const { data: usersPage } = useQuery({
    queryKey: ["admin-users"],
    queryFn: () => adminApi.listUsers(),
    enabled: activeTab === "users",
  });

  const { data: auditPage } = useQuery({
    queryKey: ["admin-audit"],
    queryFn: () => adminApi.listAudit(),
    enabled: activeTab === "audit",
  });

  const createMutation = useMutation({
    mutationFn: () => adminApi.createUser(createForm),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["admin-users"] });
      setShowCreate(false);
      setCreateForm(EMPTY_USER);
      setCreateError(null);
    },
    onError: (err) => {
      setCreateError(err instanceof ApiError ? err.detail : "Failed to create user");
    },
  });

  const patchMutation = useMutation({
    mutationFn: ({ id, body }: { id: string; body: PatchUserBody }) =>
      adminApi.patchUser(id, body),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["admin-users"] }),
  });

  const resetMutation = useMutation({
    mutationFn: () => adminApi.resetPassword(resetUserId!, newPassword),
    onSuccess: () => {
      setResetUserId(null);
      setNewPassword("");
      setResetError(null);
    },
    onError: (err) => {
      setResetError(err instanceof ApiError ? err.detail : "Failed to reset password");
    },
  });

  function openReset(user: User) {
    setResetUserId(user.id);
    setResetUsername(user.username);
    setNewPassword("");
    setResetError(null);
  }

  function setCreateField(k: keyof CreateUserBody, v: string) {
    setCreateForm((prev) => ({ ...prev, [k]: v }));
    setCreateError(null);
  }

  const users: User[] = usersPage?.items ?? [];
  const auditEntries: AuditLogEntry[] = auditPage?.items ?? [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Admin</h1>
      </div>

      <Tabs tabs={TABS} active={activeTab} onChange={setActiveTab} />

      {/* Users tab */}
      {activeTab === "users" && (
        <Card>
          <CardHeader>
            <CardTitle>Users ({usersPage?.total ?? 0})</CardTitle>
            <Button
              size="sm"
              data-testid="new-user-button"
              onClick={() => {
                setCreateForm(EMPTY_USER);
                setCreateError(null);
                setShowCreate(true);
              }}
            >
              New User
            </Button>
          </CardHeader>

          <div className="px-6 pb-6">
            <table className="w-full text-sm" data-testid="users-table">
              <thead>
                <tr className="border-b border-gray-200 text-left text-xs font-medium uppercase text-gray-500">
                  <th className="pb-2 pr-4">Username</th>
                  <th className="pb-2 pr-4">Email</th>
                  <th className="pb-2 pr-4">Role</th>
                  <th className="pb-2 pr-4">Active</th>
                  <th className="pb-2 pr-4">Joined</th>
                  <th className="pb-2" />
                </tr>
              </thead>
              <tbody>
                {users.map((user) => (
                  <tr key={user.id} className="border-b border-gray-100 last:border-0">
                    <td className="py-3 pr-4 font-medium text-gray-900">{user.username}</td>
                    <td className="py-3 pr-4 text-gray-500">{user.email}</td>
                    <td className="py-3 pr-4">
                      <select
                        value={user.role}
                        data-testid={`role-select-${user.id}`}
                        onChange={(e) =>
                          patchMutation.mutate({ id: user.id, body: { role: e.target.value } })
                        }
                        className="rounded border border-gray-200 px-2 py-1 text-xs"
                      >
                        {ROLES.map((r) => (
                          <option key={r} value={r}>
                            {r}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="py-3 pr-4">
                      <button
                        data-testid={`toggle-active-${user.id}`}
                        onClick={() =>
                          patchMutation.mutate({
                            id: user.id,
                            body: { is_active: !user.is_active },
                          })
                        }
                        className={[
                          "rounded-full px-2 py-0.5 text-xs font-medium",
                          user.is_active
                            ? "bg-green-100 text-green-700"
                            : "bg-gray-100 text-gray-500",
                        ].join(" ")}
                      >
                        {user.is_active ? "Active" : "Suspended"}
                      </button>
                    </td>
                    <td className="py-3 pr-4 text-gray-400">{formatDate(user.created_at)}</td>
                    <td className="py-3">
                      <Button
                        size="sm"
                        variant="secondary"
                        data-testid={`reset-password-${user.id}`}
                        onClick={() => openReset(user)}
                      >
                        Reset password
                      </Button>
                    </td>
                  </tr>
                ))}
                {users.length === 0 && (
                  <tr>
                    <td colSpan={6} className="py-8 text-center text-gray-400">
                      No users found.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Audit log tab */}
      {activeTab === "audit" && (
        <Card>
          <CardHeader>
            <CardTitle>Audit Log ({auditPage?.total ?? 0} entries)</CardTitle>
          </CardHeader>

          <div className="px-6 pb-6">
            <table className="w-full text-sm" data-testid="audit-table">
              <thead>
                <tr className="border-b border-gray-200 text-left text-xs font-medium uppercase text-gray-500">
                  <th className="pb-2 pr-4">When</th>
                  <th className="pb-2 pr-4">Action</th>
                  <th className="pb-2 pr-4">User</th>
                  <th className="pb-2">Detail</th>
                </tr>
              </thead>
              <tbody>
                {auditEntries.map((entry) => (
                  <tr key={entry.id} className="border-b border-gray-100 last:border-0">
                    <td className="py-3 pr-4 text-gray-400 tabular-nums">
                      {formatDate(entry.created_at)}
                    </td>
                    <td className="py-3 pr-4 font-mono text-xs text-gray-700">
                      {entry.action}
                    </td>
                    <td className="py-3 pr-4 text-gray-500">
                      {entry.username ?? entry.user_id?.slice(0, 8) ?? "—"}
                    </td>
                    <td className="max-w-xs py-3 text-xs text-gray-400">
                      {entry.detail
                        ? Object.entries(entry.detail)
                            .map(([k, v]) => `${k}: ${String(v)}`)
                            .join(", ")
                        : "—"}
                    </td>
                  </tr>
                ))}
                {auditEntries.length === 0 && (
                  <tr>
                    <td colSpan={4} className="py-8 text-center text-gray-400">
                      No audit entries yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Create user modal */}
      <Modal
        open={showCreate}
        title="Create User"
        onClose={() => setShowCreate(false)}
      >
        <form
          data-testid="create-user-form"
          onSubmit={(e) => {
            e.preventDefault();
            createMutation.mutate();
          }}
          className="space-y-4"
        >
          {createError && (
            <div
              data-testid="create-user-error"
              className="rounded bg-red-50 px-3 py-2 text-sm text-red-700"
            >
              {createError}
            </div>
          )}

          {(
            [
              { id: "username", label: "Username", type: "text", placeholder: "jsmith" },
              { id: "email", label: "Email", type: "email", placeholder: "j.smith@company.com" },
              { id: "password", label: "Password", type: "password", placeholder: "min 8 characters" },
            ] as const
          ).map(({ id, label, type, placeholder }) => (
            <div key={id}>
              <label className="block text-sm font-medium text-gray-700">{label}</label>
              <input
                data-testid={`new-user-${id}`}
                type={type}
                value={createForm[id]}
                onChange={(e) => setCreateField(id, e.target.value)}
                placeholder={placeholder}
                required
                className="mt-1 block w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-[#00A9E0] focus:outline-none"
              />
            </div>
          ))}

          <div>
            <label className="block text-sm font-medium text-gray-700">Role</label>
            <select
              data-testid="new-user-role"
              value={createForm.role}
              onChange={(e) => setCreateField("role", e.target.value)}
              className="mt-1 block w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-[#00A9E0] focus:outline-none"
            >
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
          </div>

          <div className="flex justify-end gap-3 pt-2">
            <Button type="button" variant="secondary" onClick={() => setShowCreate(false)}>
              Cancel
            </Button>
            <Button
              type="submit"
              loading={createMutation.isPending}
              data-testid="create-user-submit"
            >
              Create
            </Button>
          </div>
        </form>
      </Modal>

      {/* Reset password modal */}
      <Modal
        open={!!resetUserId}
        title={`Reset password — ${resetUsername}`}
        onClose={() => setResetUserId(null)}
      >
        <form
          data-testid="reset-password-form"
          onSubmit={(e) => {
            e.preventDefault();
            resetMutation.mutate();
          }}
          className="space-y-4"
        >
          {resetError && (
            <div
              data-testid="reset-error"
              className="rounded bg-red-50 px-3 py-2 text-sm text-red-700"
            >
              {resetError}
            </div>
          )}

          <div>
            <label className="block text-sm font-medium text-gray-700">New password</label>
            <input
              data-testid="new-password-input"
              type="password"
              value={newPassword}
              onChange={(e) => {
                setNewPassword(e.target.value);
                setResetError(null);
              }}
              placeholder="min 8 characters"
              required
              minLength={8}
              className="mt-1 block w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-[#00A9E0] focus:outline-none"
            />
          </div>

          <div className="flex justify-end gap-3 pt-2">
            <Button type="button" variant="secondary" onClick={() => setResetUserId(null)}>
              Cancel
            </Button>
            <Button
              type="submit"
              loading={resetMutation.isPending}
              data-testid="reset-password-submit"
            >
              Reset
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
