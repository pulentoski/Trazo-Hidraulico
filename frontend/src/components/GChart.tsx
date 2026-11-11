// Gráfico de la página «Gestión»: eje X por categorías (meses, horas, materiales), barras (agrupadas o apiladas) y
// líneas, con línea de referencia y de meta. Estilo uniforme (colores del tema, ejes y cuadrícula suaves), tooltip
// al pasar el cursor y dibujo inicial suave (si las animaciones están activas).
import { useRef, useState } from "react";
import type { GChartData } from "../api/types";
import { niceTicks } from "../lib/charts";
import { fmt } from "../lib/format";

const W = 560;
const COLORS = 6;
const color = (k: number) => `var(--chart-${(k % COLORS) + 1})`;

export function GChart({ chart, height = 190 }: { chart: GChartData; height?: number }) {
  const [hover, setHover] = useState<number | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const H = height;
  const m = { l: 46, r: 10, t: 12, b: 30 };
  const n = chart.x.length;
  const bars = chart.series.filter((s) => s.kind === "bar");
  const lines = chart.series.filter((s) => s.kind !== "bar");
  const stackTotals = chart.stacked ? chart.x.map((_, i) => bars.reduce((a, s) => a + Math.max(0, s.values[i] ?? 0), 0)) : [];
  const vals = [
    ...chart.series.flatMap((s) => s.values.filter((v): v is number => v !== null && v !== undefined && Number.isFinite(v))),
    ...stackTotals, ...(chart.reference != null ? [chart.reference] : []), ...(chart.goal != null ? [chart.goal] : []),
  ];
  if (!n || !chart.series.some((s) => s.values.some((v) => v !== null && v !== undefined))) {
    return <p className="muted small chart-empty">Sin datos para graficar en el período.</p>;
  }
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
  const groupW = Math.max(2, bw * 0.68);
  const barW = chart.stacked || !bars.length ? groupW : groupW / bars.length;
  const label = (x: string) => (x.length === 7 && /^\d{4}-\d{2}$/.test(x) ? `${x.slice(5)}/${x.slice(2, 4)}` : x.length > 9 ? `${x.slice(0, 8)}…` : x);
  const all = [...bars, ...lines];
  const colorOf = (name: string) => color(all.findIndex((s) => s.name === name));

  const move = (e: React.PointerEvent<SVGSVGElement>) => {
    const r = svgRef.current?.getBoundingClientRect();
    if (!r) return;
    const x = ((e.clientX - r.left) / r.width) * W;
    const i = Math.floor((x - m.l) / bw);
    setHover(i >= 0 && i < n ? i : null);
  };
  const tipX = hover !== null ? sx(hover) : 0;
  return (
    <figure className="gchart">
      <div className="gchart-plot">
        <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${chart.title}${chart.unit ? ` (${chart.unit})` : ""}`}
          onPointerMove={move} onPointerLeave={() => setHover(null)}>
          {ticks.map((t) => (
            <g key={t}>
              <line x1={m.l} x2={W - m.r} y1={sy(t)} y2={sy(t)} className="grid" />
              <text x={m.l - 6} y={sy(t) + 3} textAnchor="end" className="tick">{tickText(t)}</text>
            </g>
          ))}
          {chart.x.map((x, i) => i % every === 0 && (
            <text key={`x${i}`} x={sx(i)} y={H - m.b + 14} textAnchor="middle" className="tick">{label(x)}</text>
          ))}
          {hover !== null && <rect x={sx(hover) - bw / 2} y={m.t} width={bw} height={H - m.t - m.b} className="hover-band" />}
          {chart.x.map((_, i) => {
            let acc = 0;
            return bars.map((s, k) => {
              const v = s.values[i];
              if (v === null || v === undefined) return null;
              const delay = { animationDelay: `${Math.min(i * 12, 240)}ms` };
              if (chart.stacked) {
                const a = sy(acc + Math.max(0, v));
                const b = sy(acc);
                acc += Math.max(0, v);
                return <rect key={`${i}-${k}`} className="series-bar" style={delay} x={sx(i) - groupW / 2} y={a} width={groupW} height={Math.max(0, b - a)} fill={colorOf(s.name)} rx={1.5} />;
              }
              const top = sy(Math.max(0, v));
              const base = sy(Math.min(0, v));
              return <rect key={`${i}-${k}`} className="series-bar" style={delay} x={sx(i) - groupW / 2 + k * barW} y={top} width={Math.max(1, barW - 1)}
                height={Math.max(0, base - top)} fill={colorOf(s.name)} rx={1.5} />;
            });
          })}
          {lines.map((s) => {
            let d = "";
            let pen = false;
            let len = 0;
            let prev: [number, number] | null = null;
            s.values.forEach((v, i) => {
              if (v === null || v === undefined) { pen = false; prev = null; return; }
              const p: [number, number] = [sx(i), sy(v)];
              if (prev) len += Math.hypot(p[0] - prev[0], p[1] - prev[1]);
              d += `${pen ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)}`;
              pen = true;
              prev = p;
            });
            const c = colorOf(s.name);
            return (
              <g key={s.name}>
                <path d={d} fill="none" stroke={c} strokeWidth={2} className="series-line" style={{ ["--len" as string]: Math.ceil(len) + 2 }} />
                {s.values.map((v, i) => v !== null && v !== undefined && (n <= 31 || hover === i) && (
                  <circle key={i} cx={sx(i)} cy={sy(v)} r={hover === i ? 3.6 : 2.4} fill={c} />
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
          {chart.goal != null && (
            <g>
              <line x1={m.l} x2={W - m.r} y1={sy(chart.goal)} y2={sy(chart.goal)} className="goal" />
              <text x={m.l + 4} y={sy(chart.goal) - 4} className="tick goal-label">{chart.goal_label ?? "Meta"}</text>
            </g>
          )}
          <line x1={m.l} x2={W - m.r} y1={sy(0 > y0 ? 0 : y0)} y2={sy(0 > y0 ? 0 : y0)} className="axis" />
        </svg>
        {hover !== null && (
          <div className="gchart-tip" role="tooltip" style={{ left: `${(tipX / W) * 100}%` }}>
            <b>{chart.x[hover]}</b>
            {all.map((s) => {
              const v = s.values[hover];
              return <span key={s.name}><i style={{ background: colorOf(s.name) }} />{s.name}: {v === null || v === undefined ? "—" : `${fmt(v, Math.abs(v) < 10 ? 2 : 1)} ${chart.unit}`}</span>;
            })}
          </div>
        )}
      </div>
      <figcaption>
        <span className="gchart-title">{chart.title}{chart.unit ? ` (${chart.unit})` : ""}</span>
        {(all.length > 1 || chart.goal != null || chart.reference != null) && (
          <span className="gchart-legend">
            {all.map((s) => <span key={s.name}><i style={{ background: colorOf(s.name) }} />{s.name}</span>)}
            {chart.reference != null && <span><i className="leg-ref" />{chart.reference_label ?? "Referencia"}</span>}
            {chart.goal != null && <span><i className="leg-goal" />Meta</span>}
          </span>
        )}
      </figcaption>
    </figure>
  );
}
