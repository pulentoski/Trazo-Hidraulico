// Ubicación de etiquetas del mapa sin superposición: se ubican por prioridad (seleccionado, nudos, pozos y grifos,
// tramos, llaves, clientes) y la que choca con una ya ubicada se oculta (se ve al pasar el mouse sobre su elemento).

export interface LabelItem {
  key: string; uid: string; x: number; y: number; text: string; cls: string;
  anchor: "start" | "middle"; prio: number;
}

const CHAR_W = 6.7; // ancho medio de un carácter de la etiqueta (px)
const LINE_H = 14;

export function labelBox(l: LabelItem): [number, number, number, number] {
  const w = l.text.length * CHAR_W;
  const x0 = l.anchor === "middle" ? l.x - w / 2 : l.x;
  return [x0, l.y - LINE_H + 3, x0 + w, l.y + 3];
}

/** Devuelve las claves de las etiquetas visibles (sin choques), en orden de prioridad. */
export function placeLabels(items: LabelItem[], size?: { width: number; height: number }): Set<string> {
  const placed: [number, number, number, number][] = [];
  const out = new Set<string>();
  const order = [...items].sort((a, b) => b.prio - a.prio || a.key.localeCompare(b.key));
  // Grilla de celdas para no comparar contra todas las etiquetas ubicadas (redes grandes).
  const CELL = 64;
  const grid = new Map<string, number[]>();
  for (const l of order) {
    const b = labelBox(l);
    if (size && (b[2] < 0 || b[0] > size.width || b[3] < 0 || b[1] > size.height)) continue;
    const cells: string[] = [];
    for (let cx = Math.floor(b[0] / CELL); cx <= Math.floor(b[2] / CELL); cx++)
      for (let cy = Math.floor(b[1] / CELL); cy <= Math.floor(b[3] / CELL); cy++) cells.push(`${cx}:${cy}`);
    const hit = cells.some((c) => (grid.get(c) ?? []).some((i) => {
      const p = placed[i];
      return b[0] < p[2] && b[2] > p[0] && b[1] < p[3] && b[3] > p[1];
    }));
    if (hit) continue;
    placed.push(b);
    for (const c of cells) grid.set(c, [...(grid.get(c) ?? []), placed.length - 1]);
    out.add(l.key);
  }
  return out;
}
