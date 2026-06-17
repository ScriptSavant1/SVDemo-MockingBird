/**
 * JWT signing/verification plugin.
 *
 * The JWT_SECRET must match the one used by project-service and all other
 * platform services that verify tokens.
 * In production this value comes from HashiCorp Vault.
 */
import fp from "fastify-plugin";
import fastifyJwt from "@fastify/jwt";
import type { FastifyInstance, FastifyRequest, FastifyReply } from "fastify";

export default fp(async function jwtPlugin(app: FastifyInstance) {
  const secret = process.env["JWT_SECRET"];
  if (!secret) {
    throw new Error("JWT_SECRET environment variable is required");
  }
  await app.register(fastifyJwt, {
    secret,
    sign: { expiresIn: "8h" },
  });

  // Convenience decorator — call app.authenticate(request, reply) in routes
  app.decorate(
    "authenticate",
    async function (request: FastifyRequest, reply: FastifyReply) {
      try {
        await request.jwtVerify();
      } catch {
        reply.status(401).send({
          type: "https://mockingbird.internal/errors/unauthorized",
          title: "Unauthorized",
          status: 401,
          detail: "Valid Bearer token required",
        });
      }
    }
  );
});
