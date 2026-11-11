// Configuración del mapa base en tiempo de ejecución: la key y el Map ID guardados por el superadministrador
// (Configuración → Mapa base) llegan desde /api/maps/config; las variables VITE_ quedan solo como respaldo.
// La key nunca se muestra en la interfaz.
import { create } from "zustand";
import { api } from "../api/client";

const BUILD_KEY: string = import.meta.env.VITE_GOOGLE_MAPS_API_KEY || "";
const BUILD_MAP_ID: string = import.meta.env.VITE_GOOGLE_MAPS_MAP_ID || "";

interface MapConfigState {
  apiKey: string;
  mapId: string;
  source: "db" | "build" | "none";
  loaded: boolean;
  load: () => Promise<void>;
}

export const useMapConfig = create<MapConfigState>()((set) => ({
  apiKey: "",
  mapId: "",
  source: "none",
  loaded: false,
  load: async () => {
    try {
      const c = await api.mapsConfig();
      if (c.api_key) {
        set({ apiKey: c.api_key, mapId: c.map_id ?? "", source: "db", loaded: true });
        return;
      }
    } catch { /* sin sesión o API no disponible: respaldo */ }
    set({ apiKey: BUILD_KEY, mapId: BUILD_KEY ? BUILD_MAP_ID : "", source: BUILD_KEY ? "build" : "none", loaded: true });
  },
}));

/** Prueba una key desde el navegador (mismo referente HTTP que usará el mapa) con la API de Geocoding. */
export async function testMapsKey(key: string): Promise<{ ok: boolean; message: string }> {
  try {
    const r = await fetch(`https://maps.googleapis.com/maps/api/geocode/json?address=${encodeURIComponent("La Serena, Chile")}&key=${encodeURIComponent(key)}`);
    const body = (await r.json()) as { status?: string; error_message?: string };
    if (body.status === "OK" || body.status === "ZERO_RESULTS") return { ok: true, message: "La key responde correctamente desde este sitio." };
    return { ok: false, message: `Google respondió ${body.status ?? r.status}${body.error_message ? `: ${body.error_message}` : ""}` };
  } catch {
    return { ok: false, message: "No se pudo contactar a Google desde este equipo (sin Internet o bloqueado)." };
  }
}
