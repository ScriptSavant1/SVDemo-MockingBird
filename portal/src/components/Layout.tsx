import { Link, useNavigate, useLocation } from "react-router-dom";
import { LayoutGrid, FileBarChart, ShieldCheck, LogOut } from "lucide-react";
import { useAuthStore } from "@/store/auth";
import { logout as apiLogout } from "@/api/auth";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { cn } from "@/lib/utils";

interface LayoutProps {
  children: React.ReactNode;
}

const NAV_ITEMS = [
  { to: "/", label: "Projects", icon: LayoutGrid, testId: undefined as string | undefined },
  { to: "/reports", label: "Reports", icon: FileBarChart, testId: "reports-nav-link" },
];

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

  function isActive(path: string) {
    return path === "/" ? location.pathname === "/" : location.pathname.startsWith(path);
  }

  return (
    <div className="min-h-screen bg-muted/40">
      <header className="border-b border-primary/20 bg-primary">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-3">
          <div className="flex items-center gap-8">
            <Link to="/" className="flex items-center gap-2 text-primary-foreground">
              <span className="text-xl font-bold tracking-tight">Mockingbird</span>
              <span className="hidden text-xs font-normal text-primary-foreground/70 sm:block">
                Service Virtualisation
              </span>
            </Link>

            <nav className="flex items-center gap-1">
              {NAV_ITEMS.map(({ to, label, icon: Icon, testId }) => (
                <Link
                  key={to}
                  to={to}
                  data-testid={testId}
                  className={cn(
                    "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
                    isActive(to)
                      ? "bg-primary-foreground/15 text-primary-foreground"
                      : "text-primary-foreground/70 hover:bg-primary-foreground/10 hover:text-primary-foreground",
                  )}
                >
                  <Icon size={15} />
                  {label}
                </Link>
              ))}

              {isAdmin && (
                <Link
                  to="/admin"
                  data-testid="admin-nav-link"
                  className={cn(
                    "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
                    isActive("/admin")
                      ? "bg-primary-foreground/15 text-primary-foreground"
                      : "text-primary-foreground/70 hover:bg-primary-foreground/10 hover:text-primary-foreground",
                  )}
                >
                  <ShieldCheck size={15} />
                  Admin
                </Link>
              )}
            </nav>
          </div>

          <div className="flex items-center gap-3">
            {user && (
              <span data-testid="user-info" className="flex items-center gap-2 text-sm text-primary-foreground/80">
                {user.username}
                <Badge variant="secondary" className="bg-primary-foreground/15 text-primary-foreground">
                  {user.role}
                </Badge>
              </span>
            )}
            <Button
              variant="ghost"
              size="sm"
              onClick={() => void handleLogout()}
              className="gap-1.5 text-primary-foreground hover:bg-primary-foreground/10"
            >
              <LogOut size={14} />
              Sign out
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-6 py-8">{children}</main>

      <footer className="border-t border-border py-4 text-center text-xs text-muted-foreground">
        Mockingbird SV Platform
      </footer>
    </div>
  );
}
