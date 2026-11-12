// Encabezado de las páginas del menú (inicio, ajustes, gestión).
import { NavLink } from "react-router";
import { PATHS } from "../paths";
import { Icon } from "./Icons";
import { UserMenu } from "./UserMenu";

/** Logo de Trazo: una gota con una red de tres nudos (el último, en el acento cálido). */
export function Logo({ size = 28 }: { size?: number }) {
  return (
    <svg className="logo" viewBox="0 0 32 32" width={size} height={size} aria-hidden="true" focusable="false">
      <rect className="logo-bg" width="32" height="32" rx="8" />
      <path className="logo-drop" d="M16 4.5c-4.2 5-8 9.6-8 14.2a8 8 0 0 0 16 0c0-4.6-3.8-9.2-8-14.2z" />
      <path className="logo-net" d="M11.8 21.4l4.2-4.6 4.2 3.2" />
      <circle className="logo-node" cx="11.8" cy="21.4" r="1.7" />
      <circle className="logo-node" cx="16" cy="16.8" r="1.7" />
      <circle className="logo-node warm" cx="20.2" cy="20" r="1.7" />
    </svg>
  );
}

export function Brand({ big = false }: { big?: boolean }) {
  return (
    <div className={`brand ${big ? "big" : ""}`} title="Trazo Hidráulico — diseño y simulación de redes de agua potable">
      <Logo size={big ? 44 : 28} />
      <span className="brand-name"><b>Trazo</b> Hidráulico</span>
    </div>
  );
}

export function PageHeader() {
  const cls = ({ isActive }: { isActive: boolean }) => `btn ghost ${isActive ? "on" : ""}`;
  return (
    <header className="page-header">
      <NavLink to={PATHS.home} className="brand-link" aria-label="Trazo Hidráulico: menú principal"><Brand /></NavLink>
      <nav aria-label="Menú principal">
        <NavLink to={PATHS.home} end className={cls} title="Menú principal"><Icon.home /><span>Inicio</span></NavLink>
        <NavLink to={PATHS.ajustes()} className={cls} title="Ajustes de la cuenta, la organización y la plataforma"><Icon.gear /><span>Ajustes</span></NavLink>
      </nav>
      <UserMenu />
    </header>
  );
}
