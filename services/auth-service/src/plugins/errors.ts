/**
 * One error shape for every response this service sends (docs/ERROR_CODES.md).
 *
 * Every non-2xx body is RFC 7807 Problem JSON plus a Mockingbird code:
 *   { type, title, status, code: "MB-REQ-401", detail: "<one line>", ref? }
 *
 * - Routes that already send Problem JSON get `code` added (onSend hook),
 *   so no route needs editing.
 * - Schema-validation failures become one readable line.
 * - Unexpected errors become MB-SYS-001 with a short `ref`; the stack/message
 *   is logged under that ref and never sent to the client.
 *
 * notification-service has an identical copy (services deploy independently).
 */
import fp from "fastify-plugin";
import { randomUUID } from "node:crypto";
import type { FastifyError, FastifyInstance } from "fastify";

export const SYS_UNEXPECTED = "MB-SYS-001";

const TYPE_BASE = "https://mockingbird.internal/errors/";
const TITLES: Record<number, string> = {
  400: "Bad request",
  401: "Not signed in",
  403: "Not allowed",
  404: "Not found",
  409: "Conflict",
  422: "Invalid request",
  500: "Server error",
  503: "Service unavailable",
};

export interface ProblemBody {
  type: string;
  title: string;
  status: number;
  code: string;
  detail: string;
  ref?: string;
}

export function requestCode(status: number): string {
  return `MB-REQ-${status}`;
}

export function problem(status: number, code: string, detail: string, title?: string, ref?: string): ProblemBody {
  const body: ProblemBody = {
    type: TYPE_BASE + code.toLowerCase(),
    title: title ?? TITLES[status] ?? "Request failed",
    status,
    code,
    detail,
  };
  if (ref) body.ref = ref;
  return body;
}

function validationLine(error: FastifyError): string {
  const issues = error.validation ?? [];
  const first = issues[0];
  const params = (first?.params ?? {}) as { missingProperty?: string };
  const path = (first?.instancePath ?? "").replace(/^\//, "").replace(/\//g, ".");
  const more = issues.length > 1 ? ` (+${issues.length - 1} more)` : "";
  if (first?.keyword === "required" && params.missingProperty) {
    const field = path ? `${path}.${params.missingProperty}` : params.missingProperty;
    return `Missing required field '${field}'${more}`;
  }
  return `Invalid value for '${path || "request"}': ${first?.message ?? "invalid"}${more}`;
}

export default fp(async function errorsPlugin(app: FastifyInstance, opts: { serviceName: string }) {
  const service = opts.serviceName;

  app.setErrorHandler((error: FastifyError, request, reply) => {
    if (error.validation) {
      return reply.status(400).send(problem(400, requestCode(400), validationLine(error)));
    }
    const status = error.statusCode ?? 500;
    if (status >= 400 && status < 500) {
      return reply.status(status).send(problem(status, requestCode(status), error.message || (TITLES[status] ?? "Request failed")));
    }
    const ref = randomUUID().replace(/-/g, "").slice(0, 8);
    request.log.error({ err: error, ref }, `[ref ${ref}] Unhandled error on ${request.method} ${request.url}`);
    return reply.status(500).send(problem(
      500, SYS_UNEXPECTED,
      `Unexpected error in ${service} (ref ${ref}) — the details are in the server log`,
      "Server error", ref,
    ));
  });

  app.setNotFoundHandler((request, reply) =>
    reply.status(404).send(problem(404, requestCode(404), `No such endpoint: ${request.method} ${request.url.split("?")[0]}`)),
  );

  // Routes that send their own error bodies: add the code (and make sure
  // `detail` is a string) without touching each route.
  app.addHook("onSend", async (_request, reply, payload) => {
    if (reply.statusCode < 400 || typeof payload !== "string") return payload;
    try {
      const body = JSON.parse(payload) as Record<string, unknown>;
      if (!body || typeof body !== "object" || Array.isArray(body) || typeof body["code"] === "string") return payload;
      body["code"] = requestCode(reply.statusCode);
      if (typeof body["detail"] !== "string") {
        body["detail"] = String(body["message"] ?? body["title"] ?? TITLES[reply.statusCode] ?? "Request failed");
      }
      return JSON.stringify(body);
    } catch {
      return payload;
    }
  });
});
