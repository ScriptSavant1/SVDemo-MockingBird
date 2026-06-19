import { useEffect, useRef } from "react";
import type { MetricHistoryPoint } from "@/api/types";
import { formatTps } from "@/utils/formatters";

interface MetricsHistoryChartProps {
  points: MetricHistoryPoint[];
  height?: number;
}

interface EChartsInstance {
  setOption: (option: unknown) => void;
  dispose: () => void;
}

export function MetricsHistoryChart({ points, height = 300 }: MetricsHistoryChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<EChartsInstance | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    import("echarts").then((ec) => {
      chartRef.current = ec.init(containerRef.current!, null, { renderer: "canvas" });
    }).catch(() => undefined);
    return () => {
      chartRef.current?.dispose();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!chartRef.current || points.length === 0) return;

    const times = points.map((p) =>
      new Date(p.time).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" }),
    );

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
          data: points.map((p) => p.tps),
          smooth: true,
          yAxisIndex: 0,
          lineStyle: { color: "#003875", width: 2 },
          areaStyle: { color: "rgba(0,56,117,0.1)" },
        },
        {
          name: "Avg Latency (ms)",
          type: "line",
          data: points.map((p) => p.latency_avg_ms),
          smooth: true,
          yAxisIndex: 1,
          lineStyle: { color: "#00A9E0", width: 2 },
        },
      ],
    });
  }, [points]);

  return (
    <div
      ref={containerRef}
      style={{ width: "100%", height }}
      data-testid="metrics-history-chart"
      aria-label="Historical metrics chart"
    />
  );
}
