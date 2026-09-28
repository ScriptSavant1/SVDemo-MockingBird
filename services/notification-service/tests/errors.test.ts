/**
 * Error-shape plugin tests (docs/ERROR_CODES.md) — real Fastify via inject().
 */
import Fastify, { FastifyInstance } from "fastify";
import errorsPlugin from "../src/plugins/errors";

async function buildTestApp(): Promise<FastifyInstance> {
  const app = Fastify({ logger: false });
  await app.register(errorsPlugin, { serviceName: "test-service" });

  app.post(
    "/validate",
    {
      schema: {
        body: {
          type: "object",
          required: ["username", "password"],
          properties: { username: { type: "string" }, password: { type: "string", minLength: 8 } },
        },
      },
    },
    async () => ({ ok: true }),
  );
  app.get("/own-problem", async (_req, reply) =>
    reply.status(401).send({ type: "t", title: "Invalid Credentials", status: 401, detail: "Username or password is incorrect" }),
  );
  app.get("/legacy-message", async (_req, reply) => reply.status(409).send({ message: "User already exists" }));
  app.get("/crash", async () => {
    throw new Error("db password=hunter2 at /srv/internal");
  });
  app.get("/client-error", async () => {
    const err = new Error("Token expired") as Error & { statusCode: number };
    err.statusCode = 401;
    throw err;
  });
  app.get("/ok", async () => ({ fine: true }));
  await app.ready();
  return app;
}

describe("errors plugin", () => {
  let app: FastifyInstance;
  beforeAll(async () => {
    app = await buildTestApp();
  });
  afterAll(async () => {
    await app.close();
  });

  it("adds a code to a route's own Problem JSON without changing it", async () => {
    const res = await app.inject({ method: "GET", url: "/own-problem" });
    expect(res.statusCode).toBe(401);
    const body = res.json();
    expect(body.code).toBe("MB-REQ-401");
    expect(body.detail).toBe("Username or password is incorrect");
    expect(body.title).toBe("Invalid Credentials");
  });

  it("turns a message-only error body into a string detail", async () => {
    const body = (await app.inject({ method: "GET", url: "/legacy-message" })).json();
    expect(body.code).toBe("MB-REQ-409");
    expect(body.detail).toBe("User already exists");
  });

  it("reports a missing required field in one line", async () => {
    const res = await app.inject({ method: "POST", url: "/validate", payload: { username: "x" } });
    expect(res.statusCode).toBe(400);
    expect(res.json().code).toBe("MB-REQ-400");
    expect(res.json().detail).toBe("Missing required field 'password'");
  });

  it("reports an invalid field value in one line", async () => {
    const res = await app.inject({ method: "POST", url: "/validate", payload: { username: "x", password: "short" } });
    expect(res.json().detail).toMatch(/^Invalid value for 'password': /);
  });

  it("hides internals of an unexpected error but gives a ref", async () => {
    const res = await app.inject({ method: "GET", url: "/crash" });
    expect(res.statusCode).toBe(500);
    const body = res.json();
    expect(body.code).toBe("MB-SYS-001");
    expect(body.ref).toHaveLength(8);
    expect(body.detail).toContain(`(ref ${body.ref})`);
    expect(body.detail).toContain("test-service");
    expect(res.body).not.toContain("hunter2");
    expect(res.body).not.toContain("/srv/internal");
  });

  it("keeps a thrown 4xx's own message", async () => {
    const body = (await app.inject({ method: "GET", url: "/client-error" })).json();
    expect(body.code).toBe("MB-REQ-401");
    expect(body.detail).toBe("Token expired");
  });

  it("gives unknown routes a coded 404", async () => {
    const body = (await app.inject({ method: "GET", url: "/nope?x=1" })).json();
    expect(body.code).toBe("MB-REQ-404");
    expect(body.detail).toBe("No such endpoint: GET /nope");
  });

  it("leaves successful responses alone", async () => {
    const res = await app.inject({ method: "GET", url: "/ok" });
    expect(res.json()).toEqual({ fine: true });
  });
});
