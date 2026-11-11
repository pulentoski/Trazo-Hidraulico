// Utilidades del panel general (Resumen): enlaces a elementos, puntos para el mapa y polígonos de las capas.
import type { LngLat } from "./geo";
import type { Network } from "./network";

export type ElType = "node" | "link" | "client" | "shutoff" | "hydrant" | "well";

/** ID visible → uid del editor, por tipo de elemento. */
export function uidMaps(net: Network): Record<ElType, Map<string, string>> {
  const m = (pool: Record<string, { uid: string; id: string }>) => new Map(Object.values(pool).map((e) => [e.id, e.uid]));
  return { node: m(net.nodes), link: m(net.links), client: m(net.clients), shutoff: m(net.shutoffs), hydrant: m(net.hydrants), well: m(net.wells) };
}

export function uidsOf(maps: Record<ElType, Map<string, string>>, type: ElType, ids: string[]): string[] {
  return ids.map((i) => maps[type].get(i)).filter((u): u is string => !!u);
}

/** Puntos que encuadran un conjunto de elementos (para centrar el mapa sin seleccionarlos). */
export function pointsOf(net: Network, uids: string[]): LngLat[] {
  const pts: LngLat[] = [];
  for (const u of uids) {
    if (net.nodes[u]) pts.push(net.nodes[u].pos);
    for (const pool of [net.clients, net.hydrants, net.wells] as Record<string, { pos: LngLat }>[]) if (pool[u]) pts.push(pool[u].pos);
    const l = net.links[u] ?? (net.shutoffs[u] ? net.links[net.shutoffs[u].link] : undefined);
    if (l) {
      for (const n of [net.nodes[l.from], net.nodes[l.to]]) if (n) pts.push(n.pos);
      pts.push(...l.vertices);
    }
  }
  return pts;
}

/** Geometría GeoJSON (Polygon o MultiPolygon, lon/lat) → lista de polígonos (anillos de puntos). */
export function polygonsOf(geom: { type?: unknown; coordinates?: unknown } | null | undefined): LngLat[][][] {
  if (!geom) return [];
  if (geom.type === "Polygon") return [geom.coordinates as LngLat[][]];
  if (geom.type === "MultiPolygon") return geom.coordinates as LngLat[][][];
  if (geom.type === "GeometryCollection") {
    return ((geom as { geometries?: { type?: unknown; coordinates?: unknown }[] }).geometries ?? []).flatMap(polygonsOf);
  }
  return [];
}

/** Colores de los rangos de presión: rojo (bajo) → verde → azul → morado (alto). */
const ZONE_PALETTE = ["#d7301f", "#f39c34", "#2e9d5b", "#2b7bba", "#7b4fb3", "#4a2a7a", "#22113f", "#000000", "#555555"];
export function zoneColor(cls: number): string {
  return ZONE_PALETTE[Math.max(0, Math.min(cls, ZONE_PALETTE.length - 1))];
}

/** Hora de un periodo de reporte («8:00»). */
export function hourLabel(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `${h}:${String(m).padStart(2, "0")}`;
}

/** Pesos chilenos sin decimales. */
export function clp(x: number | null | undefined): string {
  if (x === null || x === undefined) return "—";
  return `$${Math.round(x).toLocaleString("es-CL")}`;
}
