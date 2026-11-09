// Plataforma (superadministrador): organizaciones, uso, planes y límites, suspensión de cuentas.
import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { OrgAdminOut, UserAdminOut } from "../api/types";
import { PageHeader } from "../components/PageHeader";
import { ROLE_LABEL } from "../state/auth";
import { errorText } from "../state/projects";
import { useEditor } from "../state/store";
import { UsageCard } from "./Organization";

type Plan = "basico" | "profesional" | "ilimitado";

export function Platform() {
  const toast = useEditor((s) => s.toast);
  const [orgs, setOrgs] = useState<OrgAdminOut[]>([]);
  const [users, setUsers] = useState<UserAdminOut[]>([]);
  const [name, setName] = useState("");
  const [adminEmail, setAdminEmail] = useState("");
  const [link, setLink] = useState<string | null>(null);
  const load = useCallback(async () => {
    try { const [o, u] = await Promise.all([api.adminOrgs(), api.adminUsers()]); setOrgs(o); setUsers(u); } catch (e) { toast(errorText(e), "error"); }
  }, [toast]);
  useEffect(() => { void load(); }, [load]);
  const act = async (f: () => Promise<unknown>) => { try { await f(); await load(); } catch (e) { toast(errorText(e), "error"); } };
  return (
    <div className="page">
      <PageHeader />
      <main className="page-body">
        <h1 className="page-title">Plataforma</h1>
        <section className="card">
          <h2>Nueva organización</h2>
          <form className="toolbar wrap" onSubmit={(e) => { e.preventDefault(); void act(async () => { const r = await api.adminCreateOrg({ name, admin_email: adminEmail || null }); setLink(r.admin_invitation ?? null); setName(""); setAdminEmail(""); }); }}>
            <input required placeholder="Nombre (APR, consultora, sanitaria)" value={name} onChange={(e) => setName(e.target.value)} aria-label="Nombre de la organización" />
            <input type="email" placeholder="Correo del administrador (opcional)" value={adminEmail} onChange={(e) => setAdminEmail(e.target.value)} aria-label="Correo del administrador" />
            <button className="small primary">Crear</button>
          </form>
          {link && <p className="small">Invitación del administrador: <input className="mono link-box" readOnly value={link} onFocus={(e) => e.target.select()} aria-label="Enlace" /></p>}
        </section>
        <div className="org-cards">
          {orgs.map((o) => (
            <section key={o.id} className={`card ${o.suspended ? "suspended" : ""}`}>
              <h2>{o.name} {o.suspended && <span className="badge warn">suspendida</span>}</h2>
              <div className="toolbar wrap">
                <label className="field inline"><span>Plan</span>
                  <select value={o.plan} onChange={(e) => void act(() => api.adminUpdateOrg(o.id, { plan: e.target.value as Plan }))}>
                    <option value="basico">Básico</option><option value="profesional">Profesional</option><option value="ilimitado">Ilimitado</option></select></label>
                <span className="muted small">{o.members} miembros</span>
                <button className="small ghost" onClick={() => void act(() => api.adminUpdateOrg(o.id, { suspended: !o.suspended }))}>{o.suspended ? "Reactivar" : "Suspender"}</button>
              </div>
              <UsageCard u={o.usage} />
              <details><summary className="small">Límites personalizados</summary>
                <form className="grid2" onSubmit={(e) => {
                  e.preventDefault();
                  const f = new FormData(e.currentTarget);
                  const limits: Record<string, number | null> = {};
                  for (const k of ["max_projects", "max_simulations_month", "max_map_loads_month", "max_ortho_mb"]) {
                    const v = String(f.get(k) ?? "").trim();
                    if (v !== "") limits[k] = Number(v);
                  }
                  void act(() => api.adminUpdateOrg(o.id, { limits }));
                }}>
                  {["max_projects", "max_simulations_month", "max_map_loads_month", "max_ortho_mb"].map((k) => (
                    <label key={k} className="field stacked"><span className="small">{k}</span>
                      <input name={k} inputMode="numeric" defaultValue={String((o.limits as Record<string, number> | null)?.[k] ?? "")} placeholder="según el plan" /></label>
                  ))}
                  <button className="small">Guardar límites</button>
                </form>
              </details>
            </section>
          ))}
        </div>
        <section className="card">
          <h2>Cuentas</h2>
          <table className="tbl compact">
            <thead><tr><th>Correo</th><th>Organizaciones</th><th>TOTP</th><th>Estado</th><th></th></tr></thead>
            <tbody>{users.map((u) => (
              <tr key={u.id} className={u.active ? "" : "muted"}>
                <td>{u.email}{u.is_superadmin ? " · superadmin" : ""}</td>
                <td className="small">{u.orgs.map((o) => `${o.name} (${ROLE_LABEL[o.role]})`).join(", ")}</td>
                <td>{u.mfa_enabled ? "sí" : "no"}</td>
                <td>{u.active ? (u.locked ? "bloqueada" : "activa") : "suspendida"}</td>
                <td className="right">
                  <button className="small ghost" onClick={() => void act(() => api.adminUpdateUser(u.id, !u.active))}>{u.active ? "Suspender" : "Reactivar"}</button>
                  <button className="small ghost" onClick={async () => { try { setLink((await api.adminResetLink(u.id)).link); } catch (e) { toast(errorText(e), "error"); } }}>Enlace de contraseña</button>
                </td>
              </tr>
            ))}</tbody>
          </table>
        </section>
      </main>
    </div>
  );
}
