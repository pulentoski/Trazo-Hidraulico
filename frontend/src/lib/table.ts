// Lógica de la tabla común (components/DataTable.tsx): búsqueda sin tildes, orden por tipo de dato (texto A–Z con
// números naturales, números con orden numérico real y fechas) y paginación. Sin dependencias de React.

export type CellType = "text" | "num" | "date";
export type CellValue = string | number | boolean | null | undefined | Date;

/** Normaliza para buscar: minúsculas y sin tildes. */
export function norm(t: string): string {
  return t.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
}

function isEmpty(v: CellValue): boolean {
  return v === null || v === undefined || v === "" || (typeof v === "number" && !Number.isFinite(v));
}

/** Valor numérico de una celda: acepta números y textos con coma decimal o separador de miles es-CL. */
export function toNumber(v: CellValue): number | null {
  if (typeof v === "number") return Number.isFinite(v) ? v : null;
  if (typeof v === "boolean") return v ? 1 : 0;
  if (v instanceof Date) return v.getTime();
  if (typeof v !== "string") return null;
  const t = v.trim().replace(/\s/g, "");
  if (!t) return null;
  // «1.234,5» (es-CL) → 1234.5; «1234.5» → 1234.5
  const s = /,\d+$/.test(t) || /^\-?\d{1,3}(\.\d{3})+(,\d+)?$/.test(t) ? t.replace(/\./g, "").replace(",", ".") : t.replace(",", ".");
  const m = s.match(/^[-+]?\d*\.?\d+(e[-+]?\d+)?/i);
  return m ? Number(m[0]) : null;
}

/** Fecha de una celda en milisegundos: ISO, Date o «dd-mm-aaaa» / «dd/mm/aaaa» (es-CL). */
export function toTime(v: CellValue): number | null {
  if (v instanceof Date) return v.getTime();
  if (typeof v === "number") return Number.isFinite(v) ? v : null;
  if (typeof v !== "string" || !v.trim()) return null;
  const cl = v.trim().match(/^(\d{1,2})[-/](\d{1,2})[-/](\d{2,4})(?:[ ,T]+(\d{1,2}):(\d{2}))?/);
  if (cl) {
    const y = cl[3].length === 2 ? 2000 + Number(cl[3]) : Number(cl[3]);
    return new Date(y, Number(cl[2]) - 1, Number(cl[1]), Number(cl[4] ?? 0), Number(cl[5] ?? 0)).getTime();
  }
  const t = Date.parse(v);
  return Number.isNaN(t) ? null : t;
}

const collator = new Intl.Collator("es", { numeric: true, sensitivity: "base" });

/** Compara dos celdas según su tipo; las vacías van siempre al final (en ambos sentidos). */
export function compareCells(a: CellValue, b: CellValue, type: CellType, dir: 1 | -1 = 1): number {
  const ea = isEmpty(a);
  const eb = isEmpty(b);
  if (ea || eb) return ea === eb ? 0 : ea ? 1 : -1;
  if (type === "num" || type === "date") {
    const x = type === "num" ? toNumber(a) : toTime(a);
    const y = type === "num" ? toNumber(b) : toTime(b);
    if (x === null || y === null) return x === y ? 0 : x === null ? 1 : -1;
    return (x - y) * dir;
  }
  return collator.compare(String(a), String(b)) * dir;
}

export interface SortSpec { key: string; dir: 1 | -1 }

export function sortRows<T>(rows: T[], value: (r: T) => CellValue, type: CellType, dir: 1 | -1): T[] {
  // Orden estable: ante empate conserva el orden original.
  return rows.map((r, i) => [r, i] as const)
    .sort((x, y) => compareCells(value(x[0]), value(y[0]), type, dir) || x[1] - y[1])
    .map(([r]) => r);
}

/** Filtra filas que contienen todas las palabras de la búsqueda en alguno de sus textos. */
export function filterRows<T>(rows: T[], query: string, texts: (r: T) => string[]): T[] {
  const words = norm(query).split(/\s+/).filter(Boolean);
  if (!words.length) return rows;
  return rows.filter((r) => {
    const hay = norm(texts(r).join(" "));
    return words.every((w) => hay.includes(w));
  });
}

export function paginate<T>(rows: T[], page: number, size: number): { rows: T[]; page: number; pages: number } {
  if (size <= 0) return { rows, page: 0, pages: 1 };
  const pages = Math.max(1, Math.ceil(rows.length / size));
  const p = Math.min(Math.max(0, page), pages - 1);
  return { rows: rows.slice(p * size, (p + 1) * size), page: p, pages };
}

/** Texto de una celda para búsqueda y exportación. */
export function cellText(v: CellValue): string {
  if (isEmpty(v)) return "";
  if (v instanceof Date) return v.toISOString();
  if (typeof v === "boolean") return v ? "sí" : "no";
  return String(v);
}
