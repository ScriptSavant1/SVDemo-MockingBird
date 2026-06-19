/** Shared TypeScript types for notification-service. */

export type EventType =
  | "stub.deployed"
  | "deploy.failed"
  | "report.ready"
  | "stub.suspended";

/** Canonical event payload sent to POST /api/v1/notify/send or via SQS. */
export interface NotificationEvent {
  event_type: EventType;
  project_id: string;
  project_name: string;
  /** Email address to deliver to — omit to skip email. */
  recipient_email?: string;
  /** Slack incoming webhook URL — omit to skip Slack. */
  slack_webhook_url?: string;
  /** MS Teams incoming webhook URL — omit to skip Teams. */
  teams_webhook_url?: string;
  /** Event-specific data (stub_url, api_key, error, format, report_url, etc.) */
  payload: Record<string, unknown>;
}

/** Rendered message content for all three channels. */
export interface FormattedMessage {
  subject: string;
  html: string;
  slack_text: string;
  teams_title: string;
  teams_body: string;
}

/** SMTP configuration read from environment variables. */
export interface EmailConfig {
  host: string;
  port: number;
  secure: boolean;
  from: string;
}

/** EventBridge event envelope as forwarded to SQS by an EventBridge rule. */
export interface EventBridgeEnvelope {
  source: string;
  "detail-type": string;
  detail: Record<string, unknown>;
}

/** RFC 7807 Problem JSON */
export interface ProblemDetail {
  type: string;
  title: string;
  status: number;
  detail: string;
}

/** Map EventBridge detail-type → internal EventType. */
export const DETAIL_TYPE_MAP: Record<string, EventType> = {
  "Stub.Deployed": "stub.deployed",
  "Deploy.Failed": "deploy.failed",
  "Report.Ready": "report.ready",
  "Stub.Suspended": "stub.suspended",
};
