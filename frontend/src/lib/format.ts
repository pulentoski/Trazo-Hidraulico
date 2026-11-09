// Formato numérico es-CL (coma decimal) y unidades SI.
const cache = new Map<number, Intl.NumberFormat>();
function nf(d: number): Intl.NumberFormat {
  let f = cache.get(d);
  if (!f) {
    f = new Intl.NumberFormat("es-CL", { minimumFractionDigits: d, maximumFractionDigits: d });
    cache.set(d, f);
  }
  return f;
}

export function fmt(x: number | null | undefined, digits = 2): string {
  if (x === null || x === undefined || Number.isNaN(x)) return "—";
  // Evita «-0,00» en valores que redondean a cero.
  const v = Math.abs(x) < 0.5 * 10 ** -digits ? 0 : x;
  return nf(digits).format(v);
}

export function fmtLen(m: number | null | undefined): string {
  if (m === null || m === undefined) return "—";
  return m >= 1000 ? `${fmt(m / 1000, 3)} km` : `${fmt(m, 2)} m`;
}

export function fmtTime(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `${h}:${String(m).padStart(2, "0")} h`;
}

export function fmtDate(iso: string): string {
  return new Date(iso).toLocaleString("es-CL", { dateStyle: "short", timeStyle: "short" });
}

/** Lee un número escrito con coma o punto decimal. */
export function parseNum(s: string): number | null {
  const t = s.trim().replace(/\s/g, "").replace(",", ".");
  if (t === "") return null;
  const v = Number(t);
  return Number.isFinite(v) ? v : null;
}
