// Coordenadas: lat/lon decimal, grados-minutos-segundos y UTM (WGS84). Conversión exacta al milímetro con las series
// de Krüger (Transverse Mercator), sin dependencias. Por defecto, huso 19 sur (zona central y norte de Chile).
import type { LngLat } from "./geo";

const A = 6378137.0;
const F = 1 / 298.257223563;
const K0 = 0.9996;
const N = F / (2 - F);
const AA = (A / (1 + N)) * (1 + N ** 2 / 4 + N ** 4 / 64 + N ** 6 / 256);
const ALPHA = [
  N / 2 - (2 / 3) * N ** 2 + (5 / 16) * N ** 3 + (41 / 180) * N ** 4 - (127 / 288) * N ** 5,
  (13 / 48) * N ** 2 - (3 / 5) * N ** 3 + (557 / 1440) * N ** 4 + (281 / 630) * N ** 5,
  (61 / 240) * N ** 3 - (103 / 140) * N ** 4 + (15061 / 26880) * N ** 5,
  (49561 / 161280) * N ** 4 - (179 / 168) * N ** 5,
  (34729 / 80640) * N ** 5,
];
const BETA = [
  N / 2 - (2 / 3) * N ** 2 + (37 / 96) * N ** 3 - (1 / 360) * N ** 4 - (81 / 512) * N ** 5,
  (1 / 48) * N ** 2 + (1 / 15) * N ** 3 - (437 / 1440) * N ** 4 + (46 / 105) * N ** 5,
  (17 / 480) * N ** 3 - (37 / 840) * N ** 4 - (209 / 4480) * N ** 5,
  (4397 / 161280) * N ** 4 - (11 / 504) * N ** 5,
  (4583 / 161280) * N ** 5,
];
const DELTA = [
  2 * N - (2 / 3) * N ** 2 - 2 * N ** 3 + (116 / 45) * N ** 4 + (26 / 45) * N ** 5,
  (7 / 3) * N ** 2 - (8 / 5) * N ** 3 - (227 / 45) * N ** 4 + (2704 / 315) * N ** 5,
  (56 / 15) * N ** 3 - (136 / 35) * N ** 4 - (1262 / 105) * N ** 5,
  (4279 / 630) * N ** 4 - (332 / 35) * N ** 5,
  (4174 / 315) * N ** 5,
];
const E2 = F * (2 - F);
const EE = Math.sqrt(E2);
const RAD = Math.PI / 180;

export const DEFAULT_ZONE = 19;
export const DEFAULT_SOUTH = true;

export interface Utm { e: number; n: number; zone: number; south: boolean }

export function zoneOf(lon: number): number {
  return Math.min(60, Math.max(1, Math.floor((lon + 180) / 6) + 1));
}

/** Lat/lon (WGS84) → UTM en el huso indicado (por defecto, el que corresponde a la longitud). */
export function toUtm([lon, lat]: LngLat, zone = zoneOf(lon), south = lat < 0): Utm {
  const lon0 = (zone * 6 - 183) * RAD;
  const phi = lat * RAD;
  const lam = lon * RAD - lon0;
  const t = Math.sinh(Math.atanh(Math.sin(phi)) - EE * Math.atanh(EE * Math.sin(phi)));
  const xi = Math.atan2(t, Math.cos(lam));
  const eta = Math.atanh(Math.sin(lam) / Math.sqrt(1 + t * t));
  let x = eta;
  let y = xi;
  for (let j = 1; j <= 5; j++) {
    x += ALPHA[j - 1] * Math.cos(2 * j * xi) * Math.sinh(2 * j * eta);
    y += ALPHA[j - 1] * Math.sin(2 * j * xi) * Math.cosh(2 * j * eta);
  }
  return { e: 500000 + K0 * AA * x, n: (south ? 10000000 : 0) + K0 * AA * y, zone, south };
}

/** UTM → [lon, lat] (WGS84). */
export function fromUtm({ e, n, zone, south }: Utm): LngLat {
  const xi = (n - (south ? 10000000 : 0)) / (K0 * AA);
  const eta = (e - 500000) / (K0 * AA);
  let xp = xi;
  let ep = eta;
  for (let j = 1; j <= 5; j++) {
    xp -= BETA[j - 1] * Math.sin(2 * j * xi) * Math.cosh(2 * j * eta);
    ep -= BETA[j - 1] * Math.cos(2 * j * xi) * Math.sinh(2 * j * eta);
  }
  const chi = Math.asin(Math.sin(xp) / Math.cosh(ep));
  let phi = chi;
  for (let j = 1; j <= 5; j++) phi += DELTA[j - 1] * Math.sin(2 * j * chi);
  const lon0 = (zone * 6 - 183) * RAD;
  const lam = Math.atan2(Math.sinh(ep), Math.cos(xp));
  return [(lon0 + lam) / RAD, phi / RAD];
}

const pad = (v: number, n: number, d = 0) => v.toFixed(d).padStart(n + (d ? d + 1 : 0), "0");

/** Grados-minutos-segundos: 33°26′56,0″S 70°40′09,5″W (segundos con un decimal). */
export function toDms([lon, lat]: LngLat, decimals = 1): string {
  const part = (v: number, pos: string, neg: string, w: number) => {
    const a = Math.abs(v);
    let d = Math.floor(a);
    let m = Math.floor((a - d) * 60);
    let s = Math.round(((a - d) * 60 - m) * 60 * 10 ** decimals) / 10 ** decimals;
    if (s >= 60) { s = 0; m += 1; }
    if (m >= 60) { m = 0; d += 1; }
    return `${pad(d, w)}°${pad(m, 2)}′${pad(s, 2, decimals).replace(".", ",")}″${v < 0 ? neg : pos}`;
  };
  return `${part(lat, "N", "S", 2)} ${part(lon, "E", "W", 3)}`;
}

export function formatLatLon([lon, lat]: LngLat, digits = 6): string {
  return `${lat.toFixed(digits)}, ${lon.toFixed(digits)}`;
}

export function formatUtm(u: Utm): string {
  return `${u.zone}${u.south ? "S" : "N"} E ${Math.round(u.e).toLocaleString("es-CL")} N ${Math.round(u.n).toLocaleString("es-CL")}`;
}

export type CoordKind = "decimal" | "dms" | "utm";
export interface Parsed { pos: LngLat; kind: CoordKind; utm?: Utm }

const num = (s: string) => Number(s.replace(",", "."));
const valid = ([lon, lat]: LngLat) => Number.isFinite(lon) && Number.isFinite(lat) && Math.abs(lat) <= 90 && Math.abs(lon) <= 180;

/** Huso en el texto: «19S», «19 S», «huso 19», «19H» (banda MGRS: C–M = sur, N–X = norte). */
function zoneIn(text: string): { zone: number; south: boolean } | null {
  const m = /(?:huso|zona|zone)?\s*\b(\d{1,2})\s*([A-HJ-NP-Za-hj-np-z])?\b(?![\d.,])/i.exec(text);
  if (!m) return null;
  const z = Number(m[1]);
  if (z < 1 || z > 60) return null;
  const band = m[2]?.toUpperCase();
  const south = band === undefined ? DEFAULT_SOUTH : band === "S" ? true : band === "N" ? false : band < "N";
  return { zone: z, south };
}

/** Texto libre → coordenada. Acepta:
 *  - decimal: «-33.4489, -70.6693» (lat, lon), «33.4489 S 70.6693 W», «-33,4489; -70,6693»;
 *  - grados-minutos-segundos: «33°26'56"S 70°40'9.5"W», «33 26 56 S 70 40 9,5 W», «S 33° 26.93' W 70° 40.16'»;
 *  - UTM: «344847 6297700» (huso 19S por defecto), «E 344847 N 6297700 19S», «19H 344847 6297700».
 */
export function parseCoordinates(input: string, defZone = DEFAULT_ZONE, defSouth = DEFAULT_SOUTH): Parsed | null {
  const text = input.trim().replace(/[‘’′]/g, "'").replace(/[“”″]/g, '"').replace(/''/g, '"');
  if (!text) return null;

  // UTM: dos números grandes (E, N), con o sin rótulos y huso.
  const big = [...text.matchAll(/(?<![\d.,])(\d{5,7}(?:[.,]\d+)?)(?![\d])/g)].map((m) => ({ v: num(m[1]), i: m.index ?? 0 }));
  if (big.length >= 2) {
    const labeled = (k: string) => {
      const m = new RegExp(`\\b(?:${k})\\s*[:=]?\\s*(\\d{5,7}(?:[.,]\\d+)?)`, "i").exec(text);
      return m ? num(m[1]) : null;
    };
    let e = labeled("E|Este|X");
    let n = labeled("N|Norte|Y");
    if (e === null || n === null) {
      const [a, b] = [big[0].v, big[1].v];
      [e, n] = a < b ? [a, b] : [b, a]; // el norte (7 dígitos) es mayor que el este (6 dígitos)
    }
    const rest = text.replace(/(\d{5,7}(?:[.,]\d+)?)/g, " ");
    const z = zoneIn(rest) ?? { zone: defZone, south: defSouth };
    if (e < 100000 || e > 900000 || n < 0 || n > 10000000) return null;
    const utm: Utm = { e, n, zone: z.zone, south: z.south };
    const pos = fromUtm(utm);
    return valid(pos) ? { pos, kind: "utm", utm } : null;
  }

  // Grados, minutos y segundos (o grados y minutos decimales), con hemisferio.
  const hemi = text.match(/[NSEWO]/gi);
  // El hemisferio va antes («S 33° 26′») o después («33° 26′ S») de cada valor, de forma consistente.
  const leading = /^\s*[NSEWO]\b/i.test(text) || /^\s*[NSEWO]\s*\d/i.test(text);
  const core = `(\\d{1,3}(?:[.,]\\d+)?)\\s*[°º:d\\s]\\s*(\\d{1,2}(?:[.,]\\d+)?)?\\s*'?\\s*(\\d{1,2}(?:[.,]\\d+)?)?\\s*"?`;
  const dmsRx = leading ? new RegExp(`([NSEWO])\\s*${core}()`, "gi") : new RegExp(`()${core}\\s*([NSEWO])?`, "gi");
  if (/[°º'"]/.test(text) || (hemi && hemi.length >= 2 && /\d+\s+\d+/.test(text))) {
    const parts = [...text.matchAll(dmsRx)].filter((m) => m[2]);
    if (parts.length >= 2) {
      const val = (m: RegExpMatchArray) => {
        const d = num(m[2]);
        const mi = m[3] ? num(m[3]) : 0;
        const s = m[4] ? num(m[4]) : 0;
        const h = (m[1] || m[5] || "").toUpperCase();
        const sign = h === "S" || h === "W" || h === "O" ? -1 : 1;
        return { v: sign * (d + mi / 60 + s / 3600), h };
      };
      const a = val(parts[0]);
      const b = val(parts[1]);
      const latFirst = !(a.h === "E" || a.h === "W" || a.h === "O" || b.h === "N" || b.h === "S");
      const pos: LngLat = latFirst ? [b.v, a.v] : [a.v, b.v];
      return valid(pos) ? { pos, kind: "dms" } : null;
    }
  }

  // Decimal: «lat, lon» (o con hemisferios).
  const m = /^\s*([NSEWO])?\s*(-?\d{1,3}(?:[.,]\d+)?)\s*([NSEWO])?\s*[,;\s]\s*([NSEWO])?\s*(-?\d{1,3}(?:[.,]\d+)?)\s*([NSEWO])?\s*$/i.exec(text);
  if (m) {
    const h1 = (m[1] || m[3] || "").toUpperCase();
    const h2 = (m[4] || m[6] || "").toUpperCase();
    let a = num(m[2]);
    let b = num(m[5]);
    if (h1 === "S" || h1 === "W" || h1 === "O") a = -Math.abs(a);
    if (h2 === "S" || h2 === "W" || h2 === "O") b = -Math.abs(b);
    const lonFirst = h1 === "E" || h1 === "W" || h1 === "O" || h2 === "N" || h2 === "S";
    const pos: LngLat = lonFirst ? [a, b] : [b, a];
    return valid(pos) ? { pos, kind: "decimal" } : null;
  }
  return null;
}
