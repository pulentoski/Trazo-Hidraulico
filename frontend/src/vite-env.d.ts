/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_GOOGLE_MAPS_API_KEY?: string;
  readonly VITE_GOOGLE_MAPS_MAP_ID?: string;
  readonly VITE_DEFAULT_MAP_CENTER_LAT?: string;
  readonly VITE_DEFAULT_MAP_CENTER_LNG?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

/** Versión de la aplicación (package.json), inyectada por Vite al compilar. */
declare const __APP_VERSION__: string;
