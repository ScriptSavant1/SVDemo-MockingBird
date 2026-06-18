import { Navigate, Outlet } from "react-router-dom";
import { useAuthStore } from "@/store/auth";
import { Layout } from "@/components/Layout";

export function ProtectedRoute() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return (
    <Layout>
      <Outlet />
    </Layout>
  );
}
