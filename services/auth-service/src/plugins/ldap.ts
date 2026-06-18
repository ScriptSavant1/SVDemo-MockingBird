/**
 * LDAP authentication plugin (Phase 2 / Sprint 12).
 *
 * Registers app.ldap when LDAP_SERVER env var is present.
 * If the variable is absent the plugin is a no-op and LDAP login returns 503.
 *
 * Credentials for the LDAP service account come from HashiCorp Vault in
 * production (injected as env vars by ECS task definition) — NEVER hardcoded.
 */
import fp from "fastify-plugin";
import { Client } from "ldapts";
import type { FastifyInstance } from "fastify";
import type { UserRole } from "../types/index.js";

export interface LdapLookupResult {
  dn: string;
  email: string;
  role: UserRole;
}

export interface LdapClient {
  lookupAndVerify(username: string, password: string): Promise<LdapLookupResult>;
}

declare module "fastify" {
  interface FastifyInstance {
    ldap?: LdapClient;
  }
}

/** Map a list of LDAP memberOf DNs to a Mockingbird role. */
function mapGroupsToRole(memberOf: string[], svTeamGroup: string, svUsersGroup: string): UserRole {
  const lower = memberOf.map((g) => g.toLowerCase());
  if (lower.some((g) => g.includes(svTeamGroup.toLowerCase()))) return "ADMIN";
  if (lower.some((g) => g.includes(svUsersGroup.toLowerCase()))) return "SV_TEAM";
  return "VIEWER";
}

export default fp(async function ldapPlugin(app: FastifyInstance) {
  const url = process.env["LDAP_SERVER"];
  if (!url) {
    app.log.info("LDAP_SERVER not set — LDAP authentication disabled");
    return;
  }

  const baseDn = process.env["LDAP_BASE_DN"] ?? "";
  const bindDn = process.env["LDAP_BIND_DN"] ?? "";
  const bindPassword = process.env["LDAP_BIND_PASSWORD"] ?? "";
  const svTeamGroup = process.env["LDAP_SV_TEAM_GROUP"] ?? "CN=SV-Team";
  const svUsersGroup = process.env["LDAP_SV_USERS_GROUP"] ?? "CN=SV-Users";

  const ldapClient: LdapClient = {
    async lookupAndVerify(username: string, password: string): Promise<LdapLookupResult> {
      const client = new Client({ url });
      try {
        // Step 1: bind as service account to search for the user
        await client.bind(bindDn, bindPassword);
        const { searchEntries } = await client.search(baseDn, {
          filter: `(sAMAccountName=${username})`,
          attributes: ["dn", "mail", "memberOf"],
        });

        if (searchEntries.length === 0) {
          throw new Error("LDAP_USER_NOT_FOUND");
        }

        const entry = searchEntries[0]!;
        const userDn = entry.dn;
        const rawEmail = entry["mail"];
        let email: string;
        if (Array.isArray(rawEmail) && rawEmail.length > 0) {
          email = String(rawEmail[0]);
        } else if (rawEmail != null) {
          email = String(rawEmail);
        } else {
          email = `${username}@company.com`;
        }

        const rawGroups = entry["memberOf"];
        const memberOf: string[] = Array.isArray(rawGroups)
          ? rawGroups.map(String)
          : rawGroups != null ? [String(rawGroups)] : [];

        // Step 2: bind as the user to verify their password
        await client.bind(userDn, password);

        return {
          dn: userDn,
          email,
          role: mapGroupsToRole(memberOf, svTeamGroup, svUsersGroup),
        };
      } finally {
        await client.unbind().catch(() => undefined);
      }
    },
  };

  app.decorate("ldap", ldapClient);
  app.log.info("LDAP plugin registered (%s)", url);
});
