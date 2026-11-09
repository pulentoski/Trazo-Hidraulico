// Rutas de la aplicación (etapa 5 agregará LOGIN: "/login").
export const PATHS = {
  home: "/",
  settings: "/configuracion",
  about: "/acerca-de",
  project: (id: string) => `/proyecto/${encodeURIComponent(id)}`,
} as const;
