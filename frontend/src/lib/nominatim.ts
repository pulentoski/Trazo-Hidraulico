// Búsqueda de direcciones con Nominatim (OpenStreetMap), usada cuando el mapa base es OSM. Política de uso:
// https://operations.osmfoundation.org/policies/nominatim/ — una consulta por búsqueda enviada (sin autocompletar),
// el navegador envía el referente del sitio y la respuesta se atribuye a OpenStreetMap en el mapa.
import type { LngLat } from "./geo";

const URL_BASE = "https://nominatim.openstreetmap.org/search";

export function nominatimUrl(q: string): string {
  const p = new URLSearchParams({ q, format: "jsonv2", limit: "1", countrycodes: "cl", "accept-language": "es" });
  return `${URL_BASE}?${p.toString()}`;
}

/** Primera coincidencia [lon, lat] o null; lanza un error si el servicio no responde. */
export async function nominatim(q: string): Promise<LngLat | null> {
  const r = await fetch(nominatimUrl(q), { headers: { Accept: "application/json" } });
  if (!r.ok) throw new Error(`Nominatim respondió ${r.status}`);
  const rows = (await r.json()) as { lon?: string; lat?: string }[];
  const hit = rows[0];
  const lon = Number(hit?.lon), lat = Number(hit?.lat);
  return hit && Number.isFinite(lon) && Number.isFinite(lat) ? [lon, lat] : null;
}
