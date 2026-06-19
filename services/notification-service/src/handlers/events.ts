import { sendEmail, emailConfigFromEnv } from "../channels/email.js";
import { sendSlack } from "../channels/slack.js";
import { sendTeams } from "../channels/teams.js";
import type {
  EventBridgeEnvelope,
  EventType,
  FormattedMessage,
  NotificationEvent,
} from "../types/index.js";
import { DETAIL_TYPE_MAP } from "../types/index.js";

/** Build human-readable message content for each event type. */
export function formatMessage(event: NotificationEvent): FormattedMessage {
  const name = event.project_name;

  switch (event.event_type) {
    case "stub.deployed": {
      const url = String(event.payload["stub_url"] ?? "N/A");
      const key = String(event.payload["api_key"] ?? "N/A");
      return {
        subject: `[Mockingbird] Stub deployed: ${name}`,
        html: `<p>Your stub <strong>${name}</strong> is now live.</p><p>URL: <a href="${url}">${url}</a><br>API Key: <code>${key}</code></p>`,
        slack_text: `:white_check_mark: *${name}* stub is live — ${url}`,
        teams_title: "Stub Deployed",
        teams_body: `**${name}** is live at ${url} (API Key: ${key})`,
      };
    }

    case "deploy.failed": {
      const error = String(event.payload["error"] ?? "Unknown error");
      return {
        subject: `[Mockingbird] Deploy failed: ${name}`,
        html: `<p>Deployment of <strong>${name}</strong> failed.</p><p>Error: ${error}</p>`,
        slack_text: `:x: Deploy failed for *${name}*: ${error}`,
        teams_title: "Deploy Failed",
        teams_body: `Deployment of **${name}** failed: ${error}`,
      };
    }

    case "report.ready": {
      const format = String(event.payload["format"] ?? "report");
      const reportUrl = String(event.payload["report_url"] ?? "");
      return {
        subject: `[Mockingbird] Report ready: ${name} (${format.toUpperCase()})`,
        html: `<p>Your <strong>${format.toUpperCase()}</strong> report for <strong>${name}</strong> is ready.</p>${reportUrl ? `<p><a href="${reportUrl}">Download report</a></p>` : ""}`,
        slack_text: `:page_facing_up: *${name}* ${format.toUpperCase()} report is ready${reportUrl ? ` — ${reportUrl}` : ""}`,
        teams_title: "Report Ready",
        teams_body: `**${name}** ${format.toUpperCase()} report is ready.${reportUrl ? ` [Download](${reportUrl})` : ""}`,
      };
    }

    case "stub.suspended": {
      return {
        subject: `[Mockingbird] Stub suspended: ${name}`,
        html: `<p>Stub <strong>${name}</strong> has been suspended. The EC2 instance has been terminated to save costs.</p><p>You can redeploy it at any time — no re-upload needed.</p>`,
        slack_text: `:zzz: *${name}* stub has been suspended (EC2 terminated).`,
        teams_title: "Stub Suspended",
        teams_body: `Stub **${name}** has been suspended. EC2 terminated. Redeploy any time in ~4 minutes.`,
      };
    }
  }
}

/**
 * Dispatch a notification event to all configured channels.
 * Each channel is fire-and-forget: errors are logged but do not fail the dispatch.
 */
export async function dispatch(event: NotificationEvent): Promise<void> {
  const msg = formatMessage(event);
  const tasks: Promise<void>[] = [];
  const log = (channel: string, err: unknown) =>
    console.error(`[notification] ${channel} delivery failed:`, err);

  if (event.recipient_email) {
    const emailConfig = emailConfigFromEnv();
    if (emailConfig) {
      tasks.push(
        sendEmail(emailConfig, event.recipient_email, msg.subject, msg.html).catch((err) =>
          log("email", err),
        ),
      );
    }
  }

  if (event.slack_webhook_url) {
    tasks.push(
      sendSlack(event.slack_webhook_url, msg.slack_text).catch((err) => log("slack", err)),
    );
  }

  if (event.teams_webhook_url) {
    tasks.push(
      sendTeams(event.teams_webhook_url, msg.teams_title, msg.teams_body).catch((err) =>
        log("teams", err),
      ),
    );
  }

  await Promise.all(tasks);
}

/**
 * Process a raw SQS message body (an EventBridge event JSON string).
 * Silently skips unknown detail-types — acknowledgement is always safe.
 */
export async function handleSqsMessage(body: string): Promise<void> {
  let envelope: EventBridgeEnvelope;
  try {
    envelope = JSON.parse(body) as EventBridgeEnvelope;
  } catch {
    console.error("[notification] Malformed SQS message body, skipping");
    return;
  }

  const detailType = envelope["detail-type"];
  const eventType: EventType | undefined = DETAIL_TYPE_MAP[detailType];
  if (!eventType) {
    console.warn(`[notification] Unknown detail-type '${detailType}', skipping`);
    return;
  }

  const detail = envelope.detail;
  const event: NotificationEvent = {
    event_type: eventType,
    project_id: String(detail["project_id"] ?? ""),
    project_name: String(detail["project_name"] ?? "Unknown Project"),
    recipient_email: detail["recipient_email"] ? String(detail["recipient_email"]) : undefined,
    slack_webhook_url: detail["slack_webhook_url"]
      ? String(detail["slack_webhook_url"])
      : undefined,
    teams_webhook_url: detail["teams_webhook_url"]
      ? String(detail["teams_webhook_url"])
      : undefined,
    payload: detail,
  };

  await dispatch(event);
}
