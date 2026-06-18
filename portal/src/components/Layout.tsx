import { Link, useNavigate } from "react-router-dom";
import { useAuthStore } from "@/store/auth";
import { logout as apiLogout } from "@/api/auth";
import { Button } from "@/components/ui/Button";

interface LayoutProps {
  children: React.ReactNode;
}

export function Layout({ children }: LayoutProps) {
  const { user, logout } = useAuthStore();
  const navigate = useNavigate();

  async function handleLogout() {
    try {
      await apiLogout();
    } finally {
      logout();
      void navigate("/login");
    }
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="border-b border-gray-200 bg-[#003875]">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-3">
          <Link to="/" className="flex items-center gap-2 text-white">
            <span className="text-xl font-bold tracking-tight">Mockingbird</span>
            <span className="hidden text-xs font-normal text-blue-200 sm:block">
              Service Virtualisation Platform
            </span>
          </Link>
          <div className="flex items-center gap-4">
            {user && (
              <span className="text-sm text-blue-200">
                {user.username}{" "}
                <span className="rounded bg-blue-900 px-1.5 py-0.5 text-xs">{user.role}</span>
              </span>
            )}
            <Button variant="ghost" size="sm" onClick={() => void handleLogout()}
              className="text-white hover:bg-blue-900">
              Sign out
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-6 py-8">{children}</main>

      <footer className="border-t border-gray-200 py-4 text-center text-xs text-gray-400">
        Mockingbird SV Platform
      </footer>
    </div>
  );
}
