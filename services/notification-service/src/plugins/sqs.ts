import fp from "fastify-plugin";
import type { FastifyInstance } from "fastify";
import {
  SQSClient,
  ReceiveMessageCommand,
  DeleteMessageCommand,
} from "@aws-sdk/client-sqs";
import { handleSqsMessage } from "../handlers/events.js";

const POLL_INTERVAL_MS = 5_000;
const MAX_MESSAGES = 10;
const VISIBILITY_TIMEOUT = 60;

/**
 * Fastify plugin that polls the SQS notify-queue in a background loop.
 * No-op if NOTIFY_QUEUE_URL is not set (local dev without AWS).
 */
async function sqsPlugin(app: FastifyInstance): Promise<void> {
  const queueUrl = process.env["NOTIFY_QUEUE_URL"];
  if (!queueUrl) {
    app.log.warn("NOTIFY_QUEUE_URL not set — SQS consumer disabled");
    return;
  }

  const client = new SQSClient({ region: process.env["AWS_REGION"] ?? "eu-west-2" });
  let running = true;

  async function poll(): Promise<void> {
    while (running) {
      try {
        const result = await client.send(
          new ReceiveMessageCommand({
            QueueUrl: queueUrl,
            MaxNumberOfMessages: MAX_MESSAGES,
            WaitTimeSeconds: 20,
            VisibilityTimeout: VISIBILITY_TIMEOUT,
          }),
        );

        for (const msg of result.Messages ?? []) {
          if (!msg.Body) continue;
          try {
            await handleSqsMessage(msg.Body);
          } catch (err) {
            app.log.error({ err }, "Failed to handle SQS message");
          }
          if (msg.ReceiptHandle) {
            await client.send(
              new DeleteMessageCommand({ QueueUrl: queueUrl, ReceiptHandle: msg.ReceiptHandle }),
            );
          }
        }
      } catch (err) {
        app.log.error({ err }, "SQS poll error");
        await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
      }
    }
  }

  // Start polling in the background — don't await (fire-and-forget loop)
  poll().catch((err) => app.log.error({ err }, "SQS poll loop crashed"));

  app.addHook("onClose", async () => {
    running = false;
  });
}

export default fp(sqsPlugin, { name: "sqs" });
