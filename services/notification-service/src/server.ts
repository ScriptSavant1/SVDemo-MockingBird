import { buildApp } from "./app.js";

const HOST = process.env["HOST"] ?? "0.0.0.0";
const PORT = parseInt(process.env["PORT"] ?? "3002", 10);

async function start(): Promise<void> {
  const app = await buildApp({ logger: true });
  try {
    await app.listen({ host: HOST, port: PORT });
    console.log(`notification-service listening on ${HOST}:${PORT}`);
  } catch (err) {
    app.log.error(err);
    process.exit(1);
  }
}

start();
