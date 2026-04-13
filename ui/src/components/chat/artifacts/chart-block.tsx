"use client";

import { useState, useEffect } from "react";

interface ChartSpec {
  type: "line" | "bar" | "scatter";
  title?: string;
  x: string;
  y: string[];
  data: Record<string, unknown>[];
}

const COLORS = [
  "var(--color-accent)",
  "#e45858",
  "#50b87a",
  "#f5a623",
  "#8b5cf6",
  "#ec4899",
];

interface ChartBlockProps {
  code: string;
}

function parseSpec(code: string): ChartSpec | null {
  try {
    const parsed = JSON.parse(code);
    if (!parsed.type || !parsed.x || !parsed.y || !parsed.data) return null;
    if (!Array.isArray(parsed.y)) parsed.y = [parsed.y];
    if (!Array.isArray(parsed.data)) return null;
    return parsed as ChartSpec;
  } catch {
    return null;
  }
}

export function ChartBlock({ code }: ChartBlockProps) {
  const [Chart, setChart] = useState<typeof import("recharts") | null>(null);
  const spec = parseSpec(code);

  useEffect(() => {
    import("recharts").then(setChart);
  }, []);

  if (!spec) {
    return (
      <pre className="my-1 px-3 py-2 rounded-md bg-[var(--color-layer-2)] overflow-x-auto text-[12px] text-red-500 font-[family-name:var(--font-ibm-plex-mono)] whitespace-pre">
        Invalid chart spec{"\n"}{code}
      </pre>
    );
  }

  if (!Chart) {
    return (
      <div className="my-1 p-3 rounded-md bg-[var(--color-layer-2)] h-[250px] flex items-center justify-center text-[12px] text-[var(--color-text-tertiary)]">
        Loading chart...
      </div>
    );
  }

  const { ResponsiveContainer, LineChart, BarChart, ScatterChart, Line, Bar, Scatter,
    XAxis, YAxis, CartesianGrid, Tooltip, Legend } = Chart;

  const commonProps = {
    data: spec.data,
    margin: { top: 5, right: 20, bottom: 5, left: 0 },
  };

  const axes = (
    <>
      <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
      <XAxis dataKey={spec.x} tick={{ fontSize: 11 }} stroke="var(--color-text-tertiary)" />
      <YAxis tick={{ fontSize: 11 }} stroke="var(--color-text-tertiary)" />
      <Tooltip
        contentStyle={{
          background: "var(--color-surface)",
          border: "1px solid var(--color-border)",
          borderRadius: 4,
          fontSize: 12,
        }}
      />
      {spec.y.length > 1 && <Legend wrapperStyle={{ fontSize: 12 }} />}
    </>
  );

  let chart: React.ReactNode;
  if (spec.type === "bar") {
    chart = (
      <BarChart {...commonProps}>
        {axes}
        {spec.y.map((key, i) => (
          <Bar key={key} dataKey={key} fill={COLORS[i % COLORS.length]} />
        ))}
      </BarChart>
    );
  } else if (spec.type === "scatter") {
    chart = (
      <ScatterChart {...commonProps}>
        {axes}
        {spec.y.map((key, i) => (
          <Scatter key={key} dataKey={key} fill={COLORS[i % COLORS.length]} name={key} />
        ))}
      </ScatterChart>
    );
  } else {
    chart = (
      <LineChart {...commonProps}>
        {axes}
        {spec.y.map((key, i) => (
          <Line key={key} type="monotone" dataKey={key} stroke={COLORS[i % COLORS.length]} dot={false} strokeWidth={2} />
        ))}
      </LineChart>
    );
  }

  return (
    <div className="my-1 p-3 rounded-md bg-[var(--color-layer-2)]">
      {spec.title && (
        <div className="text-[12px] font-semibold text-[var(--color-text)] mb-2">{spec.title}</div>
      )}
      <ResponsiveContainer width="100%" height={250}>
        {chart}
      </ResponsiveContainer>
    </div>
  );
}
