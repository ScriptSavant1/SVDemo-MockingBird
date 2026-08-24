/**
 * Entry point — starts the HTTP server.
 * Not imported by tests; tests use app.ts directly.
 */
import path from "node:path";
import dotenv from "dotenv";
import { buildApp } from "./app.js";

// Load services/auth-service/.env.local so `npm run dev` works standalone —
// previously this service only got JWT_SECRET etc. when launched through
// scripts/start-services.ps1, which injects it manually; running `npm run
// dev` directly in this folder crashed with "JWT_SECRET environment
// variable is required". dotenv never overrides a var that's already set
// (e.g. real ECS/Vault-injected env vars in production), and silently no-ops
// if .env.local doesn't exist, so this is safe in every environment.
// __dirname is available directly — this compiles to CommonJS (see tsconfig).
dotenv.config({ path: path.resolve(__dirname, "../.env.local") });

const HOST = process.env["HOST"] ?? "0.0.0.0";
const PORT = parseInt(process.env["PORT"] ?? "3001", 10);

async function start(): Promise<void> {
  const app = await buildApp({ logger: true });
  try {
    await app.listen({ host: HOST, port: PORT });
    console.log(`auth-service listening on ${HOST}:${PORT}`);
  } catch (err) {
    app.log.error(err);
    process.exit(1);
  }
}

start();
