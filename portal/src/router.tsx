import { createBrowserRouter } from "react-router-dom";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { LoginPage } from "@/pages/LoginPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { ProjectPage } from "@/pages/ProjectPage";
import { DeploymentPage } from "@/pages/DeploymentPage";
import { UploadPage } from "@/pages/UploadPage";
import { JobStatusPage } from "@/pages/JobStatusPage";

export const router = createBrowserRouter([
  {
    path: "/login",
    element: <LoginPage />,
  },
  {
    element: <ProtectedRoute />,
    children: [
      { path: "/", element: <DashboardPage /> },
      { path: "/projects/:projectId", element: <ProjectPage /> },
      { path: "/projects/:projectId/upload", element: <UploadPage /> },
      { path: "/projects/:projectId/stubs/:stubId", element: <DeploymentPage /> },
      { path: "/jobs/:jobId", element: <JobStatusPage /> },
    ],
  },
]);
