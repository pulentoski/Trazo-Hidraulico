// Organización (administrador): miembros, invitaciones, roles, auditoría y uso del plan.
import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { AuditOut, MemberOut, Role, Usage } from "../api/types";
import { PageHeader } from "../components/PageHeader";
import { ROLE_LABEL, useAuth } from "../state/auth";
import { errorText } from "../state/projects";
import { useEditor } from "../state/store";

const ROLES: Role[] = ["admin", "proyectista", "revisor", "lector"];

function UsageCard({ u }: { u: Usage }) {
  const lim = u.limits as Record<string, number | null>;
  const row = (label: string, v: number, cap: number | null | undefined, unit = "") => (
    <tr><td>{label}</td><td className="num">{v.toLocaleString("es-CL")}{unit}</td><td className="num">{cap == null ? "sin límite" : `${cap.toLocaleString("es-CL")}${unit}`}</td></tr>
  );
  return (
    <table className="tbl compact">
      <thead><tr><th>Uso ({u.month})</th><th className="num">Actual</th><th className="num">Límite del plan</th></tr></thead>
      <tbody>
        {row("Proyectos", u.projects, lim.max_projects)}
        {row("Simulaciones del mes", u.simulations, lim.max_simulations_month)}
        {row("Cargas del mapa de Google", u.map_loads, lim.max_map_loads_month)}
        {row("Ortofotos", u.ortho_mb, lim.max_ortho_mb, " MB")}
      </tbody>
    </table>
  );
}

export function Organization() {
  const { me } = useAuth();
  const toast = useEditor((s) => s.toast);
  const org = me?.orgs.find((o) => o.id === me.current_org && o.role === "admin") ?? me?.orgs.find((o) => o.role === "admin");
  const [members, setMembers] = useState<MemberOut[]>([]);
  const [audit, setAudit] = useState<AuditOut[]>([]);
  const [usage, setUsage] = useState<Usage | null>(null);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("lector");
  const [link, setLink] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const load = useCallback(async () => {
    if (!org) return;
    try {
      const [m, a, u] = await Promise.all([api.members(org.id), api.audit(org.id, filter || undefined), api.orgUsage(org.id)]);
      setMembers(m); setAudit(a); setUsage(u);
    } catch (e) { toast(errorText(e), "error"); }
  }, [org, filter, toast]);
  useEffect(() => { void load(); }, [load]);
  if (!org) return <div className="page"><PageHeader /><main className="page-body narrow"><p className="muted">Solo los administradores de una organización ven esta página.</p></main></div>;
  const act = async (f: () => Promise<unknown>) => { try { await f(); await load(); } catch (e) { toast(errorText(e), "error"); } };
  return (
    <div className="page">
      <PageHeader />
      <main className="page-body">
        <h1 className="page-title">{org.name}</h1>
        <div className="org-grid">
          <section className="card">
            <h2>Miembros</h2>
            <table className="tbl compact">
              <thead><tr><th>Correo</th><th>Rol</th><th>TOTP</th><th>Último ingreso</th><th></th></tr></thead>
              <tbody>{members.map((m) => (
                <tr key={m.user_id} className={m.active ? "" : "muted"}>
                  <td>{m.email}<div className="muted small">{m.name}</div></td>
                  <td><select value={m.role} disabled={m.user_id === me?.id} aria-label={`Rol de ${m.email}`}
                    onChange={(e) => void act(() => api.updateMember(org.id, m.user_id, { role: e.target.value as Role }))}>
                    {ROLES.map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}</select></td>
                  <td>{m.mfa_enabled ? "sí" : "no"}</td>
                  <td className="small">{m.last_login_at ? new Date(m.last_login_at).toLocaleString("es-CL") : "—"}</td>
                  <td className="right">
                    {m.user_id !== me?.id && <button className="small ghost" onClick={() => void act(() => api.updateMember(org.id, m.user_id, { active: !m.active }))}>{m.active ? "Desactivar" : "Activar"}</button>}
                    <button className="small ghost" onClick={async () => { try { setLink((await api.memberResetLink(org.id, m.user_id)).link); } catch (e) { toast(errorText(e), "error"); } }}>Enlace de contraseña</button>
                  </td>
                </tr>
              ))}</tbody>
            </table>
            <form className="toolbar wrap" onSubmit={(e) => { e.preventDefault(); void act(async () => { const r = await api.invite(org.id, email, role, true); setLink(r.link); toast(r.emailed ? "Invitación enviada por correo." : "Comparta el enlace de invitación."); setEmail(""); }); }}>
              <input type="email" required placeholder="correo@dominio.cl" value={email} onChange={(e) => setEmail(e.target.value)} aria-label="Correo a invitar" />
              <select value={role} onChange={(e) => setRole(e.target.value as Role)} aria-label="Rol">{ROLES.map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}</select>
              <button className="small primary">Invitar</button>
            </form>
            {link && <p className="small">Enlace de un solo uso: <input className="mono link-box" readOnly value={link} onFocus={(e) => e.target.select()} aria-label="Enlace" /></p>}
          </section>
          <section className="card">
            <h2>Uso y plan</h2>
            {usage && <UsageCard u={usage} />}
          </section>
        </div>
        <section className="card">
          <h2>Auditoría</h2>
          <div className="toolbar">
            <select value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Filtrar">
              <option value="">Todo</option><option value="login">Ingresos</option><option value="red">Cambios de red</option>
              <option value="importacion">Importaciones</option><option value="exportacion">Exportaciones</option><option value="permiso">Permisos</option>
              <option value="revision">Revisiones</option>
            </select>
          </div>
          <table className="tbl compact">
            <thead><tr><th>Fecha</th><th>Usuario</th><th>Acción</th><th>Proyecto</th><th>Versión</th><th>Detalle</th></tr></thead>
            <tbody>{audit.map((a) => (
              <tr key={a.id}><td className="small">{new Date(a.created_at).toLocaleString("es-CL")}</td><td>{a.user_email ?? "—"}</td><td className="mono">{a.action}</td>
                <td className="mono small">{a.project_id?.slice(0, 8) ?? ""}</td><td>{a.version ?? ""}</td>
                <td className="small">{a.detail ? Object.entries(a.detail).filter(([, v]) => v !== null && v !== "").map(([k, v]) => `${k}: ${typeof v === "object" ? JSON.stringify(v) : v}`).join(" · ") : ""}</td></tr>
            ))}</tbody>
          </table>
        </section>
      </main>
    </div>
  );
}

export { UsageCard };
