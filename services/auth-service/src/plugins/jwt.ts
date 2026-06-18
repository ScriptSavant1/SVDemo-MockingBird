/**
 * JWT signing/verification plugin.
 *
 * The JWT_SECRET must match the one used by project-service and all other
 * platform services that verify tokens.
 * In production this value comes from HashiCorp Vault.
 *
 * authenticate preHandler checks the Redis session cache (Sprint 12) when
 * app.redis is available — allows forced logout by deleting the session key.
 */
import fp from "fastify-plugin";
import fastifyJwt from "@fastify/jwt";
import type { FastifyInstance, FastifyRequest, FastifyReply } from "fastify";
import type { JwtPayload } from "../types/index.js";

const PROBLEM_UNAUTHORIZED = "https://mockingbird.internal/errors/unauthorized";

export default fp(async function jwtPlugin(app: FastifyInstance) {
  const secret = process.env["JWT_SECRET"];
  if (!secret) {
    throw new Error("JWT_SECRET environment variable is required");
  }
  await app.register(fastifyJwt, {
    secret,
    sign: { expiresIn: "8h" },
  });

  app.decorate(
    "authenticate",
    async function (request: FastifyRequest, reply: FastifyReply) {
      try {
        await request.jwtVerify();

        // Redis session check — only when Redis is configured (Sprint 12).
        // A missing session key means the token was explicitly invalidated via logout.
        if (app.redis) {
          const payload = request.user as JwtPayload;
          if (payload.jti) {
            const exists = await app.redis.exists(`session:${payload.jti}`);
            if (!exists) {
              return reply.status(401).send({
                type: PROBLEM_UNAUTHORIZED,
                title: "Session Expired",
                status: 401,
                detail: "Session has been invalidated. Please log in again.",
              });
            }
          }
        }
      } catch {
        reply.status(401).send({
          type: PROBLEM_UNAUTHORIZED,
          title: "Unauthorized",
          status: 401,
          detail: "Valid Bearer token required",
        });
      }
    }
  );
});
