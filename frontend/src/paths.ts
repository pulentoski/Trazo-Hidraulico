// Rutas de la aplicación.
export const PATHS = {
  home: "/",
  login: "/login",
  recover: "/recuperar",
  invitation: "/invitacion",
  ajustes: (seccion?: string) => `/ajustes${seccion ? `/${seccion}` : ""}`,
  project: (id: string) => `/proyecto/${encodeURIComponent(id)}`,
  gestion: (id: string) => `/proyecto/${encodeURIComponent(id)}/gestion`,
} as const;
