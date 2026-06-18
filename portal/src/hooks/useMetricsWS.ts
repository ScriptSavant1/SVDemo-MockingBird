import { useEffect, useRef, useState } from "react";
import type { MetricSnapshot } from "@/api/types";

interface UseMetricsWSResult {
  latest: MetricSnapshot | null;
  connected: boolean;
  history: MetricSnapshot[];
}

const MAX_HISTORY = 60;

export function useMetricsWS(deploymentId: string | null): UseMetricsWSResult {
  const [latest, setLatest] = useState<MetricSnapshot | null>(null);
  const [connected, setConnected] = useState(false);
  const [history, setHistory] = useState<MetricSnapshot[]>([]);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!deploymentId) return;

    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const url = `${proto}//${window.location.host}/ws/metrics/${deploymentId}`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);

    ws.onmessage = (event: MessageEvent) => {
      try {
        const snapshot = JSON.parse(event.data as string) as MetricSnapshot;
        setLatest(snapshot);
        setHistory((prev) => {
          const next = [...prev, snapshot];
          return next.length > MAX_HISTORY ? next.slice(next.length - MAX_HISTORY) : next;
        });
      } catch {
        // malformed message
      }
    };

    ws.onclose = () => {
      setConnected(false);
      wsRef.current = null;
    };

    ws.onerror = () => setConnected(false);

    return () => {
      ws.close();
    };
  }, [deploymentId]);

  return { latest, connected, history };
}
