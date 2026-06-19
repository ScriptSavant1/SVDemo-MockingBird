import { createBrowserRouter } from "react-router-dom";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { AdminRoute } from "@/components/AdminRoute";
import { LoginPage } from "@/pages/LoginPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { ProjectPage } from "@/pages/ProjectPage";
import { DeploymentPage } from "@/pages/DeploymentPage";
import { UploadPage } from "@/pages/UploadPage";
import { JobStatusPage } from "@/pages/JobStatusPage";
import { AiGeneratePage } from "@/pages/AiGeneratePage";
import { CreateProjectPage } from "@/pages/CreateProjectPage";
import { AdminPage } from "@/pages/AdminPage";

export const router = createBrowserRouter([
  {
    path: "/login",
    element: <LoginPage />,
  },
  {
    element: <ProtectedRoute />,
    children: [
      { path: "/", element: <DashboardPage /> },
      { path: "/projects/new", element: <CreateProjectPage /> },
      { path: "/projects/:projectId", element: <ProjectPage /> },
      { path: "/projects/:projectId/upload", element: <UploadPage /> },
      { path: "/projects/:projectId/ai-generate", element: <AiGeneratePage /> },
      { path: "/projects/:projectId/stubs/:stubId", element: <DeploymentPage /> },
      { path: "/jobs/:jobId", element: <JobStatusPage /> },
      {
        element: <AdminRoute />,
        children: [{ path: "/admin", element: <AdminPage /> }],
      },
    ],
  },
]);
