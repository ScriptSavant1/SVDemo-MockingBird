/**
 * Send a MessageCard to MS Teams via incoming webhook.
 * Uses the legacy Office 365 Connector card format (universally supported).
 * Throws if the webhook returns a non-2xx response.
 */
export async function sendTeams(
  webhookUrl: string,
  title: string,
  body: string,
): Promise<void> {
  const card = {
    "@type": "MessageCard",
    "@context": "http://schema.org/extensions",
    themeColor: "0076D7",
    summary: title,
    sections: [{ activityTitle: `**${title}**`, activityText: body }],
  };
  const res = await fetch(webhookUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(card),
  });
  if (!res.ok) {
    throw new Error(`Teams webhook returned ${res.status}`);
  }
}
