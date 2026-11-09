// Escalas de color para tramos y nudos. Las clases de pérdida y velocidad se anclan a los criterios del
// perfil de diseño; las de caudal y diámetro se derivan de los valores de la variable seleccionada.
import { fmt } from "./format";

export type LinkColorMode = "headloss" | "velocity" | "flow" | "diameter";
export const LINK_MODES: { id: LinkColorMode; label: string; unit: string }[] = [
  { id: "headloss", label: "Pérdida unitaria", unit: "m/km" },
  { id: "velocity", label: "Velocidad", unit: "m/s" },
  { id: "flow", label: "Caudal", unit: "L/s" },
  { id: "diameter", label: "Diámetro", unit: "mm" },
];

export const SEQ = ["#3b7fc4", "#2a9d8f", "#7cb342", "#e0b030", "#e8772e", "#d0342c"];
export const PRESSURE_COLORS = ["#8e44ad", "#d0342c", "#e8a02e", "#4caf50", "#2a9d8f", "#3b7fc4"];

/** Clase i: [lower[i], upper[i]); los extremos null son abiertos. */
export interface Scale {
  breaks: number[]; colors: string[]; labels: string[]; unit: string;
  lower: (number | null)[];
}

export function classify(v: number, breaks: number[]): number {
  let i = 0;
  while (i < breaks.length && v >= breaks[i]) i++;
  return i;
}

/** Quita cortes que se verían iguales con los decimales mostrados (evita clases repetidas o «a – a»). */
function distinctBreaks(breaks: number[], digits: number): number[] {
  const out: number[] = [];
  for (const b of [...breaks].filter(Number.isFinite).sort((x, y) => x - y)) {
    if (!out.length || fmt(b, digits) !== fmt(out[out.length - 1], digits)) out.push(b);
  }
  return out;
}

function spread(n: number, palette: string[]): string[] {
  if (n <= 1) return [palette[0]];
  return Array.from({ length: n }, (_, i) => palette[Math.round((i * (palette.length - 1)) / (n - 1))]);
}

function fixedScale(breaks: number[], digits: number, unit: string, palette: string[]): Scale {
  const b = distinctBreaks(breaks, digits);
  const labels: string[] = [];
  for (let i = 0; i <= b.length; i++) {
    if (b.length === 0) labels.push("todos");
    else if (i === 0) labels.push(`< ${fmt(b[0], digits)}`);
    else if (i === b.length) labels.push(`≥ ${fmt(b[i - 1], digits)}`);
    else labels.push(`${fmt(b[i - 1], digits)} – ${fmt(b[i], digits)}`);
  }
  const colors = b.length + 1 === palette.length ? palette : spread(b.length + 1, palette);
  return { breaks: b, colors, labels: labels.map((l) => `${l} ${unit}`), unit, lower: [null, ...b] };
}

/** Escala derivada de los datos: hasta 6 valores distintos → una clase por valor; si no, cuantiles. */
function dataScale(values: number[], digits: number, unit: string): Scale {
  const v = values.filter(Number.isFinite).sort((a, b) => a - b);
  const step = 10 ** -digits;
  const shown = [...new Set(v.map((x) => Math.round(x / step) * step))];
  const uniq = distinctBreaks(shown, digits);
  if (uniq.length <= 6) {
    // Corte en el punto medio entre valores mostrados consecutivos.
    const breaks = uniq.slice(1).map((u, i) => (uniq[i] + u) / 2);
    return { breaks, colors: spread(uniq.length, SEQ), labels: uniq.map((u) => `${fmt(u, digits)} ${unit}`), unit,
      lower: [null, ...breaks] };
  }
  const q: number[] = [];
  for (let i = 1; i < 6; i++) q.push(v[Math.floor((i * (v.length - 1)) / 6)]);
  const lo = v[0];
  const hi = v[v.length - 1];
  const breaks = distinctBreaks(q.filter((b) => fmt(b, digits) !== fmt(lo, digits)), digits);
  const edges = [lo, ...breaks, hi];
  const labels = breaks.map((_, i) => `${fmt(edges[i], digits)} – ${fmt(edges[i + 1], digits)}`);
  labels.push(fmt(edges[edges.length - 2], digits) === fmt(hi, digits)
    ? fmt(hi, digits) : `${fmt(edges[edges.length - 2], digits)} – ${fmt(hi, digits)}`);
  return { breaks, colors: spread(breaks.length + 1, SEQ), labels: labels.map((l) => `${l} ${unit}`), unit,
    lower: [null, ...breaks] };
}

export interface Criteria { pressureMin: number; pressureMax: number; velocityMin: number; velocityMax: number; headlossMax: number }
export const DEFAULT_CRITERIA: Criteria = { pressureMin: 15, pressureMax: 70, velocityMin: 0.3, velocityMax: 2, headlossMax: 10 };

export interface LinkLike { kind: string; id: string; props: { inner_diameter_mm?: number | null } }
export interface LinkSeriesLike { flow: number[]; velocity: number[]; headloss: number[] }

/**
 * Valor de la variable seleccionada para un tramo, o null si no corresponde (sin resultados, o pérdida
 * unitaria de bombas y válvulas, que el motor informa en m y no en m/km). Lo usan el mapa y la leyenda.
 */
export function linkValue(mode: LinkColorMode, l: LinkLike, r: LinkSeriesLike | undefined, period: number): number | null {
  if (mode === "diameter") return l.props.inner_diameter_mm ?? null;
  if (!r) return null;
  const pick = mode === "headloss" ? (l.kind === "pipe" ? r.headloss : null) : mode === "velocity" ? r.velocity : r.flow;
  const v = pick?.[period];
  return v === undefined || v === null || !Number.isFinite(v) ? null : Math.abs(v);
}

export function linkScale(mode: LinkColorMode, crit: Criteria, values: number[]): Scale {
  switch (mode) {
    case "headloss": {
      const h = crit.headlossMax;
      return fixedScale([h * 0.1, h * 0.3, h * 0.5, h, h * 2], 1, "m/km", SEQ);
    }
    case "velocity":
      return fixedScale([crit.velocityMin, 0.6, 1.0, 1.5, crit.velocityMax], 2, "m/s", SEQ);
    case "flow":
      return dataScale(values, 2, "L/s");
    case "diameter":
      return dataScale(values.filter((x) => x > 0), 0, "mm");
  }
}

export interface LegendClass { label: string; color: string; count: number; lower: number | null }

/** Clases a mostrar en la leyenda: solo las que tienen tramos (sin repetidas ni rangos vacíos). */
export function legendClasses(scale: Scale, values: number[]): LegendClass[] {
  const counts = new Array(scale.labels.length).fill(0);
  for (const v of values) if (Number.isFinite(v)) counts[classify(v, scale.breaks)]++;
  return scale.labels
    .map((label, i) => ({ label, color: scale.colors[i], count: counts[i], lower: scale.lower[i] }))
    .filter((c) => c.count > 0);
}

export function pressureScale(crit: Criteria): Scale {
  return fixedScale([0, crit.pressureMin, 30, 50, crit.pressureMax], 0, "m", PRESSURE_COLORS);
}
