/**
 * Sprint 21 — notification-service tests.
 *
 * Uses Fastify inject() — no HTTP server needed.
 * Channel functions (email/slack/teams) are mocked so no real network calls are made.
 */
import Fastify from "fastify";
import notifyRoutes from "../src/routes/notify";
import { formatMessage, dispatch, handleSqsMessage } from "../src/handlers/events";
import type { NotificationEvent } from "../src/types/index";

// ── mock channels ──────────────────────────────────────────────────────────────

jest.mock("../src/channels/email", () => ({
  sendEmail: jest.fn().mockResolvedValue(undefined),
  emailConfigFromEnv: jest.fn().mockReturnValue({
    host: "smtp.company.internal",
    port: 587,
    secure: false,
    from: "mockingbird@company.internal",
  }),
}));

jest.mock("../src/channels/slack", () => ({
  sendSlack: jest.fn().mockResolvedValue(undefined),
}));

jest.mock("../src/channels/teams", () => ({
  sendTeams: jest.fn().mockResolvedValue(undefined),
}));

import { sendEmail } from "../src/channels/email";
import { sendSlack } from "../src/channels/slack";
import { sendTeams } from "../src/channels/teams";

// ── helpers ────────────────────────────────────────────────────────────────────

async function buildTestApp() {
  const app = Fastify({ logger: false });
  await app.register(notifyRoutes);
  return app;
}

function makeEvent(overrides: Partial<NotificationEvent> = {}): NotificationEvent {
  return {
    event_type: "stub.deployed",
    project_id: "proj-1",
    project_name: "payments-stub",
    recipient_email: "owner@company.com",
    slack_webhook_url: "https://hooks.slack.com/test",
    teams_webhook_url: "https://outlook.office.com/test",
    payload: { stub_url: "https://10.0.0.1:8080", api_key: "mk_abc" },
    ...overrides,
  };
}

beforeEach(() => {
  jest.clearAllMocks();
});

// ── health ─────────────────────────────────────────────────────────────────────

describe("GET /health", () => {
  it("returns 200 with service name", async () => {
    const app = await buildTestApp();
    const res = await app.inject({ method: "GET", url: "/health" });
    expect(res.statusCode).toBe(200);
    expect(res.json()).toMatchObject({ status: "ok", service: "notification-service" });
  });
});

// ── POST /api/v1/notify/send ───────────────────────────────────────────────────

describe("POST /api/v1/notify/send", () => {
  it("returns 204 for stub.deployed", async () => {
    const app = await buildTestApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/v1/notify/send",
      payload: {
        event_type: "stub.deployed",
        project_id: "proj-1",
        project_name: "payments-stub",
        slack_webhook_url: "https://hooks.slack.com/test",
        payload: { stub_url: "https://10.0.0.1:8080", api_key: "mk_abc" },
      },
    });
    expect(res.statusCode).toBe(204);
    expect(sendSlack).toHaveBeenCalledTimes(1);
  });

  it("returns 204 for deploy.failed and calls Slack", async () => {
    const app = await buildTestApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/v1/notify/send",
      payload: {
        event_type: "deploy.failed",
        project_id: "proj-2",
        project_name: "accounts-stub",
        slack_webhook_url: "https://hooks.slack.com/test",
        payload: { error: "Terraform apply failed: timeout" },
      },
    });
    expect(res.statusCode).toBe(204);
    const slackCall = (sendSlack as jest.Mock).mock.calls[0] as [string, string];
    expect(slackCall[1]).toContain("Deploy failed");
    expect(slackCall[1]).toContain("accounts-stub");
  });

  it("returns 204 for report.ready and calls Teams", async () => {
    const app = await buildTestApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/v1/notify/send",
      payload: {
        event_type: "report.ready",
        project_id: "proj-3",
        project_name: "payments-stub",
        teams_webhook_url: "https://outlook.office.com/test",
        payload: { format: "pdf", report_url: "https://s3.amazonaws.com/report.pdf" },
      },
    });
    expect(res.statusCode).toBe(204);
    expect(sendTeams).toHaveBeenCalledTimes(1);
    const teamsCall = (sendTeams as jest.Mock).mock.calls[0] as [string, string, string];
    expect(teamsCall[1]).toBe("Report Ready");
  });

  it("returns 204 for stub.suspended", async () => {
    const app = await buildTestApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/v1/notify/send",
      payload: {
        event_type: "stub.suspended",
        project_id: "proj-4",
        project_name: "accounts-stub",
        recipient_email: "owner@company.com",
        slack_webhook_url: "https://hooks.slack.com/test",
        teams_webhook_url: "https://outlook.office.com/test",
        payload: {},
      },
    });
    expect(res.statusCode).toBe(204);
    expect(sendEmail).toHaveBeenCalledTimes(1);
    expect(sendSlack).toHaveBeenCalledTimes(1);
    expect(sendTeams).toHaveBeenCalledTimes(1);
  });

  it("returns 400 for unknown event_type", async () => {
    const app = await buildTestApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/v1/notify/send",
      payload: {
        event_type: "unknown.event",
        project_id: "proj-1",
        project_name: "test",
      },
    });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toMatchObject({ status: 400, title: "Invalid Event Type" });
  });

  it("returns 400 for missing required fields", async () => {
    const app = await buildTestApp();
    const res = await app.inject({
      method: "POST",
      url: "/api/v1/notify/send",
      payload: { event_type: "stub.deployed" },
    });
    expect(res.statusCode).toBe(400);
  });
});

// ── formatMessage ──────────────────────────────────────────────────────────────

describe("formatMessage()", () => {
  it("stub.deployed: subject contains project name", () => {
    const msg = formatMessage(makeEvent({ event_type: "stub.deployed" }));
    expect(msg.subject).toContain("payments-stub");
    expect(msg.subject).toContain("deployed");
  });

  it("stub.deployed: slack_text contains stub URL", () => {
    const msg = formatMessage(makeEvent({
      event_type: "stub.deployed",
      payload: { stub_url: "https://10.1.2.3:8080", api_key: "mk_xyz" },
    }));
    expect(msg.slack_text).toContain("https://10.1.2.3:8080");
  });

  it("deploy.failed: subject contains 'failed'", () => {
    const msg = formatMessage(makeEvent({
      event_type: "deploy.failed",
      payload: { error: "EC2 quota exceeded" },
    }));
    expect(msg.subject).toContain("failed");
    expect(msg.html).toContain("EC2 quota exceeded");
  });

  it("report.ready: subject includes format", () => {
    const msg = formatMessage(makeEvent({
      event_type: "report.ready",
      payload: { format: "excel", report_url: "https://s3.example.com/r.xlsx" },
    }));
    expect(msg.subject).toContain("EXCEL");
    expect(msg.teams_body).toContain("Download");
  });

  it("stub.suspended: slack_text mentions 'suspended'", () => {
    const msg = formatMessage(makeEvent({ event_type: "stub.suspended", payload: {} }));
    expect(msg.slack_text).toContain("suspended");
  });
});

// ── dispatch() graceful degradation ───────────────────────────────────────────

describe("dispatch() — channel skipping", () => {
  it("skips email when recipient_email is not provided", async () => {
    await dispatch(makeEvent({ recipient_email: undefined }));
    expect(sendEmail).not.toHaveBeenCalled();
    expect(sendSlack).toHaveBeenCalledTimes(1);
  });

  it("skips Slack when slack_webhook_url is not provided", async () => {
    await dispatch(makeEvent({ slack_webhook_url: undefined }));
    expect(sendSlack).not.toHaveBeenCalled();
    expect(sendEmail).toHaveBeenCalledTimes(1);
  });

  it("skips Teams when teams_webhook_url is not provided", async () => {
    await dispatch(makeEvent({ teams_webhook_url: undefined }));
    expect(sendTeams).not.toHaveBeenCalled();
  });

  it("does not throw when a channel errors", async () => {
    (sendSlack as jest.Mock).mockRejectedValueOnce(new Error("Slack is down"));
    await expect(dispatch(makeEvent())).resolves.toBeUndefined();
  });
});

// ── handleSqsMessage() ─────────────────────────────────────────────────────────

describe("handleSqsMessage()", () => {
  it("processes Stub.Deployed EventBridge event", async () => {
    const envelope = {
      source: "mockingbird.deployer-worker",
      "detail-type": "Stub.Deployed",
      detail: {
        project_id: "proj-1",
        project_name: "payments-stub",
        slack_webhook_url: "https://hooks.slack.com/test",
        stub_url: "https://10.0.0.1:8080",
        api_key: "mk_abc",
      },
    };
    await handleSqsMessage(JSON.stringify(envelope));
    expect(sendSlack).toHaveBeenCalledTimes(1);
    const slackCall = (sendSlack as jest.Mock).mock.calls[0] as [string, string];
    expect(slackCall[1]).toContain("payments-stub");
  });

  it("processes Deploy.Failed EventBridge event", async () => {
    const envelope = {
      source: "mockingbird.deployer-worker",
      "detail-type": "Deploy.Failed",
      detail: {
        project_id: "proj-2",
        project_name: "accounts-stub",
        recipient_email: "owner@company.com",
        error: "Terraform timeout",
      },
    };
    await handleSqsMessage(JSON.stringify(envelope));
    expect(sendEmail).toHaveBeenCalledTimes(1);
    const emailCall = (sendEmail as jest.Mock).mock.calls[0] as [unknown, string, string, string];
    expect(emailCall[2]).toContain("failed");
  });

  it("silently skips unknown detail-type", async () => {
    const envelope = {
      source: "mockingbird.unknown-service",
      "detail-type": "Some.UnknownEvent",
      detail: {},
    };
    await expect(handleSqsMessage(JSON.stringify(envelope))).resolves.toBeUndefined();
    expect(sendSlack).not.toHaveBeenCalled();
    expect(sendEmail).not.toHaveBeenCalled();
  });

  it("silently skips malformed JSON body", async () => {
    await expect(handleSqsMessage("not valid json {{")).resolves.toBeUndefined();
  });
});
