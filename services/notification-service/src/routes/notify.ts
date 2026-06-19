import type { FastifyInstance, FastifyRequest, FastifyReply } from "fastify";
import { dispatch } from "../handlers/events.js";
import type { EventType, NotificationEvent, ProblemDetail } from "../types/index.js";

const VALID_EVENT_TYPES = new Set<EventType>([
  "stub.deployed",
  "deploy.failed",
  "report.ready",
  "stub.suspended",
]);

interface SendBody {
  event_type: string;
  project_id: string;
  project_name: string;
  recipient_email?: string;
  slack_webhook_url?: string;
  teams_webhook_url?: string;
  payload?: Record<string, unknown>;
}

export default async function notifyRoutes(app: FastifyInstance): Promise<void> {
  // GET /health
  app.get("/health", async (_request: FastifyRequest, reply: FastifyReply) => {
    return reply.send({ status: "ok", service: "notification-service", version: "0.1.0" });
  });

  /**
   * POST /api/v1/notify/send
   *
   * Synchronous dispatch endpoint — used by other services and for testing.
   * Returns 204 on success; channels that fail are logged but do not affect the response.
   */
  app.post<{ Body: SendBody }>(
    "/api/v1/notify/send",
    {
      schema: {
        body: {
          type: "object",
          required: ["event_type", "project_id", "project_name"],
          properties: {
            event_type: { type: "string" },
            project_id: { type: "string", minLength: 1 },
            project_name: { type: "string", minLength: 1 },
            recipient_email: { type: "string" },
            slack_webhook_url: { type: "string" },
            teams_webhook_url: { type: "string" },
            payload: { type: "object" },
          },
        },
      },
    },
    async (request: FastifyRequest<{ Body: SendBody }>, reply: FastifyReply) => {
      const body = request.body;

      if (!VALID_EVENT_TYPES.has(body.event_type as EventType)) {
        const problem: ProblemDetail = {
          type: "https://mockingbird.internal/errors/invalid-event-type",
          title: "Invalid Event Type",
          status: 400,
          detail: `event_type must be one of: ${[...VALID_EVENT_TYPES].join(", ")}`,
        };
        return reply.status(400).send(problem);
      }

      const event: NotificationEvent = {
        event_type: body.event_type as EventType,
        project_id: body.project_id,
        project_name: body.project_name,
        recipient_email: body.recipient_email,
        slack_webhook_url: body.slack_webhook_url,
        teams_webhook_url: body.teams_webhook_url,
        payload: body.payload ?? {},
      };

      await dispatch(event);
      return reply.status(204).send();
    },
  );
}
