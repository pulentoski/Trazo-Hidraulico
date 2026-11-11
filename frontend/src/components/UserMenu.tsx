// Menú del usuario: identidad, organización activa, perfil, administración y cierre de sesión.
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import { api } from "../api/client";
import { PATHS } from "../paths";
import { ROLE_LABEL, useAuth } from "../state/auth";
import { Icon } from "./Icons";

export function UserMenu() {
  const { me, refresh } = useAuth();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const down = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    const key = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("mousedown", down);
    window.addEventListener("keydown", key);
    return () => { window.removeEventListener("mousedown", down); window.removeEventListener("keydown", key); };
  }, [open]);
  if (!me) return null;
  const cur = me.orgs.find((o) => o.id === me.current_org);
  const isAdmin = me.orgs.some((o) => o.role === "admin");
  const initial = (me.name || me.email)[0].toUpperCase();
  return (
    <div className="menu-wrap user-menu" ref={ref}>
      <button className="ghost" onClick={() => setOpen(!open)} aria-expanded={open} aria-haspopup="menu" aria-label="Menú de usuario" title={me.email}>
        <span className="avatar">{initial}</span>
        <span className="user-org">{cur ? `${cur.name} · ${ROLE_LABEL[cur.role]}` : me.email}</span>
        <span className="caret" aria-hidden>▾</span>
      </button>
      {open && (
        <div className="menu-pop right user-pop" role="menu">
          <div className="user-head">
            <span className="avatar big">{initial}</span>
            <div><b>{me.name || me.email.split("@")[0]}</b><span className="muted small">{me.email}</span>
              {cur && <span className="muted small">{cur.name} · {ROLE_LABEL[cur.role]}</span>}</div>
          </div>
          {me.orgs.length > 1 && (
            <label className="field stacked pad"><span className="small">Organización activa</span>
              <select value={me.current_org ?? ""} onChange={async (e) => { await api.switchOrg(e.target.value); await refresh(); window.location.assign(PATHS.home); }}>
                {me.orgs.map((o) => <option key={o.id} value={o.id}>{o.name} ({ROLE_LABEL[o.role]})</option>)}
              </select></label>
          )}
          <Link className="menu-item" role="menuitem" to={PATHS.profile} onClick={() => setOpen(false)}><Icon.user /> Perfil y seguridad</Link>
          {isAdmin && <Link className="menu-item" role="menuitem" to={PATHS.organization} onClick={() => setOpen(false)}><Icon.org /> Organización</Link>}
          {me.is_superadmin && <Link className="menu-item" role="menuitem" to={PATHS.admin} onClick={() => setOpen(false)}><Icon.gear /> Plataforma</Link>}
          <div className="menu-sep" />
          <button className="menu-item" role="menuitem" onClick={async () => { await api.logout().catch(() => undefined); window.location.assign(PATHS.login); }}>
            <Icon.back /> Cerrar sesión</button>
        </div>
      )}
    </div>
  );
}
