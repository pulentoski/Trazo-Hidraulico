// Proyección Web Mercator (la misma de Google Maps, mosaicos de 256 px) y distancias geodésicas.
export type LngLat = [number, number];
export interface Camera { center: LngLat; zoom: number }
export interface Size { width: number; height: number }

const TILE = 256;
const MAX_LAT = 85.05112878;

export function worldPx([lng, lat]: LngLat, zoom: number): [number, number] {
  const scale = TILE * 2 ** zoom;
  const phi = (Math.max(-MAX_LAT, Math.min(MAX_LAT, lat)) * Math.PI) / 180;
  const x = ((lng + 180) / 360) * scale;
  const y = (0.5 - Math.log((1 + Math.sin(phi)) / (1 - Math.sin(phi))) / (4 * Math.PI)) * scale;
  return [x, y];
}

export function worldToLngLat([x, y]: [number, number], zoom: number): LngLat {
  const scale = TILE * 2 ** zoom;
  const lng = (x / scale) * 360 - 180;
  const n = Math.PI - (2 * Math.PI * y) / scale;
  const lat = (180 / Math.PI) * Math.atan(0.5 * (Math.exp(n) - Math.exp(-n)));
  return [lng, lat];
}

export function project(p: LngLat, cam: Camera, size: Size): [number, number] {
  const [wx, wy] = worldPx(p, cam.zoom);
  const [cx, cy] = worldPx(cam.center, cam.zoom);
  return [wx - cx + size.width / 2, wy - cy + size.height / 2];
}

export function unproject([sx, sy]: [number, number], cam: Camera, size: Size): LngLat {
  const [cx, cy] = worldPx(cam.center, cam.zoom);
  return worldToLngLat([sx - size.width / 2 + cx, sy - size.height / 2 + cy], cam.zoom);
}

export function panBy(cam: Camera, dx: number, dy: number): Camera {
  const [cx, cy] = worldPx(cam.center, cam.zoom);
  return { ...cam, center: worldToLngLat([cx - dx, cy - dy], cam.zoom) };
}

/** Zoom entero (compatible con mapas raster) manteniendo fijo el punto bajo el cursor. */
export function zoomAt(cam: Camera, size: Size, at: [number, number], delta: number): Camera {
  const zoom = Math.max(2, Math.min(22, Math.round(cam.zoom + delta)));
  if (zoom === cam.zoom) return cam;
  const anchor = unproject(at, cam, size);
  const [ax, ay] = worldPx(anchor, zoom);
  const center = worldToLngLat([ax - (at[0] - size.width / 2), ay - (at[1] - size.height / 2)], zoom);
  return { center, zoom };
}

export function fitBounds(points: LngLat[], size: Size, padding = 60): Camera | null {
  if (!points.length) return null;
  const lngs = points.map((p) => p[0]);
  const lats = points.map((p) => p[1]);
  const sw: LngLat = [Math.min(...lngs), Math.min(...lats)];
  const ne: LngLat = [Math.max(...lngs), Math.max(...lats)];
  const center: LngLat = [(sw[0] + ne[0]) / 2, (sw[1] + ne[1]) / 2];
  let zoom = 20;
  while (zoom > 2) {
    const a = worldPx(sw, zoom);
    const b = worldPx(ne, zoom);
    if (Math.abs(b[0] - a[0]) <= size.width - 2 * padding && Math.abs(a[1] - b[1]) <= size.height - 2 * padding) break;
    zoom -= 1;
  }
  return { center, zoom };
}

const R = 6371008.8;
export function haversine(a: LngLat, b: LngLat): number {
  const toRad = Math.PI / 180;
  const dLat = (b[1] - a[1]) * toRad;
  const dLng = (b[0] - a[0]) * toRad;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a[1] * toRad) * Math.cos(b[1] * toRad) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}

export function polylineLength(pts: LngLat[]): number {
  let s = 0;
  for (let i = 1; i < pts.length; i++) s += haversine(pts[i - 1], pts[i]);
  return s;
}

export function distToSegment(p: [number, number], a: [number, number], b: [number, number]): number {
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  const len2 = dx * dx + dy * dy;
  const t = len2 ? Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / len2)) : 0;
  return Math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy));
}

/** Metros por píxel de pantalla en el centro de la cámara (Web Mercator, mosaicos de 256 px). */
export function metersPerPixel(cam: Camera): number {
  const lat = (Math.max(-MAX_LAT, Math.min(MAX_LAT, cam.center[1])) * Math.PI) / 180;
  return (2 * Math.PI * 6378137 * Math.cos(lat)) / (TILE * 2 ** cam.zoom);
}

/** Escala gráfica: el mayor largo «redondo» (1, 2 o 5 × 10ⁿ m) que cabe en `maxPx` píxeles. */
export function scaleBar(cam: Camera, maxPx = 120): { meters: number; px: number; label: string } {
  const mpp = metersPerPixel(cam);
  const max = mpp * maxPx;
  const pow = 10 ** Math.floor(Math.log10(max));
  const meters = [5, 2, 1].map((m) => m * pow).find((m) => m <= max) ?? pow;
  const label = meters >= 1000 ? `${(meters / 1000).toLocaleString("es-CL")} km` : `${meters.toLocaleString("es-CL")} m`;
  return { meters, px: meters / mpp, label };
}
