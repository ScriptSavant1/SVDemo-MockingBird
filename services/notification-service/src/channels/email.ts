import nodemailer from "nodemailer";
import type { EmailConfig } from "../types/index.js";

/**
 * Send an HTML email via SMTP.
 * Throws if the SMTP transport returns an error.
 */
export async function sendEmail(
  config: EmailConfig,
  to: string,
  subject: string,
  html: string,
): Promise<void> {
  const transporter = nodemailer.createTransport({
    host: config.host,
    port: config.port,
    secure: config.secure,
  });
  await transporter.sendMail({ from: config.from, to, subject, html });
}

/** Build EmailConfig from environment variables. Returns undefined if SMTP_HOST is not set. */
export function emailConfigFromEnv(): EmailConfig | undefined {
  const host = process.env["SMTP_HOST"];
  if (!host) return undefined;
  return {
    host,
    port: parseInt(process.env["SMTP_PORT"] ?? "587", 10),
    secure: process.env["SMTP_SECURE"] === "true",
    from: process.env["SMTP_FROM"] ?? "mockingbird@company.internal",
  };
}
