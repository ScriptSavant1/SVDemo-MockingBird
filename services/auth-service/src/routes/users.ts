/**
 * User management routes — ADMIN only.
 *
 * Phase 1: local admin creates users with bcrypt passwords.
 * A first-run setup endpoint lets the initial admin be created
 * when the database has no users yet.
 */
import type { FastifyInstance, FastifyRequest, FastifyReply } from "fastify";
import bcrypt from "bcrypt";
import type { CreateUserBody, JwtPayload, ProblemDetail } from "../types/index.js";

const BCRYPT_ROUNDS = 12;
const PROBLEM_FORBIDDEN = "https://mockingbird.internal/errors/forbidden";
const PROBLEM_CONFLICT = "https://mockingbird.internal/errors/conflict";
const VALID_ROLES = new Set(["ADMIN", "SV_TEAM", "PROJECT_OWNER", "VIEWER"]);

export default async function userRoutes(app: FastifyInstance) {

  // POST /api/v1/auth/setup — create the first admin (only when users table is empty)
  app.post<{ Body: CreateUserBody }>(
    "/api/v1/auth/setup",
    {
      schema: {
        body: {
          type: "object",
          required: ["username", "email", "password"],
          properties: {
            username: { type: "string", minLength: 1, maxLength: 100 },
            email: { type: "string", format: "email" },
            password: { type: "string", minLength: 8 },
          },
        },
      },
    },
    async (request: FastifyRequest<{ Body: CreateUserBody }>, reply: FastifyReply) => {
      const count = await app.pg.query<{ count: string }>("SELECT COUNT(*) AS count FROM users");
      if (parseInt(count.rows[0]?.count ?? "1", 10) > 0) {
        return reply.status(409).send({
          type: PROBLEM_CONFLICT,
          title: "Setup Already Complete",
          status: 409,
          detail: "Admin user already exists. Use the login endpoint.",
        } satisfies ProblemDetail);
      }
      const { username, email, password } = request.body;
      const hash = await bcrypt.hash(password, BCRYPT_ROUNDS);
      const result = await app.pg.query<{ id: string; username: string; email: string; role: string; created_at: Date }>(
        `INSERT INTO users (username, email, password_hash, role)
         VALUES ($1, $2, $3, 'ADMIN')
         RETURNING id, username, email, role, created_at`,
        [username, email, hash]
      );
      const row = result.rows[0]!;
      return reply.status(201).send({ id: row.id, username: row.username, email: row.email, role: row.role, created_at: row.created_at });
    }
  );

  // POST /api/v1/users — create a new user (ADMIN only)
  app.post<{ Body: CreateUserBody }>(
    "/api/v1/users",
    {
      preHandler: [app.authenticate],
      schema: {
        body: {
          type: "object",
          required: ["username", "email", "password"],
          properties: {
            username: { type: "string", minLength: 1, maxLength: 100 },
            email: { type: "string", format: "email" },
            password: { type: "string", minLength: 8 },
            role: { type: "string", enum: ["ADMIN", "SV_TEAM", "PROJECT_OWNER", "VIEWER"] },
          },
        },
      },
    },
    async (request: FastifyRequest<{ Body: CreateUserBody }>, reply: FastifyReply) => {
      const caller = request.user as JwtPayload;
      if (caller.role !== "ADMIN") {
        return reply.status(403).send({
          type: PROBLEM_FORBIDDEN,
          title: "Forbidden",
          status: 403,
          detail: "Only admins can create users",
        } satisfies ProblemDetail);
      }
      const { username, email, password, role = "VIEWER" } = request.body;
      if (!VALID_ROLES.has(role)) {
        return reply.status(422).send({
          type: "https://mockingbird.internal/errors/validation",
          title: "Invalid Role",
          status: 422,
          detail: `role must be one of: ${[...VALID_ROLES].join(", ")}`,
        } satisfies ProblemDetail);
      }

      // Check uniqueness
      const existing = await app.pg.query(
        "SELECT id FROM users WHERE username = $1 OR email = $2",
        [username, email]
      );
      if (existing.rows.length > 0) {
        return reply.status(409).send({
          type: PROBLEM_CONFLICT,
          title: "User Already Exists",
          status: 409,
          detail: "A user with this username or email already exists",
        } satisfies ProblemDetail);
      }

      const hash = await bcrypt.hash(password, BCRYPT_ROUNDS);
      const result = await app.pg.query<{
        id: string; username: string; email: string; role: string; is_active: boolean; created_at: Date;
      }>(
        `INSERT INTO users (username, email, password_hash, role)
         VALUES ($1, $2, $3, $4)
         RETURNING id, username, email, role, is_active, created_at`,
        [username, email, hash, role]
      );
      const row = result.rows[0]!;
      return reply.status(201).send({
        id: row.id,
        username: row.username,
        email: row.email,
        role: row.role,
        is_active: row.is_active,
        created_at: row.created_at,
      });
    }
  );

  // GET /api/v1/users — list all users (ADMIN only)
  app.get(
    "/api/v1/users",
    { preHandler: [app.authenticate] },
    async (request: FastifyRequest, reply: FastifyReply) => {
      const caller = request.user as JwtPayload;
      if (caller.role !== "ADMIN") {
        return reply.status(403).send({
          type: PROBLEM_FORBIDDEN,
          title: "Forbidden",
          status: 403,
          detail: "Only admins can list users",
        } satisfies ProblemDetail);
      }
      const result = await app.pg.query<{
        id: string; username: string; email: string; role: string; is_active: boolean; created_at: Date;
      }>(
        "SELECT id, username, email, role, is_active, created_at FROM users ORDER BY created_at"
      );
      type UserRow = { id: string; username: string; email: string; role: string; is_active: boolean; created_at: Date };
      return reply.send((result.rows as UserRow[]).map((r) => ({
        id: r.id,
        username: r.username,
        email: r.email,
        role: r.role,
        is_active: r.is_active,
        created_at: r.created_at,
      })));
    }
  );
}
