import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { login as apiLogin } from "@/api/auth";
import { ApiError } from "@/api/client";
import { useAuthStore } from "@/store/auth";
import { Button } from "@/components/ui/Button";

export function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const { login } = useAuthStore();
  const navigate = useNavigate();

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const res = await apiLogin(username, password);
      login(res.access_token, { username: res.username, role: res.role });
      void navigate("/");
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50">
      <div className="w-full max-w-sm space-y-8">
        <div className="text-center">
          <h1 className="text-3xl font-bold text-[#003875]">Mockingbird</h1>
          <p className="mt-2 text-sm text-gray-500">Service Virtualisation Platform</p>
        </div>

        <form
          onSubmit={(e) => void handleSubmit(e)}
          className="rounded-lg border border-gray-200 bg-white p-8 shadow-sm"
          aria-label="Login form"
        >
          <div className="space-y-5">
            <div>
              <label htmlFor="username" className="block text-sm font-medium text-gray-700">
                Username
              </label>
              <input
                id="username"
                type="text"
                autoComplete="username"
                required
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="mt-1 block w-full rounded border border-gray-300 px-3 py-2 text-sm
                           focus:border-[#003875] focus:outline-none focus:ring-1 focus:ring-[#003875]"
              />
            </div>

            <div>
              <label htmlFor="password" className="block text-sm font-medium text-gray-700">
                Password
              </label>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="mt-1 block w-full rounded border border-gray-300 px-3 py-2 text-sm
                           focus:border-[#003875] focus:outline-none focus:ring-1 focus:ring-[#003875]"
              />
            </div>

            {error && (
              <p role="alert" className="rounded bg-red-50 px-3 py-2 text-sm text-red-700">
                {error}
              </p>
            )}

            <Button type="submit" className="w-full" loading={loading}>
              Sign in
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
