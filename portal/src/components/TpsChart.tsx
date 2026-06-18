import { useEffect, useRef } from "react";
import type { MetricSnapshot } from "@/api/types";
import { formatTps } from "@/utils/formatters";

interface TpsChartProps {
  snapshots: MetricSnapshot[];
  height?: number;
}

interface EChartsInstance {
  setOption: (option: unknown) => void;
  dispose: () => void;
  resize: () => void;
}

interface EChartsStatic {
  init: (el: HTMLElement, theme: null, opts: { renderer: string }) => EChartsInstance;
}

declare global {
  interface Window {
    echarts?: EChartsStatic;
  }
}

export function TpsChart({ snapshots, height = 300 }: TpsChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<EChartsInstance | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    import("echarts").then((ec) => {
      chartRef.current = ec.init(containerRef.current!, null, { renderer: "canvas" });
      return () => chartRef.current?.dispose();
    }).catch(() => undefined);

    return () => {
      chartRef.current?.dispose();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!chartRef.current || snapshots.length === 0) return;

    const times = snapshots.map((s) =>
      new Date(s.timestamp).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
    );
    const tpsValues = snapshots.map((s) => s.tps);
    const latencyValues = snapshots.map((s) => s.avg_latency_ms);

    chartRef.current.setOption({
      grid: { left: 60, right: 60, top: 20, bottom: 40 },
      tooltip: { trigger: "axis" },
      legend: { data: ["TPS", "Avg Latency (ms)"], bottom: 0 },
      xAxis: { type: "category", data: times, axisLabel: { rotate: 30 } },
      yAxis: [
        { type: "value", name: "TPS", axisLabel: { formatter: (v: number) => formatTps(v) } },
        { type: "value", name: "Latency (ms)", position: "right" },
      ],
      series: [
        {
          name: "TPS",
          type: "line",
          data: tpsValues,
          smooth: true,
          yAxisIndex: 0,
          lineStyle: { color: "#003875", width: 2 },
          areaStyle: { color: "rgba(0,56,117,0.1)" },
        },
        {
          name: "Avg Latency (ms)",
          type: "line",
          data: latencyValues,
          smooth: true,
          yAxisIndex: 1,
          lineStyle: { color: "#00A9E0", width: 2 },
        },
      ],
    });
  }, [snapshots]);

  return (
    <div
      ref={containerRef}
      style={{ width: "100%", height }}
      data-testid="tps-chart"
      aria-label="Live TPS chart"
    />
  );
}
