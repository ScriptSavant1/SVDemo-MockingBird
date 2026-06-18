/**
 * LDAP login route (Phase 2 / Sprint 12).
 *
 * POST /api/v1/auth/ldap/login
 *   - Verifies credentials against LDAP directory
 *   - Maps LDAP groups to Mockingbird roles
 *   - Upserts user record in PostgreSQL
 *   - Returns same JWT response shape as local login
 *
 * Returns 503 when LDAP is not configured (LDAP_SERVER env var absent).
 * Phase 1 local login remains fully operational alongside this endpoint.
 */
import { randomUUID } from "crypto";
import type { FastifyInstance, FastifyRequest, FastifyReply } from "fastify";
import type { LdapLoginBody, JwtPayload, ProblemDetail } from "../types/index.js";

const PROBLEM_UNAUTHORIZED = "https://mockingbird.internal/errors/unauthorized";
const PROBLEM_UNAVAILABLE = "https://mockingbird.internal/errors/service-unavailable";
const JWT_TTL_SECONDS = 8 * 60 * 60;

export default async function ldapRoutes(app: FastifyInstance) {

  app.post<{ Body: LdapLoginBody }>(
    "/api/v1/auth/ldap/login",
    {
      schema: {
        body: {
          type: "object",
          required: ["username", "password"],
          properties: {
            username: { type: "string", minLength: 1 },
            password: { type: "string", minLength: 1 },
          },
        },
      },
    },
    async (request: FastifyRequest<{ Body: LdapLoginBody }>, reply: FastifyReply) => {
      if (!app.ldap) {
        return reply.status(503).send({
          type: PROBLEM_UNAVAILABLE,
          title: "Service Unavailable",
          status: 503,
          detail: "LDAP authentication is not configured on this server",
        } satisfies ProblemDetail);
      }

      const { username, password } = request.body;

      // Verify credentials against LDAP
      let ldapResult: Awaited<ReturnType<typeof app.ldap.lookupAndVerify>>;
      try {
        ldapResult = await app.ldap.lookupAndVerify(username, password);
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        if (msg === "LDAP_USER_NOT_FOUND") {
          return reply.status(401).send({
            type: PROBLEM_UNAUTHORIZED,
            title: "Invalid Credentials",
            status: 401,
            detail: "Username not found in directory",
          } satisfies ProblemDetail);
        }
        // ldapts throws InvalidCredentialsError for wrong password
        return reply.status(401).send({
          type: PROBLEM_UNAUTHORIZED,
          title: "Invalid Credentials",
          status: 401,
          detail: "Username or password is incorrect",
        } satisfies ProblemDetail);
      }

      // Upsert user in PostgreSQL (create on first login; sync role on subsequent logins)
      const newUserId = randomUUID();
      const upsertResult = await app.pg.query<{
        id: string; username: string; email: string; role: string;
      }>(
        `INSERT INTO users (id, username, email, password_hash, role, is_active)
         VALUES ($1, $2, $3, '$LDAP$', $4, true)
         ON CONFLICT (username) DO UPDATE
           SET role = EXCLUDED.role,
               email = EXCLUDED.email,
               updated_at = NOW()
         RETURNING id, username, email, role`,
        [newUserId, username, ldapResult.email, ldapResult.role]
      );

      const user = upsertResult.rows[0]!;
      const jti = randomUUID();
      const payload: JwtPayload = {
        sub: user.id,
        username: user.username,
        role: user.role as JwtPayload["role"],
        jti,
      };
      const token = app.jwt.sign(payload);

      if (app.redis) {
        await app.redis.set(`session:${jti}`, JSON.stringify(payload), "EX", JWT_TTL_SECONDS);
      }

      return reply.status(200).send({
        access_token: token,
        token_type: "bearer",
        auth_method: "ldap",
        user: {
          id: user.id,
          username: user.username,
          email: user.email,
          role: user.role,
        },
      });
    }
  );
}
