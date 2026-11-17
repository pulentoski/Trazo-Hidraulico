// Rutas de la aplicación.
export const PATHS = {
  home: "/",
  login: "/login",
  recover: "/recuperar",
  invitation: "/invitacion",
  ajustes: (seccion?: string) => `/ajustes${seccion ? `/${seccion}` : ""}`,
  /** Panel admin (superadministrador): resumen, organizaciones y su ficha, planes, usuarios, mapa base y sistema. */
  panel: (seccion?: string) => `/panel-admin${seccion ? `/${seccion}` : ""}`,
  panelOrg: (id: string) => `/panel-admin/organizaciones/${encodeURIComponent(id)}`,
  project: (id: string) => `/proyecto/${encodeURIComponent(id)}`,
  gestion: (id: string) => `/proyecto/${encodeURIComponent(id)}/gestion`,
} as const;
