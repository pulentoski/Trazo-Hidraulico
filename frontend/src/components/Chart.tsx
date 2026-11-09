// Gráfico de líneas liviano en SVG (sin dependencias): ejes, leyenda, líneas de referencia, tema claro y oscuro,
// exportación a PNG y CSV.
import { useMemo, useRef } from "react";
import type { Series } from "../lib/charts";
import { niceTicks, seriesCsv } from "../lib/charts";
import { downloadText } from "../lib/csv";
import { useEditor } from "../state/store";

export const PALETTE = ["#0b6aa8", "#e07b00", "#2e9d5b", "#c0362c", "#7a4fb3", "#00a3b4"];

interface Props {
  title: string;
  x: number[];
  xLabel: string;
  xFormat?: (v: number) => string;
  series: Series[];
  yLabel: string;
  refLines?: { value: number; label: string; color?: string }[];
  right?: { factor: number; label: string };
  step?: boolean;
  fileName: string;
  height?: number;
}

function themeColors() {
  const cs = getComputedStyle(document.documentElement);
  const v = (k: string, fb: string) => cs.getPropertyValue(k).trim() || fb;
  return { text: v("--text", "#1b2733"), muted: v("--muted", "#5f6f7f"), line: v("--line", "#d8dee5"), panel: v("--panel", "#ffffff") };
}

export function Chart({ title, x, xLabel, xFormat = (v) => String(v), series, yLabel, refLines = [], right, step, fileName, height = 260 }: Props) {
  const theme = useEditor((s) => s.theme);
  const svgRef = useRef<SVGSVGElement>(null);
  const c = useMemo(() => themeColors(), [theme]); // eslint-disable-line react-hooks/exhaustive-deps
  const W = 640;
  const H = height;
  const m = { l: 56, r: right ? 56 : 16, t: 42, b: 42 };
  const vals = series.flatMap((s) => s.values.filter((v): v is number => v !== null && Number.isFinite(v)));
  const ys = [...vals, ...refLines.map((r) => r.value)];
  let y0 = ys.length ? Math.min(...ys) : 0;
  let y1 = ys.length ? Math.max(...ys) : 1;
  if (y0 > 0 && y0 < (y1 - y0) * 0.6) y0 = 0;
  if (y0 === y1) { y0 -= 1; y1 += 1; }
  const pad = (y1 - y0) * 0.06;
  y0 -= y0 === 0 ? 0 : pad;
  y1 += pad;
  const xa = x.length ? Math.min(...x) : 0;
  const xb = x.length ? Math.max(...x) : 1;
  const sx = (v: number) => m.l + ((v - xa) / (xb - xa || 1)) * (W - m.l - m.r);
  const sy = (v: number) => H - m.b - ((v - y0) / (y1 - y0 || 1)) * (H - m.t - m.b);
  const yt = niceTicks(y0, y1, 5);
  const xt = x.length <= 25 ? x.filter((_, i) => x.length <= 13 || i % 2 === 0) : niceTicks(xa, xb, 8);
  const path = (vs: (number | null)[]) => {
    let d = "";
    let pen = false;
    vs.forEach((v, i) => {
      if (v === null || !Number.isFinite(v)) { pen = false; return; }
      const px = sx(x[i]);
      const py = sy(v);
      if (!pen) d += `M${px.toFixed(1)},${py.toFixed(1)}`;
      else if (step) d += `H${px.toFixed(1)}V${py.toFixed(1)}`;
      else d += `L${px.toFixed(1)},${py.toFixed(1)}`;
      pen = true;
    });
    return d;
  };

  const exportPng = () => {
    const svg = svgRef.current;
    if (!svg) return;
    const xml = new XMLSerializer().serializeToString(svg);
    const img = new Image();
    const scale = 2;
    img.onload = () => {
      const canvas = document.createElement("canvas");
      canvas.width = W * scale;
      canvas.height = H * scale;
      const ctx = canvas.getContext("2d")!;
      ctx.fillStyle = c.panel;
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      canvas.toBlob((blob) => {
        if (!blob) return;
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = `${fileName}.png`;
        a.click();
        setTimeout(() => URL.revokeObjectURL(a.href), 2000);
      }, "image/png");
    };
    img.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(xml);
  };
  const exportCsv = () => downloadText(`${fileName}.csv`, seriesCsv(xLabel, x.map(xFormat), series));

  return (
    <figure className="chart">
      <svg ref={svgRef} xmlns="http://www.w3.org/2000/svg" viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label={title}
        fontFamily="IBM Plex Sans, system-ui, sans-serif" fontSize="11">
        <rect x={0} y={0} width={W} height={H} fill={c.panel} />
        <text x={m.l} y={16} fill={c.text} fontSize="13" fontWeight="600">{title}</text>
        {yt.map((t) => (
          <g key={`y${t}`}>
            <line x1={m.l} x2={W - m.r} y1={sy(t)} y2={sy(t)} stroke={c.line} />
            <text x={m.l - 6} y={sy(t) + 4} textAnchor="end" fill={c.muted}>{Number(t.toFixed(3)).toLocaleString("es-CL")}</text>
            {right && <text x={W - m.r + 6} y={sy(t) + 4} fill={c.muted}>{Number((t * right.factor).toFixed(1)).toLocaleString("es-CL")}</text>}
          </g>
        ))}
        {xt.map((t) => (
          <g key={`x${t}`}>
            <line x1={sx(t)} x2={sx(t)} y1={H - m.b} y2={H - m.b + 4} stroke={c.muted} />
            <text x={sx(t)} y={H - m.b + 16} textAnchor="middle" fill={c.muted}>{xFormat(t)}</text>
          </g>
        ))}
        <line x1={m.l} x2={W - m.r} y1={H - m.b} y2={H - m.b} stroke={c.muted} />
        <text x={(m.l + W - m.r) / 2} y={H - 6} textAnchor="middle" fill={c.muted}>{xLabel}</text>
        <text transform={`translate(13,${(m.t + H - m.b) / 2}) rotate(-90)`} textAnchor="middle" fill={c.muted}>{yLabel}</text>
        {right && <text transform={`translate(${W - 10},${(m.t + H - m.b) / 2}) rotate(90)`} textAnchor="middle" fill={c.muted}>{right.label}</text>}
        {refLines.map((r) => (
          <g key={r.label}>
            <line x1={m.l} x2={W - m.r} y1={sy(r.value)} y2={sy(r.value)} stroke={r.color ?? "#c0362c"} strokeDasharray="6 4" strokeWidth={1.5} />
            <text x={W - m.r - 4} y={sy(r.value) - 4} textAnchor="end" fill={r.color ?? "#c0362c"}>{r.label}</text>
          </g>
        ))}
        {series.map((s, i) => (
          <path key={s.name} d={path(s.values)} fill="none" stroke={s.color ?? PALETTE[i % PALETTE.length]} strokeWidth={2}
            strokeDasharray={s.dashed ? "5 4" : undefined} />
        ))}
        {series.map((s, i) => (
          <g key={`lg-${s.name}`} transform={`translate(${m.l + 8 + i * 160},${m.t - 14})`}>
            <line x1={0} x2={18} y1={0} y2={0} stroke={s.color ?? PALETTE[i % PALETTE.length]} strokeWidth={2} strokeDasharray={s.dashed ? "5 4" : undefined} />
            <text x={22} y={4} fill={c.text}>{s.name}</text>
          </g>
        ))}
      </svg>
      <figcaption className="toolbar">
        <button className="small" onClick={exportPng}>PNG</button>
        <button className="small" onClick={exportCsv}>CSV</button>
      </figcaption>
    </figure>
  );
}
