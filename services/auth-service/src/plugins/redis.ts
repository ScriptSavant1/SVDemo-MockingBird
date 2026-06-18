/**
 * Redis session cache plugin (Sprint 12).
 *
 * Registers app.redis when REDIS_URL env var is present.
 * Used for JWT session invalidation (forced logout) and caching.
 *
 * If REDIS_URL is absent the plugin is a no-op — authentication falls back
 * to JWT signature-only verification (no forced logout capability).
 */
import fp from "fastify-plugin";
import Redis from "ioredis";
import type { FastifyInstance } from "fastify";

declare module "fastify" {
  interface FastifyInstance {
    redis?: Redis;
  }
}

export default fp(async function redisPlugin(app: FastifyInstance) {
  const redisUrl = process.env["REDIS_URL"];
  if (!redisUrl) {
    app.log.info("REDIS_URL not set — Redis session cache disabled");
    return;
  }

  const client = new Redis(redisUrl, { lazyConnect: true });

  client.on("error", (err: Error) => {
    app.log.error({ err }, "Redis connection error");
  });

  await client.connect();

  app.decorate("redis", client);

  app.addHook("onClose", async () => {
    await client.quit();
  });

  app.log.info("Redis plugin registered (%s)", redisUrl);
});
