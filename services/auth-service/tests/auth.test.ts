/**
 * Phase 3 Sprint 9 — auth-service tests.
 *
 * Tests use Fastify's inject() API (no HTTP server needed) and mock the
 * pg plugin so no real PostgreSQL server is required.
 *
 * To run: npm install && npm test
 */
import Fastify, { FastifyInstance } from "fastify";
import fastifyJwt from "@fastify/jwt";
import bcrypt from "bcrypt";
import authRoutes from "../src/routes/auth";
import userRoutes from "../src/routes/users";

const JWT_SECRET = "test-jwt-secret";

// ── mock database rows ────────────────────────────────────────────────────────

const ADMIN_HASH = bcrypt.hashSync("admin-password-123", 10);
const SV_HASH = bcrypt.hashSync("sv-password-123", 10);

const MOCK_USERS: Record<string, object> = {
  admin: {
    id: "00000000-0000-0000-0000-000000000001",
    username: "admin",
    email: "admin@company.com",
    password_hash: ADMIN_HASH,
    role: "ADMIN",
    is_active: true,
    created_at: new Date("2026-01-01"),
  },
  "sv.engineer": {
    id: "00000000-0000-0000-0000-000000000002",
    username: "sv.engineer",
    email: "sv@company.com",
    password_hash: SV_HASH,
    role: "SV_TEAM",
    is_active: true,
    created_at: new Date("2026-01-02"),
  },
  disabled: {
    id: "00000000-0000-0000-0000-000000000003",
    username: "disabled",
    email: "disabled@company.com",
    password_hash: ADMIN_HASH,
    role: "VIEWER",
    is_active: false,
    created_at: new Date("2026-01-03"),
  },
};

// ── build test app ────────────────────────────────────────────────────────────

async function buildTestApp(): Promise<FastifyInstance> {
  const app = Fastify({ logger: false });

  // Register JWT plugin (same as production but with test secret)
  await app.register(fastifyJwt, { secret: JWT_SECRET, sign: { expiresIn: "8h" } });

  // Authenticate decorator (mirrors jwt plugin)
  app.decorate(
    "authenticate",
    async function (request: import("fastify").FastifyRequest, reply: import("fastify").FastifyReply) {
      try {
        await request.jwtVerify();
      } catch {
        reply.status(401).send({ type: "unauthorized", title: "Unauthorized", status: 401, detail: "Token required" });
      }
    }
  );

  // Mock pg plugin — queries return from MOCK_USERS in memory
  app.decorate("pg", {
    query: async (sql: string, params?: unknown[]) => {
      // SELECT user by username (login)
      if (sql.includes("WHERE username = $1") && params?.[0]) {
        const user = MOCK_USERS[params[0] as string];
        return { rows: user ? [user] : [] };
      }
      // SELECT user by id (me endpoint)
      if (sql.includes("WHERE id = $1") && params?.[0]) {
        const user = Object.values(MOCK_USERS).find(
          (u) => (u as { id: string }).id === params[0]
        );
        return { rows: user ? [user] : [] };
      }
      // Count for setup endpoint
      if (sql.includes("COUNT(*)")) {
        return { rows: [{ count: String(Object.keys(MOCK_USERS).length) }] };
      }
      // Uniqueness check for user creation
      if (sql.includes("WHERE username = $1 OR email = $2") && params) {
        const exists = Object.values(MOCK_USERS).some(
          (u) => (u as Record<string, string>)["username"] === params[0] ||
                  (u as Record<string, string>)["email"] === params[1]
        );
        return { rows: exists ? [{}] : [] };
      }
      // INSERT new user (user creation)
      if (sql.includes("INSERT INTO users")) {
        const now = new Date();
        return {
          rows: [{
            id: "00000000-0000-0000-0000-999999999999",
            username: (params as string[])?.[0],
            email: (params as string[])?.[1],
            role: (params as string[])?.[3] ?? "VIEWER",
            is_active: true,
            created_at: now,
          }],
        };
      }
      // List all users
      if (sql.includes("SELECT id, username, email, role")) {
        return { rows: Object.values(MOCK_USERS) };
      }
      return { rows: [] };
    },
  } as unknown as FastifyInstance["pg"]);

  await app.register(authRoutes);
  await app.register(userRoutes);

  return app;
}

// ── helpers ───────────────────────────────────────────────────────────────────

let app: FastifyInstance;

beforeAll(async () => {
  app = await buildTestApp();
  await app.ready();
});

afterAll(async () => {
  await app.close();
});

function makeToken(sub: string, username: string, role: string): string {
  return app.jwt.sign({ sub, username, role });
}

// ── health ────────────────────────────────────────────────────────────────────

describe("GET /health", () => {
  it("returns 200 ok", async () => {
    const resp = await app.inject({ method: "GET", url: "/health" });
    expect(resp.statusCode).toBe(200);
    expect(resp.json().status).toBe("ok");
    expect(resp.json().service).toBe("auth-service");
  });
});

// ── POST /api/v1/auth/login ───────────────────────────────────────────────────

describe("POST /api/v1/auth/login", () => {
  it("returns 200 and access_token for valid admin credentials", async () => {
    const resp = await app.inject({
      method: "POST",
      url: "/api/v1/auth/login",
      payload: { username: "admin", password: "admin-password-123" },
    });
    expect(resp.statusCode).toBe(200);
    const body = resp.json();
    expect(body.access_token).toBeDefined();
    expect(body.token_type).toBe("bearer");
    expect(body.user.username).toBe("admin");
    expect(body.user.role).toBe("ADMIN");
  });

  it("returns 200 for SV_TEAM user", async () => {
    const resp = await app.inject({
      method: "POST",
      url: "/api/v1/auth/login",
      payload: { username: "sv.engineer", password: "sv-password-123" },
    });
    expect(resp.statusCode).toBe(200);
    expect(resp.json().user.role).toBe("SV_TEAM");
  });

  it("returns 401 for wrong password", async () => {
    const resp = await app.inject({
      method: "POST",
      url: "/api/v1/auth/login",
      payload: { username: "admin", password: "wrong-password" },
    });
    expect(resp.statusCode).toBe(401);
    expect(resp.json().title).toBe("Invalid Credentials");
  });

  it("returns 401 for unknown username", async () => {
    const resp = await app.inject({
      method: "POST",
      url: "/api/v1/auth/login",
      payload: { username: "nobody", password: "any-password" },
    });
    expect(resp.statusCode).toBe(401);
  });

  it("returns 401 for disabled account", async () => {
    const resp = await app.inject({
      method: "POST",
      url: "/api/v1/auth/login",
      payload: { username: "disabled", password: "admin-password-123" },
    });
    expect(resp.statusCode).toBe(401);
  });

  it("returns 400 when body fields are missing", async () => {
    const resp = await app.inject({
      method: "POST",
      url: "/api/v1/auth/login",
      payload: { username: "admin" },
    });
    expect(resp.statusCode).toBe(400);
  });

  it("JWT token contains correct claims", async () => {
    const resp = await app.inject({
      method: "POST",
      url: "/api/v1/auth/login",
      payload: { username: "admin", password: "admin-password-123" },
    });
    const { access_token } = resp.json();
    const decoded = app.jwt.verify(access_token) as { sub: string; username: string; role: string };
    expect(decoded.username).toBe("admin");
    expect(decoded.role).toBe("ADMIN");
    expect(decoded.sub).toBeDefined();
  });
});

// ── GET /api/v1/auth/me ───────────────────────────────────────────────────────

describe("GET /api/v1/auth/me", () => {
  it("returns current user for valid token", async () => {
    const token = makeToken("00000000-0000-0000-0000-000000000001", "admin", "ADMIN");
    const resp = await app.inject({
      method: "GET",
      url: "/api/v1/auth/me",
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(resp.statusCode).toBe(200);
    expect(resp.json().username).toBe("admin");
  });

  it("returns 401 with no token", async () => {
    const resp = await app.inject({ method: "GET", url: "/api/v1/auth/me" });
    expect(resp.statusCode).toBe(401);
  });

  it("returns 401 with invalid token", async () => {
    const resp = await app.inject({
      method: "GET",
      url: "/api/v1/auth/me",
      headers: { Authorization: "Bearer not-a-valid-jwt" },
    });
    expect(resp.statusCode).toBe(401);
  });
});

// ── POST /api/v1/users ────────────────────────────────────────────────────────

describe("POST /api/v1/users", () => {
  it("admin can create a new user", async () => {
    const token = makeToken("00000000-0000-0000-0000-000000000001", "admin", "ADMIN");
    const resp = await app.inject({
      method: "POST",
      url: "/api/v1/users",
      headers: { Authorization: `Bearer ${token}` },
      payload: {
        username: "new.engineer",
        email: "new@company.com",
        password: "secure-password-123",
        role: "SV_TEAM",
      },
    });
    expect(resp.statusCode).toBe(201);
    expect(resp.json().username).toBe("new.engineer");
    expect(resp.json().role).toBe("SV_TEAM");
  });

  it("non-admin gets 403", async () => {
    const token = makeToken("00000000-0000-0000-0000-000000000002", "sv.engineer", "SV_TEAM");
    const resp = await app.inject({
      method: "POST",
      url: "/api/v1/users",
      headers: { Authorization: `Bearer ${token}` },
      payload: {
        username: "another",
        email: "another@company.com",
        password: "secure-password-123",
      },
    });
    expect(resp.statusCode).toBe(403);
  });

  it("returns 409 for duplicate username", async () => {
    const token = makeToken("00000000-0000-0000-0000-000000000001", "admin", "ADMIN");
    const resp = await app.inject({
      method: "POST",
      url: "/api/v1/users",
      headers: { Authorization: `Bearer ${token}` },
      payload: {
        username: "admin",  // duplicate
        email: "new2@company.com",
        password: "secure-password-123",
      },
    });
    expect(resp.statusCode).toBe(409);
  });

  it("returns 401 with no token", async () => {
    const resp = await app.inject({
      method: "POST",
      url: "/api/v1/users",
      payload: { username: "x", email: "x@test.com", password: "secure-123" },
    });
    expect(resp.statusCode).toBe(401);
  });

  it("returns 400 for missing required fields", async () => {
    const token = makeToken("00000000-0000-0000-0000-000000000001", "admin", "ADMIN");
    const resp = await app.inject({
      method: "POST",
      url: "/api/v1/users",
      headers: { Authorization: `Bearer ${token}` },
      payload: { username: "nopassword", email: "x@test.com" },
    });
    expect(resp.statusCode).toBe(400);
  });
});

// ── GET /api/v1/users ─────────────────────────────────────────────────────────

describe("GET /api/v1/users", () => {
  it("admin can list users", async () => {
    const token = makeToken("00000000-0000-0000-0000-000000000001", "admin", "ADMIN");
    const resp = await app.inject({
      method: "GET",
      url: "/api/v1/users",
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(resp.statusCode).toBe(200);
    expect(Array.isArray(resp.json())).toBe(true);
  });

  it("non-admin gets 403", async () => {
    const token = makeToken("00000000-0000-0000-0000-000000000002", "sv.engineer", "SV_TEAM");
    const resp = await app.inject({
      method: "GET",
      url: "/api/v1/users",
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(resp.statusCode).toBe(403);
  });
});
