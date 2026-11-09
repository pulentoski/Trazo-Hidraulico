// Configuración del mapa base, incorporada al compilar. La key nunca se muestra en la interfaz.
export const GOOGLE_MAPS_API_KEY: string = import.meta.env.VITE_GOOGLE_MAPS_API_KEY || "";
export const GOOGLE_MAPS_MAP_ID: string = import.meta.env.VITE_GOOGLE_MAPS_MAP_ID || "";
export const HAS_MAP_KEY = GOOGLE_MAPS_API_KEY.length > 0;
