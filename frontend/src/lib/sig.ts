// Utilidades del SIG en el editor: ubicar elementos por hoja e ID, textos de cuarteles y teselas visibles.
import type { Camera, Size } from "./geo";
import { worldPx } from "./geo";
import type { Network } from "./network";

/** uid del editor para un elemento de una hoja de la planilla (nudos, tramos, válvulas, …). */
export function uidOf(net: Network, element: string, id: string): string | null {
  const find = (pool: Record<string, { uid: string; id: string }>) => Object.values(pool).find((x) => x.id === id)?.uid ?? null;
  switch (element) {
    case "nudos": case "estanques": case "reservorios": return find(net.nodes);
    case "tramos": case "bombas": return find(net.links);
    case "valvulas": return find(net.shutoffs) ?? find(net.links);
    case "grifos": return find(net.hydrants);
    case "pozos": return find(net.wells);
    case "clientes": return find(net.clients);
    default: return null;
  }
}

/** «V3», «V3 y V7», «V3, V7 y V9». */
export function joinEs(items: string[]): string {
  if (items.length <= 1) return items.join("");
  return `${items.slice(0, -1).join(", ")} y ${items[items.length - 1]}`;
}

export function cutMessage(valves: string[], affected: number): string {
  const v = valves.length ? `cierre ${joinEs(valves)}` : "no hay válvulas que lo aíslen (se debe cortar en la fuente)";
  const c = affected === 1 ? "queda sin agua 1 cliente" : `quedan sin agua ${affected} clientes`;
  return `Para cortar aquí, ${v}; ${c}.`;
}

export interface Tile { z: number; x: number; y: number; left: number; top: number; size: number }

/** Teselas XYZ (256 px) que cubren la vista, al zoom entero de la cámara (máx. `maxZoom`, sobremuestreo). */
export function visibleTiles(cam: Camera, size: Size, bounds?: number[] | null, maxZoom = 22): Tile[] {
  const z = Math.max(0, Math.min(maxZoom, Math.round(cam.zoom)));
  const scale = 2 ** (cam.zoom - z);
  const tilePx = 256 * scale;
  const [cx, cy] = worldPx(cam.center, cam.zoom);
  const left = cx - size.width / 2;
  const top = cy - size.height / 2;
  const n = 2 ** z;
  let x0 = Math.floor(left / tilePx);
  let x1 = Math.floor((left + size.width) / tilePx);
  let y0 = Math.max(0, Math.floor(top / tilePx));
  let y1 = Math.min(n - 1, Math.floor((top + size.height) / tilePx));
  if (bounds && bounds.length === 4) {
    const [bw, bs, be, bn] = bounds;
    const [ax, ay] = worldPx([bw, bn], cam.zoom);
    const [bx, by] = worldPx([be, bs], cam.zoom);
    x0 = Math.max(x0, Math.floor(ax / tilePx));
    x1 = Math.min(x1, Math.floor(bx / tilePx));
    y0 = Math.max(y0, Math.floor(ay / tilePx));
    y1 = Math.min(y1, Math.floor(by / tilePx));
  }
  const out: Tile[] = [];
  for (let x = x0; x <= x1; x++) {
    for (let y = y0; y <= y1; y++) {
      const wx = ((x % n) + n) % n;
      out.push({ z, x: wx, y, left: x * tilePx - left, top: y * tilePx - top, size: tilePx });
    }
  }
  return out.slice(0, 400);
}

export function tileUrl(template: string, t: Tile): string {
  return template.replace("{z}", String(t.z)).replace("{x}", String(t.x)).replace("{y}", String(t.y));
}
