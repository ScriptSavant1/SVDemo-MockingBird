/**
 * Phase 3 Sprint 12 — LDAP authentication + Redis session cache tests.
 *
 * Tests use Fastify inject() API — no real LDAP server or Redis required.
 * app.ldap is mocked via Fastify decoration.
 * app.redis is mocked with a minimal in-memory Map-backed implementation.
 */
import Fastify, { FastifyInstance } from "fastify";
import fastifyJwt from "@fastify/jwt";
import type { JwtPayload } from "../src/types/index";
import type { LdapClient, LdapLookupResult } from "../src/plugins/ldap";
import authRoutes from "../src/routes/auth";
import ldapRoutes from "../src/routes/ldap";
import userRoutes from "../src/routes/users";

const JWT_SECRET = "test-jwt-secret-ldap";

// ── minimal Redis mock ────────────────────────────────────────────────────────

function makeRedisMock() {
  const store = new Map<string, string>();
  return {
    async get(key: string) { return store.get(key) ?? null; },
    async set(key: string, value: string, _mode: string, _ttl: number) {
      store.set(key, value);
      return "OK" as const;
    },
    async del(...keys: string[]) {
      let count = 0;
      for (const k of keys) { if (store.delete(k)) count++; }
      return count;
    },
    async exists(...keys: string[]) {
      return keys.filter((k) => store.has(k)).length;
    },
    async quit() { store.clear(); },
    _store: store,
  };
}

// ── mock DB rows ──────────────────────────────────────────────────────────────

const LDAP_USER_ID = "cccccccc-0000-0000-0000-000000000001";

const MOCK_PG = {
  query: async (sql: string, params?: unknown[]) => {
    // LDAP upsert → always return the ldap user row
    if (sql.includes("INSERT INTO users")) {
      return {
        rows: [{
          id: LDAP_USER_ID,
          username: params?.[1] ?? "ldapuser",
          email: params?.[2] ?? "ldapuser@company.com",
          role: params?.[3] ?? "SV_TEAM",
        }],
      };
    }
    // SELECT by id for /me
    if (sql.includes("WHERE id = $1")) {
      return {
        rows: [{
          id: LDAP_USER_ID,
          username: "ldapuser",
          email: "ldapuser@company.com",
          role: "SV_TEAM",
          is_active: true,
          created_at: new Date("2026-01-01"),
        }],
      };
    }
    return { rows: [] };
  },
};

// ── build test app ────────────────────────────────────────────────────────────

type RedisMock = ReturnType<typeof makeRedisMock>;

async function buildLdapApp(
  ldapOverride?: LdapClient | null,
  redisMock?: RedisMock
): Promise<FastifyInstance> {
  const app = Fastify({ logger: false });

  await app.register(fastifyJwt, { secret: JWT_SECRET, sign: { expiresIn: "8h" } });

  // Authenticate decorator with Redis session check (mirrors production behaviour)
  app.decorate(
    "authenticate",
    async function (request: import("fastify").FastifyRequest, reply: import("fastify").FastifyReply) {
      try {
        await request.jwtVerify();
        if ((app as FastifyInstance & { redis?: RedisMock }).redis) {
          const payload = request.user as JwtPayload;
          if (payload.jti) {
            const exists = await (app as FastifyInstance & { redis?: RedisMock }).redis!.exists(`session:${payload.jti}`);
            if (!exists) {
              return reply.status(401).send({
                type: "https://mockingbird.internal/errors/unauthorized",
                title: "Session Expired",
                status: 401,
                detail: "Session has been invalidated. Please log in again.",
              });
            }
          }
        }
      } catch {
        reply.status(401).send({
          type: "https://mockingbird.internal/errors/unauthorized",
          title: "Unauthorized",
          status: 401,
          detail: "Token required",
        });
      }
    }
  );

  app.decorate("pg", MOCK_PG as unknown as FastifyInstance["pg"]);

  if (ldapOverride !== null) {
    app.decorate("ldap", ldapOverride ?? undefined);
  }

  if (redisMock) {
    app.decorate("redis", redisMock as unknown as FastifyInstance["redis"]);
  }

  await app.register(authRoutes);
  await app.register(ldapRoutes);
  await app.register(userRoutes);

  return app;
}

// ── helpers ───────────────────────────────────────────────────────────────────

function makeLdapClient(result: LdapLookupResult): LdapClient {
  return {
    lookupAndVerify: jest.fn().mockResolvedValue(result),
  };
}

function makeFailingLdapClient(errorMsg: string): LdapClient {
  return {
    lookupAndVerify: jest.fn().mockRejectedValue(new Error(errorMsg)),
  };
}

// ── POST /api/v1/auth/ldap/login — LDAP not configured ───────────────────────

describe("POST /api/v1/auth/ldap/login — LDAP not configured", () => {
  let app: FastifyInstance;

  beforeAll(async () => {
    app = await buildLdapApp(undefined); // no ldap decoration
    await app.ready();
  });

  afterAll(() => app.close());

  it("returns 503 when LDAP not configured", async () => {
    const resp = await app.inject({
      method: "POST",
      url: "/api/v1/auth/ldap/login",
      payload: { username: "user1", password: "pass" },
    });
    expect(resp.statusCode).toBe(503);
    expect(resp.json().title).toBe("Service Unavailable");
  });
});

// ── POST /api/v1/auth/ldap/login — successful logins ─────────────────────────

describe("POST /api/v1/auth/ldap/login — success", () => {
  let app: FastifyInstance;
  const redisMock = makeRedisMock();

  beforeAll(async () => {
    const ldapClient = makeLdapClient({
      dn: "CN=ldapuser,OU=Users,DC=company,DC=com",
      email: "ldapuser@company.com",
      role: "ADMIN",
    });
    app = await buildLdapApp(ldapClient, redisMock);
    await app.ready();
  });

  afterAll(() => app.close());

  it("returns 200 with access_token and auth_method=ldap", async () => {
    const resp = await app.inject({
      method: "POST",
      url: "/api/v1/auth/ldap/login",
      payload: { username: "ldapuser", password: "correct-pass" },
    });
    expect(resp.statusCode).toBe(200);
    const body = resp.json();
    expect(body.access_token).toBeDefined();
    expect(body.token_type).toBe("bearer");
    expect(body.auth_method).toBe("ldap");
    expect(body.user.username).toBe("ldapuser");
  });

  it("JWT contains correct claims including jti", async () => {
    const resp = await app.inject({
      method: "POST",
      url: "/api/v1/auth/ldap/login",
      payload: { username: "ldapuser", password: "correct-pass" },
    });
    const { access_token } = resp.json<{ access_token: string }>();
    const decoded = app.jwt.verify(access_token) as JwtPayload;
    expect(decoded.username).toBe("ldapuser");
    expect(decoded.role).toBe("ADMIN");
    expect(decoded.sub).toBe(LDAP_USER_ID);
    expect(decoded.jti).toMatch(/^[0-9a-f-]{36}$/);
  });

  it("session is cached in Redis after login", async () => {
    const resp = await app.inject({
      method: "POST",
      url: "/api/v1/auth/ldap/login",
      payload: { username: "ldapuser", password: "correct-pass" },
    });
    const { access_token } = resp.json<{ access_token: string }>();
    const { jti } = app.jwt.verify(access_token) as JwtPayload;
    expect(jti).toBeDefined();
    const cached = await redisMock.get(`session:${jti!}`);
    expect(cached).not.toBeNull();
    const parsed = JSON.parse(cached!);
    expect(parsed.username).toBe("ldapuser");
  });

  it("returns 400 when body fields are missing", async () => {
    const resp = await app.inject({
      method: "POST",
      url: "/api/v1/auth/ldap/login",
      payload: { username: "ldapuser" }, // no password
    });
    expect(resp.statusCode).toBe(400);
  });
});

// ── POST /api/v1/auth/ldap/login — failure cases ─────────────────────────────

describe("POST /api/v1/auth/ldap/login — LDAP failures", () => {
  it("returns 401 when user not found in LDAP", async () => {
    const app = await buildLdapApp(makeFailingLdapClient("LDAP_USER_NOT_FOUND"));
    await app.ready();
    const resp = await app.inject({
      method: "POST",
      url: "/api/v1/auth/ldap/login",
      payload: { username: "nobody", password: "any" },
    });
    await app.close();
    expect(resp.statusCode).toBe(401);
    expect(resp.json().detail).toMatch(/not found/i);
  });

  it("returns 401 for invalid password (LDAP bind fails)", async () => {
    const app = await buildLdapApp(makeFailingLdapClient("InvalidCredentialsError"));
    await app.ready();
    const resp = await app.inject({
      method: "POST",
      url: "/api/v1/auth/ldap/login",
      payload: { username: "ldapuser", password: "wrong-pass" },
    });
    await app.close();
    expect(resp.statusCode).toBe(401);
    expect(resp.json().title).toBe("Invalid Credentials");
  });
});

// ── POST /api/v1/auth/logout ──────────────────────────────────────────────────

describe("POST /api/v1/auth/logout", () => {
  let app: FastifyInstance;
  const redisMock = makeRedisMock();

  beforeAll(async () => {
    const ldapClient = makeLdapClient({
      dn: "CN=ldapuser,OU=Users,DC=company,DC=com",
      email: "ldapuser@company.com",
      role: "SV_TEAM",
    });
    app = await buildLdapApp(ldapClient, redisMock);
    await app.ready();
  });

  afterAll(() => app.close());

  it("returns 200 on successful logout", async () => {
    // First login to get a valid token with Redis session
    const loginResp = await app.inject({
      method: "POST",
      url: "/api/v1/auth/ldap/login",
      payload: { username: "ldapuser", password: "pass" },
    });
    const { access_token } = loginResp.json<{ access_token: string }>();

    const logoutResp = await app.inject({
      method: "POST",
      url: "/api/v1/auth/logout",
      headers: { Authorization: `Bearer ${access_token}` },
    });
    expect(logoutResp.statusCode).toBe(200);
    expect(logoutResp.json().message).toBe("Logged out successfully");
  });

  it("session deleted from Redis after logout", async () => {
    const loginResp = await app.inject({
      method: "POST",
      url: "/api/v1/auth/ldap/login",
      payload: { username: "ldapuser", password: "pass" },
    });
    const { access_token } = loginResp.json<{ access_token: string }>();
    const { jti } = app.jwt.verify(access_token) as JwtPayload;

    // Verify session exists
    expect(await redisMock.exists(`session:${jti!}`)).toBe(1);

    // Logout
    await app.inject({
      method: "POST",
      url: "/api/v1/auth/logout",
      headers: { Authorization: `Bearer ${access_token}` },
    });

    // Session must be gone
    expect(await redisMock.exists(`session:${jti!}`)).toBe(0);
  });

  it("authenticated request fails after logout (session invalidated)", async () => {
    const loginResp = await app.inject({
      method: "POST",
      url: "/api/v1/auth/ldap/login",
      payload: { username: "ldapuser", password: "pass" },
    });
    const { access_token } = loginResp.json<{ access_token: string }>();

    // Logout
    await app.inject({
      method: "POST",
      url: "/api/v1/auth/logout",
      headers: { Authorization: `Bearer ${access_token}` },
    });

    // /me should now return 401
    const meResp = await app.inject({
      method: "GET",
      url: "/api/v1/auth/me",
      headers: { Authorization: `Bearer ${access_token}` },
    });
    expect(meResp.statusCode).toBe(401);
    expect(meResp.json().title).toBe("Session Expired");
  });

  it("logout returns 401 without token", async () => {
    const resp = await app.inject({ method: "POST", url: "/api/v1/auth/logout" });
    expect(resp.statusCode).toBe(401);
  });
});

// ── role mapping (via LDAP group injection) ───────────────────────────────────

describe("LDAP role mapping", () => {
  async function loginWithRole(role: "ADMIN" | "SV_TEAM" | "VIEWER") {
    const ldapClient = makeLdapClient({
      dn: "CN=ldapuser,OU=Users,DC=company,DC=com",
      email: "ldapuser@company.com",
      role,
    });
    const app = await buildLdapApp(ldapClient);
    await app.ready();
    const resp = await app.inject({
      method: "POST",
      url: "/api/v1/auth/ldap/login",
      payload: { username: "ldapuser", password: "pass" },
    });
    const body = resp.json();
    await app.close();
    return body;
  }

  it("SV-Team group → ADMIN role", async () => {
    const body = await loginWithRole("ADMIN");
    expect(body.user.role).toBe("ADMIN");
  });

  it("SV-Users group → SV_TEAM role", async () => {
    const body = await loginWithRole("SV_TEAM");
    expect(body.user.role).toBe("SV_TEAM");
  });

  it("no matching group → VIEWER role", async () => {
    const body = await loginWithRole("VIEWER");
    expect(body.user.role).toBe("VIEWER");
  });
});
