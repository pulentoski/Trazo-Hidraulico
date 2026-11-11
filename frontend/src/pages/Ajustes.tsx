// Ajustes (/ajustes/:seccion): una sola página con menú lateral y secciones según el rol.
// Mi cuenta (todos) · Organización (administrador) · Plataforma (superadministrador).
import type { ReactElement } from "react";
import { Navigate, NavLink, useParams } from "react-router";
import { PageFooter } from "../components/PageFooter";
import { PageHeader } from "../components/PageHeader";
import { PATHS } from "../paths";
import { useAuth } from "../state/auth";
import { Perfil, Preferencias, Seguridad } from "./ajustes/Cuenta";
import { Auditoria, Catalogos, Criterios, Miembros, UsoPlan } from "./ajustes/Organizacion";
import { MapaBase, Organizaciones, Planes, Sistema } from "./ajustes/Plataforma";

type Need = "all" | "admin" | "super";
export interface AjusteSection { id: string; label: string; group: string; need: Need; el: () => ReactElement | null }

export const SECTIONS: AjusteSection[] = [
  { id: "perfil", label: "Perfil", group: "Mi cuenta", need: "all", el: Perfil },
  { id: "seguridad", label: "Seguridad", group: "Mi cuenta", need: "all", el: Seguridad },
  { id: "preferencias", label: "Preferencias", group: "Mi cuenta", need: "all", el: Preferencias },
  { id: "miembros", label: "Miembros e invitaciones", group: "Organización", need: "admin", el: Miembros },
  { id: "criterios", label: "Criterios de diseño", group: "Organización", need: "admin", el: Criterios },
  { id: "catalogos", label: "Catálogos", group: "Organización", need: "admin", el: Catalogos },
  { id: "uso", label: "Uso y plan", group: "Organización", need: "admin", el: UsoPlan },
  { id: "auditoria", label: "Auditoría", group: "Organización", need: "admin", el: Auditoria },
  { id: "organizaciones", label: "Organizaciones", group: "Plataforma", need: "super", el: Organizaciones },
  { id: "mapa-base", label: "Mapa base", group: "Plataforma", need: "super", el: MapaBase },
  { id: "planes", label: "Planes y límites", group: "Plataforma", need: "super", el: Planes },
  { id: "sistema", label: "Sistema", group: "Plataforma", need: "super", el: Sistema },
];

/** Secciones visibles para el usuario de la sesión. */
export function useSections(): AjusteSection[] {
  const me = useAuth((s) => s.me);
  const admin = !!me?.orgs.some((o) => o.role === "admin");
  const sup = !!me?.is_superadmin;
  return SECTIONS.filter((s) => s.need === "all" || (s.need === "admin" && admin) || (s.need === "super" && sup));
}

export function Ajustes() {
  const { seccion } = useParams();
  const visible = useSections();
  const me = useAuth((s) => s.me);
  if (!me) return null;
  const cur = visible.find((s) => s.id === seccion);
  if (!cur) return <Navigate to={PATHS.ajustes("perfil")} replace />;
  const groups = [...new Set(visible.map((s) => s.group))];
  const El = cur.el;
  return (
    <div className="page">
      <PageHeader />
      <main className="page-body ajustes">
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
      </main>
      <PageFooter />
    </div>
  );
}
