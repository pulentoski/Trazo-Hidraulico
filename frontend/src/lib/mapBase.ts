// Proveedor del mapa base (Configuración → Mapa base) y mapa efectivo en el editor.
export type MapProvider = "google" | "osm" | "auto";
/** Mapa base efectivo: Google solo si se eligió (o es automático) y hay key; si no, OpenStreetMap. */
export type BaseKind = "google" | "osm";

export function baseOf(provider: MapProvider, apiKey: string): BaseKind {
  return provider !== "osm" && apiKey ? "google" : "osm";
}
