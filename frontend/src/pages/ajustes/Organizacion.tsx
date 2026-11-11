// Ajustes → Organización (administrador): miembros e invitaciones, criterios de diseño por defecto, catálogos
// (tuberías, vida útil y precios por metro), uso y plan, y auditoría.
import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../../api/client";
import type { AuditOut, CatalogPipe, MemberOut, OrgSettings, Role, Usage } from "../../api/types";
import { fmt } from "../../lib/format";
import { ROLE_LABEL, useAuth } from "../../state/auth";
import { errorText } from "../../state/projects";
import { useEditor } from "../../state/store";
import { Panel, SaveButton } from "./common";

const ROLES: Role[] = ["admin", "proyectista", "revisor", "lector"];
// Valores sugeridos (los mismos del servidor): «no verificado» hasta revisarlos.
const DEFAULT_LIFE: Record<string, number> = { PVC: 50, HDPE: 50, PEAD: 50, AC: 40, Acero: 40, FFD: 60, HA: 50 };
const DEFAULT_PRICES = [{ material: "*", dn_max: 75, price_m: 45000 }, { material: "*", dn_max: 110, price_m: 60000 },
  { material: "*", dn_max: 200, price_m: 90000 }, { material: "*", dn_max: 100000, price_m: 130000 }];

/** Organización que administra el usuario: la activa si es administrador en ella; si no, la primera. */
export function useAdminOrg() {
  const me = useAuth((s) => s.me);
  return me?.orgs.find((o) => o.id === me.current_org && o.role === "admin") ?? me?.orgs.find((o) => o.role === "admin") ?? null;
}

export function UsageCard({ u }: { u: Usage }) {
  const lim = u.limits as Record<string, number | null>;
  const row = (label: string, v: number, cap: number | null | undefined, unit = "") => {
    const pct = cap ? Math.min(100, (v / cap) * 100) : null;
    return (
      <tr><td>{label}</td><td className="num">{v.toLocaleString("es-CL")}{unit}</td>
        <td className="num">{cap == null ? "sin límite" : `${cap.toLocaleString("es-CL")}${unit}`}</td>
        <td className="usage-bar-cell">{pct !== null && <span className="usage-bar"><i style={{ width: `${pct}%` }} className={pct > 90 ? "bad" : pct > 70 ? "warn" : ""} /></span>}</td></tr>
    );
  };
  return (
    <table className="tbl compact">
      <thead><tr><th>Uso ({u.month})</th><th className="num">Actual</th><th className="num">Límite del plan</th><th /></tr></thead>
      <tbody>
        {row("Proyectos", u.projects, lim.max_projects)}
        {row("Simulaciones del mes", u.simulations, lim.max_simulations_month)}
        {row("Cargas del mapa de Google", u.map_loads, lim.max_map_loads_month)}
        {row("Ortofotos", u.ortho_mb, lim.max_ortho_mb, " MB")}
      </tbody>
    </table>
  );
}

export function Miembros() {
  const me = useAuth((s) => s.me);
  const org = useAdminOrg();
  const toast = useEditor((s) => s.toast);
  const [members, setMembers] = useState<MemberOut[]>([]);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("lector");
  const [link, setLink] = useState<string | null>(null);
  const load = useCallback(async () => {
    if (org) try { setMembers(await api.members(org.id)); } catch (e) { toast(errorText(e), "error"); }
  }, [org, toast]);
  useEffect(() => { void load(); }, [load]);
  if (!org) return null;
  const act = async (f: () => Promise<unknown>, ok?: string) => { try { await f(); await load(); if (ok) toast(ok); } catch (e) { toast(errorText(e), "error"); } };
  return (
    <Panel id="miembros" title="Miembros e invitaciones" description={`Personas de «${org.name}», su rol y acceso. Los cambios de rol se aplican al instante.`}>
      <div className="table-scroll">
        <table className="tbl compact">
          <thead><tr><th>Correo</th><th>Rol</th><th>TOTP</th><th>Último ingreso</th><th /></tr></thead>
          <tbody>{members.map((m) => (
            <tr key={m.user_id} className={m.active ? "" : "muted"}>
              <td>{m.email}<div className="muted small">{m.name}</div></td>
              <td><select value={m.role} disabled={m.user_id === me?.id} aria-label={`Rol de ${m.email}`}
                onChange={(e) => void act(() => api.updateMember(org.id, m.user_id, { role: e.target.value as Role }), "Rol guardado.")}>
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
      </div>
      <h3>Invitar</h3>
      <form className="toolbar wrap" onSubmit={(e) => { e.preventDefault(); void act(async () => { const r = await api.invite(org.id, email, role, true); setLink(r.link); toast(r.emailed ? "Invitación enviada por correo." : "Comparta el enlace de invitación."); setEmail(""); }); }}>
        <input type="email" required placeholder="correo@dominio.cl" value={email} onChange={(e) => setEmail(e.target.value)} aria-label="Correo a invitar" />
        <select value={role} onChange={(e) => setRole(e.target.value as Role)} aria-label="Rol">{ROLES.map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}</select>
        <button className="small primary">Invitar</button>
      </form>
      {link && <p className="small">Enlace de un solo uso: <input className="mono link-box" readOnly value={link} onFocus={(e) => e.target.select()} aria-label="Enlace" /></p>}
    </Panel>
  );
}

function useOrgSettings(orgId: string | undefined) {
  const toast = useEditor((s) => s.toast);
  const [saved, setSaved] = useState<OrgSettings | null>(null);
  const [st, setSt] = useState<OrgSettings | null>(null);
  useEffect(() => {
    if (!orgId) return;
    api.orgSettings(orgId).then((s) => { setSaved(s); setSt(s); }).catch((e) => toast(errorText(e), "error"));
  }, [orgId, toast]);
  const save = async () => {
    if (!orgId || !st) return;
    const s = await api.saveOrgSettings(orgId, st);
    setSaved(s);
    setSt(s);
  };
  return { st, setSt, dirty: JSON.stringify(st) !== JSON.stringify(saved), save };
}

export function Criterios() {
  const org = useAdminOrg();
  const profiles = useEditor((s) => s.profiles);
  const { st, setSt, dirty, save } = useOrgSettings(org?.id);
  if (!org || !st) return <p className="muted">Cargando…</p>;
  const fallback = profiles.find((p) => p.id === st.default_profile_id) ?? profiles[0];
  return (
    <Panel id="criterios" title="Criterios de diseño por defecto" description="Perfil que reciben los proyectos nuevos de la organización. Cada proyecto conserva el suyo.">
      {profiles.length === 0 ? <p className="muted">Cargando perfiles…</p> : (<>
        <label className="field"><span>Perfil</span>
          <select value={fallback?.id ?? ""} aria-label="Perfil de criterios por defecto" onChange={(e) => setSt({ ...st, default_profile_id: Number(e.target.value) })}>
            {profiles.map((p) => <option key={p.id} value={p.id}>{p.name} (v{p.version}){p.verified ? "" : " · no verificado"}</option>)}
          </select>
        </label>
        {fallback && (<>
          <table className="tbl compact">
            <tbody>{fallback.criteria.map((c) => (
              <tr key={c.key}><td>{c.label}</td>
                <td className="num">{c.min != null ? `≥ ${fmt(c.min, 1)}` : ""}{c.max != null ? `≤ ${fmt(c.max, 1)}` : ""} {c.unit}</td></tr>
            ))}</tbody>
          </table>
          <p className="muted small">{fallback.source} {!fallback.verified && <span className="badge warn">no verificado</span>}</p>
        </>)}
      </>)}
      <SaveButton dirty={dirty} onSave={save} />
    </Panel>
  );
}

export function Catalogos() {
  const org = useAdminOrg();
  const { st, setSt, dirty, save } = useOrgSettings(org?.id);
  const [pipes, setPipes] = useState<CatalogPipe[]>([]);
  const [mat, setMat] = useState("");
  useEffect(() => { api.catalog().then(setPipes).catch(() => undefined); }, []);
  const materials = useMemo(() => [...new Set(pipes.map((p) => p.material))].sort(), [pipes]);
  if (!org || !st) return <p className="muted">Cargando…</p>;
  const life = st.service_life ?? DEFAULT_LIFE;
  const prices = st.prices ?? DEFAULT_PRICES;
  const mats = [...new Set([...Object.keys(DEFAULT_LIFE), ...materials, ...Object.keys(life)])].sort();
  const n = (v: string, fb: number) => { const x = Number(v.replace(",", ".")); return Number.isFinite(x) && x > 0 ? x : fb; };
  return (
    <Panel id="catalogos" title="Catálogos" description="Catálogo de tuberías (referencia de diámetros y rugosidades) y, para la organización, vida útil por material y precios de renovación por metro. Se aplican a los proyectos sin valores propios.">
      <h3>Vida útil por material</h3>
      <table className="tbl compact narrow-table">
        <thead><tr><th>Material</th><th className="num">Años</th></tr></thead>
        <tbody>{mats.map((m) => (
          <tr key={m}><td>{m}</td><td className="num">
            <input className="cell-input" inputMode="numeric" defaultValue={life[m] ?? st.default_life ?? 50} aria-label={`Vida útil ${m}`}
              onBlur={(e) => setSt({ ...st, service_life: { ...life, [m]: Math.round(n(e.target.value, life[m] ?? 50)) } })} /></td></tr>))}</tbody>
      </table>
      <label className="check small"><input type="checkbox" checked={!!st.life_verified} onChange={(e) => setSt({ ...st, service_life: life, life_verified: e.target.checked })} />
        Vida útil revisada (sin marcar = «no verificado»)</label>
      <h3>Precios de renovación por metro</h3>
      <table className="tbl compact narrow-table">
        <thead><tr><th>Material («*» = cualquiera)</th><th className="num">DN máximo (mm)</th><th className="num">CLP/m</th><th /></tr></thead>
        <tbody>{prices.map((p, i) => (
          <tr key={`${i}-${p.material}-${p.dn_max}`}>
            <td><input className="cell-input" defaultValue={p.material} aria-label={`Material del precio ${i + 1}`}
              onBlur={(e) => setSt({ ...st, prices: prices.map((x, k) => (k === i ? { ...x, material: e.target.value || "*" } : x)) })} /></td>
            <td className="num"><input className="cell-input" inputMode="numeric" defaultValue={p.dn_max} aria-label={`DN máximo del precio ${i + 1}`}
              onBlur={(e) => setSt({ ...st, prices: prices.map((x, k) => (k === i ? { ...x, dn_max: Math.round(n(e.target.value, p.dn_max)) } : x)) })} /></td>
            <td className="num"><input className="cell-input" inputMode="numeric" defaultValue={p.price_m} aria-label={`Precio por metro ${i + 1}`}
              onBlur={(e) => setSt({ ...st, prices: prices.map((x, k) => (k === i ? { ...x, price_m: n(e.target.value, p.price_m) } : x)) })} /></td>
            <td><button className="ghost small" onClick={() => setSt({ ...st, prices: prices.filter((_, k) => k !== i) })} aria-label="Quitar precio">✕</button></td>
          </tr>))}</tbody>
      </table>
      <div className="toolbar plain">
        <button className="small" onClick={() => setSt({ ...st, prices: [...prices, { material: "*", dn_max: 110, price_m: 60000 }] })}>+ Precio</button>
        <label className="check small"><input type="checkbox" checked={!!st.prices_verified} onChange={(e) => setSt({ ...st, prices, prices_verified: e.target.checked })} />
          Precios revisados</label>
      </div>
      <SaveButton dirty={dirty} onSave={save} />
      <h3>Catálogo de tuberías <span className="muted small">({pipes.length})</span></h3>
      <label className="field"><span>Material</span>
        <select value={mat} onChange={(e) => setMat(e.target.value)} aria-label="Filtrar catálogo por material">
          <option value="">Todos</option>{materials.map((m) => <option key={m}>{m}</option>)}</select></label>
      <div className="table-scroll catalog-table">
        <table className="tbl compact">
          <thead><tr><th>Material</th><th>Norma</th><th className="num">DN</th><th>Clase</th><th className="num">D int. (mm)</th><th className="num">C H-W</th><th className="num">ε (mm)</th><th>Verificado</th></tr></thead>
          <tbody>{pipes.filter((p) => !mat || p.material === mat).map((p) => (
            <tr key={p.id}><td>{p.material}</td><td className="small">{p.standard}</td><td className="num">{p.dn}</td><td>{p.pipe_class}</td>
              <td className="num">{fmt(p.inner_diameter_mm, 1)}</td><td className="num">{fmt(p.hw_c, 0)}</td><td className="num">{fmt(p.dw_roughness_mm, 3)}</td>
              <td>{p.verified ? "sí" : <span className="badge warn">no verificado</span>}</td></tr>))}</tbody>
        </table>
      </div>
    </Panel>
  );
}

export function UsoPlan() {
  const org = useAdminOrg();
  const [usage, setUsage] = useState<Usage | null>(null);
  const toast = useEditor((s) => s.toast);
  useEffect(() => { if (org) api.orgUsage(org.id).then(setUsage).catch((e) => toast(errorText(e), "error")); }, [org, toast]);
  if (!org) return null;
  return (
    <Panel id="uso" title="Uso y plan" description="Consumo del mes de la organización contra los límites de su plan. El plan lo cambia el superadministrador.">
      {usage ? <UsageCard u={usage} /> : <p className="muted">Cargando…</p>}
    </Panel>
  );
}

export function Auditoria() {
  const org = useAdminOrg();
  const toast = useEditor((s) => s.toast);
  const [audit, setAudit] = useState<AuditOut[]>([]);
  const [filter, setFilter] = useState("");
  useEffect(() => { if (org) api.audit(org.id, filter || undefined).then(setAudit).catch((e) => toast(errorText(e), "error")); }, [org, filter, toast]);
  if (!org) return null;
  return (
    <Panel id="auditoria" title="Auditoría" description="Quién hizo qué y cuándo: ingresos, cambios de red, importaciones, exportaciones, permisos y revisiones.">
      <div className="toolbar">
        <select value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Filtrar">
          <option value="">Todo</option><option value="login">Ingresos</option><option value="red">Cambios de red</option>
          <option value="importacion">Importaciones</option><option value="exportacion">Exportaciones</option><option value="permiso">Permisos</option>
          <option value="revision">Revisiones</option><option value="gestion">Gestión</option>
        </select>
      </div>
      <div className="table-scroll">
        <table className="tbl compact">
          <thead><tr><th>Fecha</th><th>Usuario</th><th>Acción</th><th>Proyecto</th><th>Versión</th><th>Detalle</th></tr></thead>
          <tbody>{audit.map((a) => (
            <tr key={a.id}><td className="small">{new Date(a.created_at).toLocaleString("es-CL")}</td><td>{a.user_email ?? "—"}</td><td className="mono">{a.action}</td>
              <td className="mono small">{a.project_id?.slice(0, 8) ?? ""}</td><td>{a.version ?? ""}</td>
              <td className="small">{a.detail ? Object.entries(a.detail).filter(([, v]) => v !== null && v !== "").map(([k, v]) => `${k}: ${typeof v === "object" ? JSON.stringify(v) : v}`).join(" · ") : ""}</td></tr>
          ))}</tbody>
        </table>
      </div>
    </Panel>
  );
}
