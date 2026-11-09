// Curvas de modulación ([PATTERNS] en texto) y tiempos de simulación.

/** Curva CurvaMod de la planilla ModeloEstanque (0–23 h, promedio 0,956). */
export const CURVA_MOD = [0.3, 0.2, 0.1, 0.1, 0.3, 0.5, 0.9, 1.5, 1.6, 1.5, 1.45, 1.35, 1.4, 1.4, 1.3, 1.1, 1.0, 0.9, 1.0, 1.2, 1.25, 1.2, 0.9, 0.5];
export const DEFAULT_PATTERN_ID = "MOD";

export function mean(values: number[]): number {
  return values.length ? values.reduce((a, b) => a + b, 0) / values.length : 0;
}

/** Divide por el promedio para que el promedio sea 1 (conserva el volumen diario del caudal base). */
export function normalize(values: number[], digits = 4): number[] {
  const m = mean(values);
  if (!(m > 0)) return values;
  const k = 10 ** digits;
  return values.map((v) => Math.round((v / m) * k) / k);
}

export const CURVA_MOD_NORMALIZADA = normalize(CURVA_MOD);

export function parsePatterns(text: string | undefined | null): Record<string, number[]> {
  const out: Record<string, number[]> = {};
  for (const raw of (text ?? "").split("\n")) {
    const s = raw.split(";")[0].trim();
    if (!s) continue;
    const [id, ...vals] = s.split(/\s+/);
    const nums = vals.map(Number);
    if (nums.some((n) => !Number.isFinite(n))) continue;
    (out[id] ??= []).push(...nums);
  }
  return out;
}

export function formatPatterns(patterns: Record<string, number[]>): string {
  const lines: string[] = [];
  for (const [id, vals] of Object.entries(patterns)) {
    for (let i = 0; i < vals.length; i += 12) lines.push(` ${id}\t${vals.slice(i, i + 12).map((v) => String(v)).join("\t")}`);
  }
  return lines.join("\n");
}

/** «MOD tiene promedio 0,956»: null si el promedio está a menos de 0,5 % de 1. */
export function meanWarning(values: number[]): string | null {
  const m = mean(values);
  if (!values.length || Math.abs(m - 1) <= 0.005) return null;
  return `Promedio ${m.toFixed(3).replace(".", ",")} (no 1): el consumo diario queda ${(Math.abs(1 - m) * 100).toFixed(1).replace(".", ",")} % ${m < 1 ? "bajo" : "sobre"} el caudal base.`;
}

export function hourLabel(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `${h}:${String(m).padStart(2, "0")}`;
}
