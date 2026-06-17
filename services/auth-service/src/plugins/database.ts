/**
 * PostgreSQL connection plugin.
 *
 * In production the DATABASE_URL is injected by HashiCorp Vault via ECS
 * task definition environment variables.
 * NEVER hard-code the connection string.
 */
import fp from "fastify-plugin";
import fastifyPostgres from "@fastify/postgres";
import type { FastifyInstance } from "fastify";

export default fp(async function databasePlugin(app: FastifyInstance) {
  const url = process.env["DATABASE_URL"];
  if (!url) {
    throw new Error("DATABASE_URL environment variable is required");
  }
  await app.register(fastifyPostgres, { connectionString: url });
  app.log.info("Database plugin registered");
});
