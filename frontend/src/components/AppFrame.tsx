// Marco de las páginas del menú (inicio, Gestión, Ajustes y Panel admin), según la maqueta principal: menú lateral
// con la marca, barra superior con migas, versión, tema, alertas y usuario, aviso del modo soporte y pie con la
// versión y el estado del sistema. El editor conserva su propia barra (no se mueven paneles ni herramientas).
import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router";
import { api } from "../api/client";
import { PATHS } from "../paths";
import { overdueOf, useAlerts } from "../state/alerts";
import { useAuth } from "../state/auth";
import { readPref, useEditor, writePref } from "../state/store";
import { Icon } from "./Icons";
import { MenuButton } from "./MenuButton";
import { Logo } from "./PageHeader";
import { UserMenu } from "./UserMenu";

export interface Crumb { label: string; to?: string }

function ThemeButton() {
  const theme = useEditor((s) => s.theme);
  const set = useEditor((s) => s.set);
  const next = theme === "dark" ? "light" : "dark";
  return (
    <button className="ghost icon-btn theme-btn" onClick={() => { set({ themePref: next, theme: next }); writePref("theme", next); }}
      title={theme === "dark" ? "Cambiar a tema claro" : "Cambiar a tema oscuro"} aria-label={theme === "dark" ? "Tema claro" : "Tema oscuro"}>
      {theme === "dark" ? <Icon.sun /> : <Icon.moon />}
    </button>
  );
}

/** Campana: mantenciones atrasadas de los proyectos de la organización (enlace a Gestión → Activos). */
function AlertsBell() {
  const { projects, load } = useAlerts();
  useEffect(() => { void load(); }, [load]);
  const late = overdueOf(projects);
  const total = late.reduce((a, p) => a + (p.overdue_tasks ?? 0), 0);
  return (
    <MenuButton menuLabel="Alertas pendientes" align="right" buttonClass="ghost icon-btn bell-btn" ariaLabel={`Alertas pendientes: ${total}`}
      title={total ? `${total} mantenciones atrasadas` : "Sin alertas pendientes"}
      label={<><Icon.bell />{total > 0 && <span className="bell-count">{total > 99 ? "99+" : total}</span>}</>}>
      {(close) => (<>
        <p className="menu-title">Alertas pendientes</p>
        {late.length === 0 ? <p className="muted small pad">Sin mantenciones atrasadas.</p> : late.map((p) => (
          <Link key={p.id} role="menuitem" className="menu-item" to={`${PATHS.gestion(p.id)}?pestana=activos`} onClick={close}>
            <Icon.wrench /><span><b>{p.name}</b> · {p.overdue_tasks} {p.overdue_tasks === 1 ? "mantención atrasada" : "mantenciones atrasadas"}</span>
          </Link>
        ))}
      </>)}
    </MenuButton>
  );
}

function SupportBanner() {
  const { me, refresh } = useAuth();
  if (!me?.support_org) return null;
  const exit = async () => { await api.supportExit().catch(() => undefined); await refresh(); window.location.assign(PATHS.panel()); };
  return (
    <div className="support-banner" role="status">
      <Icon.support /><span>Modo soporte en <b>{me.support_org.name}</b>: actúa como administrador y cada acción queda en la auditoría.</span>
      <button className="small" onClick={() => void exit()}><Icon.logout /><span>Salir del modo soporte</span></button>
    </div>
  );
}

function useHealth(): "ok" | "error" | null {
  const [st, setSt] = useState<"ok" | "error" | null>(null);
  useEffect(() => {
    let alive = true;
    const ctl = new AbortController();
    // Se lee el cuerpo para cerrar la solicitud (sin leerlo, el navegador la deja abierta).
    fetch("/api/health", { signal: ctl.signal }).then(async (r) => { await r.text(); if (alive) setSt(r.ok ? "ok" : "error"); })
      .catch(() => { if (alive) setSt("error"); });
    return () => { alive = false; ctl.abort(); };
  }, []);
  return st;
}

export function AppFrame({ crumbs, children, className }: { crumbs: Crumb[]; children: ReactNode; className?: string }) {
  const me = useAuth((s) => s.me);
  const navigate = useNavigate();
  const loc = useLocation();
  const [collapsed, setCollapsed] = useState<boolean>(() => readPref("sidebarCollapsed", typeof window !== "undefined" && window.innerWidth < 1180));
  const [mobileOpen, setMobileOpen] = useState(false);
  const health = useHealth();
  const toggle = () => {
    if (window.innerWidth < 900) { setMobileOpen(!mobileOpen); return; }
    setCollapsed(!collapsed);
    writePref("sidebarCollapsed", !collapsed);
  };
  useEffect(() => { setMobileOpen(false); }, [loc.pathname]);
  const isAdminOrg = !!me?.orgs.some((o) => o.role === "admin");
  const go = (q: string) => navigate(`${PATHS.home}${q}`);
  const item = (to: string, icon: ReactNode, label: string, end = false) => (
    <NavLink to={to} end={end} className={({ isActive }) => `nav-item ${isActive ? "on" : ""}`} title={collapsed ? label : undefined}>
      {icon}<span>{label}</span></NavLink>
  );
  const action = (icon: ReactNode, label: string, onClick: () => void, title: string) => (
    <button type="button" className="nav-item" onClick={onClick} title={collapsed ? label : title}>{icon}<span>{label}</span></button>
  );
  return (
    <div className={`frame ${collapsed ? "collapsed" : ""} ${mobileOpen ? "mobile-open" : ""} ${className ?? ""}`}>
      <aside className="sidebar" aria-label="Menú lateral">
        <Link to={PATHS.home} className="side-brand" aria-label="Trazo Hidráulico: inicio">
          <Logo size={collapsed ? 32 : 44} plain={!collapsed} />
          {!collapsed && <span className="side-brand-name"><b>Trazo</b><span>Hidráulico</span></span>}
        </Link>
        <nav className="side-nav" aria-label="Menú principal">
          {item(PATHS.home, <Icon.home />, "Inicio", true)}
          {action(<Icon.folder />, "Proyectos", () => go("#proyectos"), "Lista de proyectos")}
          {action(<Icon.upload />, "Importar .inp", () => go("?crear=importar"), "Importar un modelo de EPANET (.inp) o un proyecto .trazo")}
          {action(<Icon.csv />, "Desde Excel", () => go("?crear=excel"), "Crear un proyecto desde la planilla")}
          {item(PATHS.ajustes(), <Icon.gear />, "Ajustes")}
          {isAdminOrg && !me?.is_superadmin && item(PATHS.ajustes("organizacion"), <Icon.org />, "Organización")}
          {me?.is_superadmin && item(PATHS.panel(), <Icon.shield />, "Panel admin")}
        </nav>
        {!collapsed && (
          <div className="side-card" aria-hidden="true">
            <svg viewBox="0 0 200 50" preserveAspectRatio="none"><path d="M0 35 Q 50 15, 100 35 T 200 35 L 200 50 L 0 50 Z" /><path className="line" d="M0 40 Q 60 25, 120 40 T 200 30" /></svg>
            <b>Ingeniería</b><b>Hidráulica</b><small>Simula • Diseña • Gestiona</small>
          </div>
        )}
      </aside>
      {mobileOpen && <div className="side-overlay" onClick={() => setMobileOpen(false)} aria-hidden="true" />}
      <div className="frame-main">
        <header className="frame-header">
          <div className="fh-left">
            <button className="ghost icon-btn" onClick={toggle} aria-label={collapsed ? "Desplegar el menú lateral" : "Plegar el menú lateral"}
              title={collapsed ? "Desplegar el menú lateral" : "Plegar el menú lateral"}>{collapsed ? <Icon.sidebarOpen /> : <Icon.sidebarClose />}</button>
            <nav className="crumbs" aria-label="Ubicación">
              <Link to={PATHS.home} aria-label="Inicio"><Icon.home /></Link>
              {crumbs.map((c, i) => (
                <span key={i} className="crumb">{i > 0 && <Icon.chevronRight />}
                  {c.to && i < crumbs.length - 1 ? <Link to={c.to}>{c.label}</Link> : <span aria-current={i === crumbs.length - 1 ? "page" : undefined}>{c.label}</span>}
                </span>
              ))}
            </nav>
          </div>
          <div className="fh-right">
            <span className="status-pill version-chip" title="Versión de la aplicación"><i />v{__APP_VERSION__}</span>
            <ThemeButton />
            <AlertsBell />
            <UserMenu />
          </div>
        </header>
        <SupportBanner />
        <main className="frame-body">{children}</main>
        <footer className="frame-footer">
          <span>Trazo Hidráulico <span className="dot-sep">•</span> versión {__APP_VERSION__}</span>
          <span className={`sys-state ${health ?? ""}`}><i />{health === null ? "Comprobando el sistema…" : health === "ok" ? "Sistema: en línea" : "Sistema: con problemas"}</span>
        </footer>
      </div>
    </div>
  );
}
