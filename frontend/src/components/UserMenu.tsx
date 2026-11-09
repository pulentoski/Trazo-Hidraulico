// Menú del usuario: organización activa, perfil, administración y cierre de sesión.
import { useState } from "react";
import { Link } from "react-router";
import { api } from "../api/client";
import { PATHS } from "../paths";
import { ROLE_LABEL, useAuth } from "../state/auth";
import { Icon } from "./Icons";

export function UserMenu() {
  const { me, refresh } = useAuth();
  const [open, setOpen] = useState(false);
  if (!me) return null;
  const cur = me.orgs.find((o) => o.id === me.current_org);
  const isAdmin = me.orgs.some((o) => o.role === "admin");
  return (
    <div className="menu-wrap user-menu">
      <button className="ghost" onClick={() => setOpen(!open)} aria-expanded={open} aria-label="Menú de usuario" title={me.email}>
        <span className="avatar">{(me.name || me.email)[0].toUpperCase()}</span>
        <span className="user-org">{cur ? `${cur.name} · ${ROLE_LABEL[cur.role]}` : me.email}</span>
      </button>
      {open && (
        <div className="menu-pop right" onMouseLeave={() => setOpen(false)}>
          <p className="small pad muted">{me.email}</p>
          {me.orgs.length > 1 && (
            <label className="field stacked pad"><span className="small">Organización activa</span>
              <select value={me.current_org ?? ""} onChange={async (e) => { await api.switchOrg(e.target.value); await refresh(); window.location.assign(PATHS.home); }}>
                {me.orgs.map((o) => <option key={o.id} value={o.id}>{o.name} ({ROLE_LABEL[o.role]})</option>)}
              </select></label>
          )}
          <Link className="menu-item" to={PATHS.profile} onClick={() => setOpen(false)}>Perfil y seguridad</Link>
          {isAdmin && <Link className="menu-item" to={PATHS.organization} onClick={() => setOpen(false)}>Organización</Link>}
          {me.is_superadmin && <Link className="menu-item" to={PATHS.admin} onClick={() => setOpen(false)}>Plataforma</Link>}
          <button className="menu-item" onClick={async () => { await api.logout().catch(() => undefined); window.location.assign(PATHS.login); }}>
            <Icon.back /> Cerrar sesión</button>
        </div>
      )}
    </div>
  );
}
