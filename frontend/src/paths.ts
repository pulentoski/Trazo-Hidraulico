// Rutas de la aplicación.
export const PATHS = {
  home: "/",
  login: "/login",
  recover: "/recuperar",
  invitation: "/invitacion",
  profile: "/perfil",
  organization: "/organizacion",
  admin: "/plataforma",
  settings: "/configuracion",
  about: "/acerca-de",
  project: (id: string) => `/proyecto/${encodeURIComponent(id)}`,
} as const;
