// Encabezado de las páginas del menú (inicio, ajustes, gestión).
import { NavLink } from "react-router";
import { PATHS } from "../paths";
import { Icon } from "./Icons";
import { UserMenu } from "./UserMenu";

export function Brand() {
  return (
    <div className="brand" title="Trazo Hidráulico — diseño y simulación de redes de agua potable">
      <svg viewBox="0 0 32 32" aria-hidden><path d="M5 23 L13 12 L19 18 L27 7" /><circle cx="5" cy="23" r="2.6" /><circle cx="13" cy="12" r="2.6" /><circle cx="19" cy="18" r="2.6" /><circle cx="27" cy="7" r="2.6" /></svg>
      <span>Trazo Hidráulico</span>
    </div>
  );
}

export function PageHeader() {
  const cls = ({ isActive }: { isActive: boolean }) => `btn ghost ${isActive ? "on" : ""}`;
  return (
    <header className="page-header">
      <Brand />
      <nav aria-label="Menú principal">
        <NavLink to={PATHS.home} end className={cls}><Icon.home /><span>Inicio</span></NavLink>
        <NavLink to={PATHS.ajustes()} className={cls}><Icon.gear /><span>Ajustes</span></NavLink>
      </nav>
      <UserMenu />
    </header>
  );
}
