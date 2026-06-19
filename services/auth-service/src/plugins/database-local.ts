/**
 * Local development database plugin — SQLite via better-sqlite3.
 *
 * Used when DATABASE_URL is not set (i.e. no PostgreSQL available).
 * Exposes the same app.pg.query() interface that all routes expect,
 * so no route code needs to change.
 *
 * NOT for production. Production always uses PostgreSQL via database.ts.
 */
import fp from "fastify-plugin";
import Database from "better-sqlite3";
import type { FastifyInstance } from "fastify";
import path from "path";

/** Converts PostgreSQL $1 $2 placeholders → SQLite ? placeholders. */
function pgToSqlite(sql: string): string {
  return sql.replace(/\$\d+/g, "?");
}

/** SQLite stores booleans as 0/1 — coerce back to JS booleans. */
function coerceRow(row: Record<string, unknown>): void {
  if ("is_active" in row) row["is_active"] = row["is_active"] !== 0;
}

export default fp(async function localDatabasePlugin(app: FastifyInstance) {
  const dbPath = process.env["LOCAL_DB_PATH"] ?? path.join(process.cwd(), "auth-local.db");
  const db = new Database(dbPath);
  db.pragma("journal_mode = WAL");

  // Create users table with SQLite-compatible UUID generation.
  db.exec(`
    CREATE TABLE IF NOT EXISTS users (
      id           TEXT NOT NULL PRIMARY KEY DEFAULT (
        lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) ||
        '-4' || substr(lower(hex(randomblob(2))), 2) || '-' ||
        substr('89ab', abs(random()) % 4 + 1, 1) ||
        substr(lower(hex(randomblob(2))), 2) || '-' || lower(hex(randomblob(6)))
      ),
      username      TEXT NOT NULL UNIQUE,
      email         TEXT NOT NULL UNIQUE,
      password_hash TEXT NOT NULL,
      role          TEXT NOT NULL DEFAULT 'VIEWER',
      is_active     INTEGER NOT NULL DEFAULT 1,
      created_at    TEXT NOT NULL DEFAULT (datetime('now'))
    );
  `);

  // Provide a pg-compatible .query() so all existing routes work unchanged.
  // Only .query(sql, params?) is used in auth/users routes — no pooling or streaming.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (app as any).pg = {
    query<T = Record<string, unknown>>(
      sql: string,
      params: unknown[] = [],
    ): Promise<{ rows: T[]; rowCount: number }> {
      const sqlite = pgToSqlite(sql).trim();
      const upper = sqlite.toUpperCase();

      if (upper.startsWith("SELECT") || upper.startsWith("WITH")) {
        const rows = db.prepare(sqlite).all(...params) as Record<string, unknown>[];
        rows.forEach(coerceRow);
        return Promise.resolve({ rows: rows as T[], rowCount: rows.length });
      }

      if (upper.includes("RETURNING")) {
        const row = db.prepare(sqlite).get(...params) as Record<string, unknown> | undefined;
        if (row) coerceRow(row);
        const rows: T[] = row ? [row as T] : [];
        return Promise.resolve({ rows, rowCount: rows.length });
      }

      const info = db.prepare(sqlite).run(...params);
      return Promise.resolve({ rows: [], rowCount: info.changes });
    },
  };

  app.log.info(`Local SQLite database: ${dbPath}`);
});
