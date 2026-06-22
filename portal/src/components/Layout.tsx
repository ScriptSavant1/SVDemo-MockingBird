import { Link, useNavigate, useLocation } from "react-router-dom";
import { useAuthStore } from "@/store/auth";
import { logout as apiLogout } from "@/api/auth";
import { Button } from "@/components/ui/Button";

interface LayoutProps {
  children: React.ReactNode;
}

export function Layout({ children }: LayoutProps) {
  const { user, logout } = useAuthStore();
  const navigate = useNavigate();
  const location = useLocation();
  const isAdmin = user?.role === "ADMIN";

  async function handleLogout() {
    try {
      await apiLogout();
    } finally {
      logout();
      void navigate("/login");
    }
  }

  function navLinkClass(path: string) {
    const active = location.pathname.startsWith(path);
    return `text-sm transition-colors ${active ? "text-white font-semibold" : "text-blue-200 hover:text-white"}`;
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="border-b border-blue-900 bg-[#003875]">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-3">
          <div className="flex items-center gap-6">
            <Link to="/" className="flex items-center gap-2 text-white">
              <span className="text-xl font-bold tracking-tight">Mockingbird</span>
              <span className="hidden text-xs font-normal text-blue-200 sm:block">
                Service Virtualisation
              </span>
            </Link>

            <nav className="flex items-center gap-5">
              <Link to="/" className={navLinkClass("/projects")}>Projects</Link>

              {/* Reports — Phase 5, coming soon */}
              <span
                title="Reports — available in Phase 5 (Metrics & Reporting)"
                className="cursor-not-allowed text-sm text-blue-400 select-none"
              >
                Reports
                <span className="ml-1 rounded bg-blue-900 px-1 py-0.5 text-[10px] text-blue-300">
                  Phase 5
                </span>
              </span>

              {isAdmin && (
                <Link
                  to="/admin"
                  className={navLinkClass("/admin")}
                  data-testid="admin-nav-link"
                >
                  Admin
                </Link>
              )}
            </nav>
          </div>

          <div className="flex items-center gap-4">
            {user && (
              <span data-testid="user-info" className="text-sm text-blue-200">
                {user.username}{" "}
                <span className="rounded bg-blue-900 px-1.5 py-0.5 text-xs">{user.role}</span>
              </span>
            )}
            <Button
              variant="ghost"
              size="sm"
              onClick={() => void handleLogout()}
              className="text-white hover:bg-blue-900"
            >
              Sign out
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-6 py-8">{children}</main>

      <footer className="border-t border-gray-200 py-4 text-center text-xs text-gray-400">
        Mockingbird SV Platform · Phase 1
      </footer>
    </div>
  );
}
