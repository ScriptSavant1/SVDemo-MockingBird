/**
 * Fastify application factory for auth-service.
 *
 * Builds and returns a configured Fastify instance.
 * Separated from server.ts so tests can import the app directly
 * without starting the HTTP listener.
 */
import Fastify, { FastifyInstance } from "fastify";
import databasePlugin from "./plugins/database.js";
import jwtPlugin from "./plugins/jwt.js";
import authRoutes from "./routes/auth.js";
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

  await app.register(databasePlugin);
  await app.register(jwtPlugin);
  await app.register(authRoutes);
  await app.register(userRoutes);

  return app;
}
