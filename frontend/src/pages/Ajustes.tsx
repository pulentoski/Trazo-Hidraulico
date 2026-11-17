// Ajustes (/ajustes/:seccion): una sola página con menú de secciones según el rol.
// Mi cuenta (todos) · Organización (administrador). Lo de la plataforma está en el Panel admin (/panel-admin).
import type { ReactElement } from "react";
import { Navigate, NavLink, useParams } from "react-router";
import { AppFrame } from "../components/AppFrame";
import { PATHS } from "../paths";
import { useAuth } from "../state/auth";
import { Perfil, Preferencias, Seguridad } from "./ajustes/Cuenta";
import { Auditoria, Catalogos, Criterios, DatosOrganizacion, Miembros, UsoPlan } from "./ajustes/Organizacion";

type Need = "all" | "admin";
export interface AjusteSection { id: string; label: string; group: string; need: Need; el: () => ReactElement | null }

export const SECTIONS: AjusteSection[] = [
  { id: "perfil", label: "Perfil", group: "Mi cuenta", need: "all", el: Perfil },
  { id: "seguridad", label: "Seguridad", group: "Mi cuenta", need: "all", el: Seguridad },
  { id: "preferencias", label: "Preferencias", group: "Mi cuenta", need: "all", el: Preferencias },
  { id: "organizacion", label: "Datos de la organización", group: "Organización", need: "admin", el: DatosOrganizacion },
  { id: "miembros", label: "Miembros e invitaciones", group: "Organización", need: "admin", el: Miembros },
  { id: "criterios", label: "Criterios de diseño", group: "Organización", need: "admin", el: Criterios },
  { id: "catalogos", label: "Catálogos", group: "Organización", need: "admin", el: Catalogos },
  { id: "uso", label: "Uso y plan", group: "Organización", need: "admin", el: UsoPlan },
  { id: "auditoria", label: "Auditoría", group: "Organización", need: "admin", el: Auditoria },
];

/** Secciones que antes estaban en Ajustes → Plataforma: ahora en el Panel admin. */
const MOVED_TO_PANEL: Record<string, string> = { organizaciones: "organizaciones", "mapa-base": "mapa-base", planes: "planes", sistema: "sistema", plataforma: "" };

/** Secciones visibles para el usuario de la sesión. */
export function useSections(): AjusteSection[] {
  const me = useAuth((s) => s.me);
  const admin = !!me?.orgs.some((o) => o.role === "admin");
  return SECTIONS.filter((s) => s.need === "all" || (s.need === "admin" && admin));
}

export function Ajustes() {
  const { seccion } = useParams();
  const visible = useSections();
  const me = useAuth((s) => s.me);
  if (!me) return null;
  if (seccion && seccion in MOVED_TO_PANEL) return <Navigate to={me.is_superadmin ? PATHS.panel(MOVED_TO_PANEL[seccion] || undefined) : PATHS.ajustes("perfil")} replace />;
  const cur = visible.find((s) => s.id === seccion);
  if (!cur) return <Navigate to={PATHS.ajustes("perfil")} replace />;
  const groups = [...new Set(visible.map((s) => s.group))];
  const El = cur.el;
  return (
    <AppFrame crumbs={[{ label: "Ajustes", to: PATHS.ajustes() }, { label: cur.label }]}>
      <div className="page-body ajustes">
        <h1 className="page-title">Ajustes</h1>
        <div className="ajustes-layout">
          <nav className="ajustes-nav" aria-label="Secciones de ajustes">
            {groups.map((g) => (
              <div key={g} className="ajustes-group">
                <h2>{g}</h2>
                {visible.filter((s) => s.group === g).map((s) => (
                  <NavLink key={s.id} to={PATHS.ajustes(s.id)} className={({ isActive }) => (isActive ? "on" : "")}>{s.label}</NavLink>
                ))}
              </div>
            ))}
          </nav>
          <div className="ajustes-content" key={cur.id}><El /></div>
        </div>
      </div>
    </AppFrame>
  );
}
