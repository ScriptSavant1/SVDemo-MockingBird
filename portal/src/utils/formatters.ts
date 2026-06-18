export function formatTps(tps: number): string {
  return new Intl.NumberFormat("en-GB", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 1,
  }).format(tps);
}

export function formatLatency(ms: number): string {
  return `${ms.toFixed(2)}ms`;
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleString("en-GB", {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "UTC",
    timeZoneName: "short",
  });
}

export function formatErrorRate(rate: number): string {
  return `${(rate * 100).toFixed(2)}%`;
}

export function formatRequests(count: number): string {
  return new Intl.NumberFormat("en-GB").format(count);
}
