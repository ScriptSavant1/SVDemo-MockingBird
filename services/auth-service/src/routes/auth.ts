/**
 * Auth routes — login, logout (stub), current user.
 *
 * Phase 1: local bcrypt credentials.
 * Phase 2 (Sprint 12): LDAP added alongside bcrypt.
 */
import type { FastifyInstance, FastifyRequest, FastifyReply } from "fastify";
import bcrypt from "bcrypt";
import type { LoginBody, JwtPayload, ProblemDetail } from "../types/index.js";

const PROBLEM_NOT_FOUND = "https://mockingbird.internal/errors/not-found";
const PROBLEM_UNAUTHORIZED = "https://mockingbird.internal/errors/unauthorized";

export default async function authRoutes(app: FastifyInstance) {

  // POST /api/v1/auth/login
  app.post<{ Body: LoginBody }>(
    "/api/v1/auth/login",
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
    async (request: FastifyRequest<{ Body: LoginBody }>, reply: FastifyReply) => {
      const { username, password } = request.body;

      const result = await app.pg.query<{
        id: string; username: string; email: string; role: string;
        password_hash: string; is_active: boolean;
      }>(
        "SELECT id, username, email, role, password_hash, is_active FROM users WHERE username = $1",
        [username]
      );

      if (result.rows.length === 0) {
        const problem: ProblemDetail = {
          type: PROBLEM_UNAUTHORIZED,
          title: "Invalid Credentials",
          status: 401,
          detail: "Username or password is incorrect",
        };
        return reply.status(401).send(problem);
      }

      const user = result.rows[0];
      if (!user || !user.is_active) {
        return reply.status(401).send({
          type: PROBLEM_UNAUTHORIZED,
          title: "Account Disabled",
          status: 401,
          detail: "This account has been disabled",
        } satisfies ProblemDetail);
      }

      const passwordMatch = await bcrypt.compare(password, user.password_hash);
      if (!passwordMatch) {
        return reply.status(401).send({
          type: PROBLEM_UNAUTHORIZED,
          title: "Invalid Credentials",
          status: 401,
          detail: "Username or password is incorrect",
        } satisfies ProblemDetail);
      }

      const payload: JwtPayload = {
        sub: user.id,
        username: user.username,
        role: user.role as JwtPayload["role"],
      };
      const token = app.jwt.sign(payload);

      return reply.status(200).send({
        access_token: token,
        token_type: "bearer",
        user: {
          id: user.id,
          username: user.username,
          email: user.email,
          role: user.role,
        },
      });
    }
  );

  // GET /api/v1/auth/me — returns current user from JWT
  app.get(
    "/api/v1/auth/me",
    { preHandler: [app.authenticate] },
    async (request: FastifyRequest, reply: FastifyReply) => {
      const payload = request.user as JwtPayload;
      const result = await app.pg.query<{
        id: string; username: string; email: string; role: string;
        is_active: boolean; created_at: Date;
      }>(
        "SELECT id, username, email, role, is_active, created_at FROM users WHERE id = $1",
        [payload.sub]
      );
      if (result.rows.length === 0) {
        return reply.status(404).send({
          type: PROBLEM_NOT_FOUND,
          title: "User Not Found",
          status: 404,
          detail: `User ${payload.sub} does not exist`,
        } satisfies ProblemDetail);
      }
      const row = result.rows[0]!;
      return reply.send({
        id: row.id,
        username: row.username,
        email: row.email,
        role: row.role,
        is_active: row.is_active,
        created_at: row.created_at,
      });
    }
  );

  // GET /health
  app.get("/health", async (_request, reply) => {
    return reply.send({ status: "ok", service: "auth-service", version: "0.1.0" });
  });
}
