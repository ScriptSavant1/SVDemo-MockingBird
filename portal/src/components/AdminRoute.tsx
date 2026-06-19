import { Navigate, Outlet } from "react-router-dom";
import { useAuthStore } from "@/store/auth";

export function AdminRoute() {
  const role = useAuthStore((s) => s.user?.role);
  if (role !== "ADMIN") return <Navigate to="/" replace />;
  return <Outlet />;
}
