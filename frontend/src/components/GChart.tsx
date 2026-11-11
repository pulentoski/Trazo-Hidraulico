// Gráfico de la página «Gestión»: eje X por categorías (meses, horas, materiales), barras (agrupadas o apiladas) y
// líneas, con línea de referencia opcional. SVG liviano, legible en tema claro y oscuro.
import type { GChartData } from "../api/types";
import { niceTicks } from "../lib/charts";
import { fmt } from "../lib/format";
import { PALETTE } from "./Chart";

const W = 560;

export function GChart({ chart, height = 190 }: { chart: GChartData; height?: number }) {
  const H = height;
  const m = { l: 46, r: 10, t: 10, b: 30 };
  const n = chart.x.length;
  const bars = chart.series.filter((s) => s.kind === "bar");
  const lines = chart.series.filter((s) => s.kind !== "bar");
  const stackTotals = chart.stacked ? chart.x.map((_, i) => bars.reduce((a, s) => a + Math.max(0, s.values[i] ?? 0), 0)) : [];
  const vals = [
    ...chart.series.flatMap((s) => s.values.filter((v): v is number => v !== null && v !== undefined && Number.isFinite(v))),
    ...stackTotals, ...(chart.reference != null ? [chart.reference] : []),
  ];
  if (!n || !vals.length) return <p className="muted small chart-empty">Sin datos para graficar en el período.</p>;
  let y0 = Math.min(0, ...vals);
  let y1 = Math.max(...vals);
  if (y0 === y1) y1 = y0 + 1;
  y1 += (y1 - y0) * 0.08;
  const ticks = niceTicks(y0, y1, 4);
  y0 = Math.min(y0, ticks[0]);
  y1 = Math.max(y1, ticks[ticks.length - 1]);
  const tickText = (t: number) => fmt(t, Math.abs(t) < 10 && t % 1 ? 1 : 0);
  m.l = Math.max(34, 8 + 6.2 * Math.max(...ticks.map((t) => tickText(t).length)));
  const bw = (W - m.l - m.r) / n;
  const sx = (i: number) => m.l + bw * (i + 0.5);
  const sy = (v: number) => H - m.b - ((v - y0) / (y1 - y0)) * (H - m.t - m.b);
  const every = Math.ceil(n / 12);
  const groupW = Math.max(2, bw * 0.72);
  const barW = chart.stacked || !bars.length ? groupW : groupW / bars.length;
  const color = (k: number) => PALETTE[k % PALETTE.length];
  const label = (x: string) => (x.length === 7 && /^\d{4}-\d{2}$/.test(x) ? `${x.slice(5)}/${x.slice(2, 4)}` : x.length > 9 ? `${x.slice(0, 8)}…` : x);
  return (
    <figure className="gchart">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${chart.title}${chart.unit ? ` (${chart.unit})` : ""}`}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={m.l} x2={W - m.r} y1={sy(t)} y2={sy(t)} className="grid" />
            <text x={m.l - 6} y={sy(t) + 3} textAnchor="end" className="tick">{tickText(t)}</text>
          </g>
        ))}
        {chart.x.map((x, i) => i % every === 0 && (
          <text key={`x${i}`} x={sx(i)} y={H - m.b + 14} textAnchor="middle" className="tick">{label(x)}</text>
        ))}
        {chart.x.map((_, i) => {
          let acc = 0;
          return bars.map((s, k) => {
            const v = s.values[i];
            if (v === null || v === undefined) return null;
            if (chart.stacked) {
              const a = sy(acc + Math.max(0, v));
              const b = sy(acc);
              acc += Math.max(0, v);
              return <rect key={`${i}-${k}`} x={sx(i) - groupW / 2} y={a} width={groupW} height={Math.max(0, b - a)} fill={color(k)}><title>{`${s.name} · ${chart.x[i]}: ${fmt(v, 2)} ${chart.unit}`}</title></rect>;
            }
            const top = sy(Math.max(0, v));
            const base = sy(Math.min(0, v));
            return <rect key={`${i}-${k}`} x={sx(i) - groupW / 2 + k * barW} y={top} width={Math.max(1, barW - 1)} height={Math.max(0, base - top)}
              fill={color(k)}><title>{`${s.name} · ${chart.x[i]}: ${fmt(v, 2)} ${chart.unit}`}</title></rect>;
          });
        })}
        {lines.map((s, k) => {
          let d = "";
          let pen = false;
          s.values.forEach((v, i) => {
            if (v === null || v === undefined) { pen = false; return; }
            d += `${pen ? "L" : "M"}${sx(i).toFixed(1)},${sy(v).toFixed(1)}`;
            pen = true;
          });
          const c = color(bars.length + k);
          return (
            <g key={s.name}>
              <path d={d} fill="none" stroke={c} strokeWidth={2} />
              {s.values.map((v, i) => v !== null && v !== undefined && n <= 31 && (
                <circle key={i} cx={sx(i)} cy={sy(v)} r={2.4} fill={c}><title>{`${s.name} · ${chart.x[i]}: ${fmt(v, 2)} ${chart.unit}`}</title></circle>
              ))}
            </g>
          );
        })}
        {chart.reference != null && (
          <g>
            <line x1={m.l} x2={W - m.r} y1={sy(chart.reference)} y2={sy(chart.reference)} className="ref" />
            <text x={W - m.r} y={sy(chart.reference) - 4} textAnchor="end" className="tick ref-label">{chart.reference_label ?? ""}</text>
          </g>
        )}
        <line x1={m.l} x2={W - m.r} y1={sy(0 > y0 ? 0 : y0)} y2={sy(0 > y0 ? 0 : y0)} className="axis" />
      </svg>
      <figcaption>
        <span className="gchart-title">{chart.title}{chart.unit ? ` (${chart.unit})` : ""}</span>
        {chart.series.length > 1 && (
          <span className="gchart-legend">
            {[...bars, ...lines].map((s, k) => <span key={s.name}><i style={{ background: color(k) }} />{s.name}</span>)}
          </span>
        )}
      </figcaption>
    </figure>
  );
}
