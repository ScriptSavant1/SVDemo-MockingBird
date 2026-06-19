/**
 * Fastify application factory for auth-service.
 *
 * Builds and returns a configured Fastify instance.
 * Separated from server.ts so tests can import the app directly
 * without starting the HTTP listener.
 */
import Fastify, { FastifyInstance } from "fastify";
import databasePlugin from "./plugins/database.js";
import localDatabasePlugin from "./plugins/database-local.js";
import jwtPlugin from "./plugins/jwt.js";
import ldapPlugin from "./plugins/ldap.js";
import redisPlugin from "./plugins/redis.js";
import authRoutes from "./routes/auth.js";
import ldapRoutes from "./routes/ldap.js";
import userRoutes from "./routes/users.js";

declare module "fastify" {
  interface FastifyInstance {
    authenticate: (request: import("fastify").FastifyRequest, reply: import("fastify").FastifyReply) => Promise<void>;
  }
}

export async function buildApp(opts: { logger?: boolean } = {}): Promise<FastifyInstance> {
  const app = Fastify({
    logger: opts.logger ?? true,
  });

  // Use SQLite locally when no PostgreSQL DATABASE_URL is set.
  // In production (ECS + Vault) DATABASE_URL is always provided.
  const useLocalDb = !process.env["DATABASE_URL"] || process.env["DATABASE_URL"].startsWith("sqlite:");
  await app.register(useLocalDb ? localDatabasePlugin : databasePlugin);
  await app.register(jwtPlugin);
  await app.register(redisPlugin);   // no-op if REDIS_URL absent
  await app.register(ldapPlugin);    // no-op if LDAP_SERVER absent
  await app.register(authRoutes);
  await app.register(ldapRoutes);
  await app.register(userRoutes);

  return app;
}
