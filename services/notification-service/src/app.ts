import Fastify, { FastifyInstance } from "fastify";
import sqsPlugin from "./plugins/sqs.js";
import notifyRoutes from "./routes/notify.js";

export async function buildApp(opts: { logger?: boolean; disableSqs?: boolean } = {}): Promise<FastifyInstance> {
  const app = Fastify({ logger: opts.logger ?? true });

  // SQS consumer — disabled in tests via disableSqs flag
  if (!opts.disableSqs) {
    await app.register(sqsPlugin);
  }

  await app.register(notifyRoutes);

  return app;
}
