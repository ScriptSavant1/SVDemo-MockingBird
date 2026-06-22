import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 3000,
    proxy: {
      "/api/v1/auth": {
        target: "http://localhost:3001",
        changeOrigin: true,
        // No rewrite — auth-service routes live at /api/v1/auth/* (versioned)
      },
      // ai-service routes — must precede generic /api/v1
      "/api/v1/ai": {
        target: "http://localhost:8004",
        changeOrigin: true,
      },
      // metrics-service routes — must precede generic /api/v1
      "/api/v1/metrics": {
        target: "http://localhost:8005",
        changeOrigin: true,
      },
      // ingestion-service routes — must precede generic /api/v1
      "^/api/v1/projects/[^/]+/stubs/upload$": {
        target: "http://localhost:8003",
        changeOrigin: true,
      },
      "^/api/v1/projects/[^/]+/stubs/[^/]+/source$": {
        target: "http://localhost:8003",
        changeOrigin: true,
      },
      "^/api/v1/projects/[^/]+/stubs/[^/]+/wiremock\\.zip$": {
        target: "http://localhost:8003",
        changeOrigin: true,
      },
      "/api/v1": {
        target: "http://localhost:8001",
        changeOrigin: true,
      },
      "/ws": {
        target: "ws://localhost:8005",
        ws: true,
        changeOrigin: true,
      },
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    include: ["tests/**/*.test.{ts,tsx}"],
  },
});
