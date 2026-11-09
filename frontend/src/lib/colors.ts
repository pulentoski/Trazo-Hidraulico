// Escalas de color para tramos y nudos. Las clases se anclan a los criterios del perfil de diseño.
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

export interface Scale { breaks: number[]; colors: string[]; labels: string[]; unit: string }

function labelsFor(breaks: number[], digits: number, unit: string): string[] {
  const out: string[] = [];
  for (let i = 0; i <= breaks.length; i++) {
    if (i === 0) out.push(`< ${fmt(breaks[0], digits)}`);
    else if (i === breaks.length) out.push(`≥ ${fmt(breaks[i - 1], digits)}`);
    else out.push(`${fmt(breaks[i - 1], digits)} – ${fmt(breaks[i], digits)}`);
  }
  return out.map((l) => `${l} ${unit}`);
}

export function classify(v: number, breaks: number[]): number {
  let i = 0;
  while (i < breaks.length && v >= breaks[i]) i++;
  return i;
}

function quantileBreaks(values: number[], n: number): number[] {
  const v = values.filter((x) => Number.isFinite(x)).sort((a, b) => a - b);
  if (v.length < 2) return [1, 2, 3, 4, 5];
  const out: number[] = [];
  for (let i = 1; i < n; i++) out.push(v[Math.floor((i * (v.length - 1)) / n)]);
  for (let i = 1; i < out.length; i++) if (out[i] <= out[i - 1]) out[i] = out[i - 1] + 1e-6;
  return out;
}

export interface Criteria { pressureMin: number; pressureMax: number; velocityMin: number; velocityMax: number; headlossMax: number }
export const DEFAULT_CRITERIA: Criteria = { pressureMin: 15, pressureMax: 70, velocityMin: 0.3, velocityMax: 2, headlossMax: 10 };

export function linkScale(mode: LinkColorMode, crit: Criteria, values: number[]): Scale {
  switch (mode) {
    case "headloss": {
      const h = crit.headlossMax;
      const b = [h * 0.1, h * 0.3, h * 0.5, h, h * 2];
      return { breaks: b, colors: SEQ, labels: labelsFor(b, 1, "m/km"), unit: "m/km" };
    }
    case "velocity": {
      const b = [crit.velocityMin, 0.6, 1.0, 1.5, crit.velocityMax].sort((x, y) => x - y);
      return { breaks: b, colors: SEQ, labels: labelsFor(b, 2, "m/s"), unit: "m/s" };
    }
    case "flow": {
      const b = quantileBreaks(values.map(Math.abs), 6);
      return { breaks: b, colors: SEQ, labels: labelsFor(b, 2, "L/s"), unit: "L/s" };
    }
    case "diameter": {
      const uniq = [...new Set(values.filter((x) => x > 0))].sort((a, b) => a - b);
      const b = uniq.length <= 6 ? uniq.slice(1) : quantileBreaks(uniq, 6);
      return { breaks: b, colors: SEQ.slice(0, b.length + 1), labels: labelsFor(b, 0, "mm"), unit: "mm" };
    }
  }
}

export function pressureScale(crit: Criteria): Scale {
  const b = [0, crit.pressureMin, 30, 50, crit.pressureMax].sort((x, y) => x - y);
  return { breaks: b, colors: PRESSURE_COLORS, labels: labelsFor(b, 0, "m"), unit: "m" };
}
