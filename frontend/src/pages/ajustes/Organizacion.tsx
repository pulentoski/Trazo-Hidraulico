// Ajustes → Organización (administrador): datos de la organización, miembros e invitaciones (con el tope de usuarios
// del plan), criterios de diseño por defecto, catálogos (tuberías, vida útil y precios por metro), uso y plan, y
// auditoría. Las reglas (rol máximo, último administrador, límites) las valida el backend.
import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../../api/client";
import type { AuditOut, CatalogPipe, InvitationOut, MemberOut, OrgDataUpdate, OrgInfo, OrgOut, OrgSettings, Role, Usage } from "../../api/types";
import { DataTable } from "../../components/DataTable";
import { fmt } from "../../lib/format";
import { ROLE_LABEL, useAuth } from "../../state/auth";
import { errorText } from "../../state/projects";
import { useEditor } from "../../state/store";
import { Panel, SaveButton } from "./common";
import { Icon } from "../../components/Icons";
import { Skeleton } from "../../components/Skeleton";

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

export const LIMIT_ROWS: { key: string; label: string; used: (u: Usage) => number; unit?: string }[] = [
  { key: "max_users", label: "Usuarios", used: (u) => u.users ?? 0 },
  { key: "max_projects", label: "Proyectos", used: (u) => u.projects },
  { key: "max_simulations_month", label: "Simulaciones del mes", used: (u) => u.simulations },
  { key: "max_map_loads_month", label: "Cargas del mapa de Google", used: (u) => u.map_loads },
  { key: "max_ortho_mb", label: "Ortofotos", used: (u) => u.ortho_mb, unit: " MB" },
  { key: "max_invites_day", label: "Invitaciones de hoy", used: (u) => u.invitations_today ?? 0 },
];

/** Barra de uso contra el límite (verde, ámbar desde 70 %, rojo desde 90 %). */
export function UsageBar({ used, cap }: { used: number; cap: number | null | undefined }) {
  if (cap == null) return <span className="muted small">sin límite</span>;
  const pct = cap ? Math.min(100, (used / cap) * 100) : 100;
  return <span className="usage-bar" role="img" aria-label={`${fmt(pct, 0)} % usado`}><i style={{ width: `${pct}%` }} className={pct >= 90 ? "bad" : pct >= 70 ? "warn" : ""} /></span>;
}

export function UsageCard({ u }: { u: Usage }) {
  const lim = u.limits as Record<string, number | null>;
  return (
    <>
      <div className="usage-grid">
        {LIMIT_ROWS.map((r) => {
          const v = r.used(u);
          const cap = lim[r.key];
          return (
            <div key={r.key} className="usage-tile" data-limit={r.key}>
              <span className="muted small">{r.label}</span>
              <b>{v.toLocaleString("es-CL")}{r.unit ?? ""} <span className="muted">/ {cap == null ? "∞" : `${cap.toLocaleString("es-CL")}${r.unit ?? ""}`}</span></b>
              <UsageBar used={v} cap={cap} />
            </div>
          );
        })}
      </div>
      <p className="muted small">Mes {u.month} · {u.pending_invitations ?? 0} invitaciones vigentes (vencen a los {u.invite_days ?? 7} días).</p>
    </>
  );
}

const KIND_LABEL: Record<string, string> = { apr: "APR (comité o cooperativa)", consultora: "Consultora", sanitaria: "Sanitaria", otra: "Otra" };
const INFO_FIELDS: { key: keyof OrgInfo; label: string; ph?: string; type?: string }[] = [
  { key: "rut", label: "RUT", ph: "76.123.456-7" }, { key: "region", label: "Región", ph: "Coquimbo" },
  { key: "comuna", label: "Comuna", ph: "Vicuña" }, { key: "address", label: "Dirección", ph: "Calle y número" },
  { key: "contact", label: "Persona de contacto" }, { key: "phone", label: "Teléfono", ph: "+56 9 …" },
  { key: "email", label: "Correo de contacto", ph: "contacto@apr.cl", type: "email" },
];

/** Datos de la organización (nombre, tipo y contacto). El plan, los límites y la suspensión los cambia el superadministrador. */
export function DatosOrganizacion() {
  const org = useAdminOrg();
  const refresh = useAuth((s) => s.refresh);
  const [saved, setSaved] = useState<OrgOut | null>(null);
  const [form, setForm] = useState<{ name: string; kind: string; info: OrgInfo }>({ name: "", kind: "apr", info: {} });
  const toast = useEditor((s) => s.toast);
  useEffect(() => {
    if (!org) return;
    api.orgData(org.id).then((o) => { setSaved(o); setForm({ name: o.name, kind: o.kind, info: (o.info ?? {}) as OrgInfo }); })
      .catch((e) => toast(errorText(e), "error"));
  }, [org, toast]);
  if (!org) return null;
  if (!saved) return <Skeleton />;
  const dirty = JSON.stringify(form) !== JSON.stringify({ name: saved.name, kind: saved.kind, info: saved.info ?? {} });
  return (
    <Panel id="organizacion" title="Datos de la organización" description="Nombre, tipo y datos de contacto. El plan y sus límites los administra el Super Admin.">
      <div className="form-grid two">
        <label className="field stacked"><span>Nombre</span>
          <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required minLength={2} maxLength={200} /></label>
        <label className="field stacked"><span>Tipo</span>
          <select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>
            {Object.entries(KIND_LABEL).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
        {INFO_FIELDS.map((f) => (
          <label key={f.key} className="field stacked"><span>{f.label}</span>
            <input type={f.type ?? "text"} value={form.info[f.key] ?? ""} placeholder={f.ph}
              onChange={(e) => setForm({ ...form, info: { ...form.info, [f.key]: e.target.value } })} /></label>
        ))}
      </div>
      <dl className="kv compact"><dt>Plan</dt><dd>{PLAN_LABEL[saved.plan] ?? saved.plan} <span className="muted small">(lo cambia el Super Admin)</span></dd></dl>
      <SaveButton dirty={dirty} onSave={async () => {
        const o = await api.updateOrgData(org.id, { name: form.name.trim(), kind: form.kind as OrgDataUpdate["kind"], info: form.info });
        setSaved(o);
        await refresh();
      }} />
    </Panel>
  );
}

export const PLAN_LABEL: Record<string, string> = { basico: "Básico", profesional: "Profesional", ilimitado: "Ilimitado" };
export const ROLE_RANK: Record<Role, number> = { lector: 1, revisor: 2, proyectista: 3, admin: 4 };

export function Miembros() {
  const me = useAuth((s) => s.me);
  const org = useAdminOrg();
  const toast = useEditor((s) => s.toast);
  const [members, setMembers] = useState<MemberOut[]>([]);
  const [invites, setInvites] = useState<InvitationOut[]>([]);
  const [usage, setUsage] = useState<Usage | null>(null);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("lector");
  const [link, setLink] = useState<string | null>(null);
  const load = useCallback(async () => {
    if (!org) return;
    try {
      const [m, i, u] = await Promise.all([api.members(org.id), api.invitations(org.id), api.orgUsage(org.id)]);
      setMembers(m); setInvites(i); setUsage(u);
    } catch (e) { toast(errorText(e), "error"); }
  }, [org, toast]);
  useEffect(() => { void load(); }, [load]);
  if (!org) return null;
  const act = async (f: () => Promise<unknown>, ok?: string) => { try { await f(); await load(); if (ok) toast(ok); } catch (e) { toast(errorText(e), "error"); } };
  // Roles asignables: hasta el propio (el Super Admin, todos).
  const myRank = me?.is_superadmin ? 9 : ROLE_RANK[org.role];
  const assignable = ROLES.filter((r) => ROLE_RANK[r] <= myRank);
  const maxUsers = (usage?.limits as Record<string, number | null> | undefined)?.max_users ?? null;
  const maxDay = (usage?.limits as Record<string, number | null> | undefined)?.max_invites_day ?? null;
  const used = (usage?.users ?? 0) + (usage?.pending_invitations ?? 0);
  const full = maxUsers != null && used >= maxUsers;
  const dayFull = maxDay != null && (usage?.invitations_today ?? 0) >= maxDay;
  return (
    <Panel id="miembros" title="Miembros e invitaciones" description={`Personas de «${org.name}», su rol y acceso. Los cambios de rol se aplican al instante y quedan en la auditoría.`}>
      {usage && (
        <p className="usage-line">
          <Icon.users /><span><b>{usage.users}</b> usuarios activos{maxUsers != null ? <> de <b>{maxUsers}</b> que permite el plan</> : " (sin límite de usuarios)"}
            {usage.pending_invitations ? ` · ${usage.pending_invitations} invitaciones vigentes` : ""}</span>
          <UsageBar used={used} cap={maxUsers} />
        </p>
      )}
      <DataTable label="Miembros" rows={members} rowKey={(m) => m.user_id} exportName={`miembros-${org.name}`} initialSort={{ key: "email" }}
        rowClassName={(m) => (m.active ? "" : "muted")}
        columns={[
          { key: "email", label: "Correo", value: (m) => m.email },
          { key: "name", label: "Nombre", value: (m) => m.name },
          { key: "role", label: "Rol", value: (m) => ROLE_LABEL[m.role], render: (m) => (
            <select value={m.role} disabled={m.user_id === me?.id} aria-label={`Rol de ${m.email}`}
              onChange={(e) => void act(() => api.updateMember(org.id, m.user_id, { role: e.target.value as Role }), "Rol guardado.")}>
              {ROLES.map((r) => <option key={r} value={r} disabled={!assignable.includes(r)}>{ROLE_LABEL[r]}</option>)}</select>) },
          { key: "state", label: "Estado", value: (m) => (m.active ? "activo" : "desactivado"),
            render: (m) => <span className={`status-pill ${m.active ? "ok" : "muted"}`}><i />{m.active ? "activo" : "desactivado"}</span> },
          { key: "mfa", label: "TOTP", value: (m) => (m.mfa_enabled ? "sí" : "no") },
          { key: "last", label: "Último ingreso", type: "date", value: (m) => m.last_login_at ?? null,
            render: (m) => (m.last_login_at ? new Date(m.last_login_at).toLocaleString("es-CL", { dateStyle: "short", timeStyle: "short" }) : "—"), className: "nowrap" },
          { key: "acc", label: "", sortable: false, noExport: true, value: () => "", className: "right nowrap", render: (m) => (<>
            {m.user_id !== me?.id && <button className={`small ghost ${m.active ? "danger-text" : ""}`} onClick={() => {
              if (m.active && !window.confirm(`¿Desactivar a ${m.email}? No podrá ingresar a esta organización.`)) return;
              void act(() => api.updateMember(org.id, m.user_id, { active: !m.active }));
            }}>{m.active ? "Desactivar" : "Activar"}</button>}
            <button className="small ghost" title="Enlace de un solo uso para crear una contraseña nueva" onClick={async () => { try { setLink((await api.memberResetLink(org.id, m.user_id)).link); } catch (e) { toast(errorText(e), "error"); } }}>Enlace de clave</button>
          </>) },
        ]} />
      <h3>Invitar</h3>
      <form className="toolbar wrap" onSubmit={(e) => { e.preventDefault(); void act(async () => { const r = await api.invite(org.id, email, role, true); setLink(r.link); toast(r.emailed ? "Invitación enviada por correo." : "Comparta el enlace de invitación."); setEmail(""); }); }}>
        <input type="email" required placeholder="correo@dominio.cl" value={email} onChange={(e) => setEmail(e.target.value)} aria-label="Correo a invitar" disabled={full || dayFull} />
        <select value={role} onChange={(e) => setRole(e.target.value as Role)} aria-label="Rol" disabled={full || dayFull}>
          {assignable.map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}</select>
        <button className="small primary" disabled={full || dayFull} title={full ? `Su plan permite ${maxUsers} usuarios` : undefined}>Invitar</button>
        {full && <span className="limit-note" role="status"><Icon.alert />Su plan permite {maxUsers} usuarios.</span>}
        {!full && dayFull && <span className="limit-note" role="status"><Icon.alert />Se alcanzó el máximo de {maxDay} invitaciones por día.</span>}
      </form>
      <p className="muted small">La invitación vence a los {usage?.invite_days ?? 7} días. Solo puede invitar con un rol igual o inferior al suyo.</p>
      {link && <p className="small">Enlace de un solo uso: <input className="mono link-box" readOnly value={link} onFocus={(e) => e.target.select()} aria-label="Enlace" /></p>}
      {invites.length > 0 && (<>
        <h3>Invitaciones vigentes</h3>
        <DataTable compact label="Invitaciones vigentes" rows={invites} rowKey={(i) => i.id} initialSort={{ key: "exp" }} search={false}
          columns={[
            { key: "email", label: "Correo", value: (i) => i.email },
            { key: "role", label: "Rol", value: (i) => ROLE_LABEL[i.role] },
            { key: "at", label: "Enviada", type: "date", value: (i) => i.created_at, render: (i) => new Date(i.created_at).toLocaleString("es-CL") },
            { key: "exp", label: "Vence", type: "date", value: (i) => i.expires_at, render: (i) => new Date(i.expires_at).toLocaleDateString("es-CL") },
            { key: "x", label: "", sortable: false, noExport: true, value: () => "", className: "right", render: (i) => (
              <button className="small ghost danger-text" onClick={() => { if (window.confirm(`¿Anular la invitación de ${i.email}?`)) void act(() => api.revokeInvitation(org.id, i.id), "Invitación anulada."); }}>Anular</button>) },
          ]} />
      </>)}
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
  if (!org || !st) return <Skeleton />;
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
  if (!org || !st) return <Skeleton />;
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
            <td><button className="ghost small" onClick={() => setSt({ ...st, prices: prices.filter((_, k) => k !== i) })} aria-label="Quitar precio"><Icon.close /></button></td>
          </tr>))}</tbody>
      </table>
      <div className="toolbar plain">
        <button className="small" onClick={() => setSt({ ...st, prices: [...prices, { material: "*", dn_max: 110, price_m: 60000 }] })}><Icon.plus /><span>Precio</span></button>
        <label className="check small"><input type="checkbox" checked={!!st.prices_verified} onChange={(e) => setSt({ ...st, prices, prices_verified: e.target.checked })} />
          Precios revisados</label>
      </div>
      <SaveButton dirty={dirty} onSave={save} />
      <h3>Catálogo de tuberías <span className="muted small">({pipes.length})</span></h3>
      <label className="field"><span>Material</span>
        <select value={mat} onChange={(e) => setMat(e.target.value)} aria-label="Filtrar catálogo por material">
          <option value="">Todos</option>{materials.map((m) => <option key={m}>{m}</option>)}</select></label>
      <DataTable compact className="catalog-table" label="Catálogo de tuberías" rows={pipes.filter((p) => !mat || p.material === mat)} rowKey={(p) => String(p.id)}
        exportName="catalogo-tuberias" initialSort={{ key: "dn" }}
        columns={[
          { key: "mat", label: "Material", value: (p) => p.material },
          { key: "std", label: "Norma", value: (p) => p.standard ?? "", className: "small" },
          { key: "dn", label: "DN", type: "num", value: (p) => p.dn },
          { key: "cls", label: "Clase", value: (p) => p.pipe_class ?? "" },
          { key: "di", label: "D int. (mm)", type: "num", value: (p) => p.inner_diameter_mm, render: (p) => fmt(p.inner_diameter_mm, 1) },
          { key: "c", label: "C H-W", type: "num", value: (p) => p.hw_c, render: (p) => fmt(p.hw_c, 0) },
          { key: "e", label: "ε (mm)", type: "num", value: (p) => p.dw_roughness_mm, render: (p) => fmt(p.dw_roughness_mm, 3) },
          { key: "v", label: "Verificado", value: (p) => (p.verified ? "sí" : "no verificado"),
            render: (p) => (p.verified ? "sí" : <span className="badge warn">no verificado</span>) },
        ]} />
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
    <Panel id="uso" title="Uso y plan" description="Usuarios usados y permitidos, y el consumo del mes contra los límites del plan. El plan lo cambia el Super Admin.">
      {usage ? <UsageCard u={usage} /> : <Skeleton kind="tiles" rows={3} />}
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
          <option value="organizacion">Organización</option><option value="soporte">Modo soporte</option>
        </select>
      </div>
      <AuditTable rows={audit} name={`auditoria-${org.name}`} />
    </Panel>
  );
}

export function auditDetail(a: AuditOut): string {
  return a.detail ? Object.entries(a.detail).filter(([, v]) => v !== null && v !== "")
    .map(([k, v]) => `${k}: ${typeof v === "object" ? JSON.stringify(v) : v}`).join(" · ") : "";
}

/** Tabla de auditoría (organización y Panel admin). */
export function AuditTable({ rows, name, compact }: { rows: AuditOut[]; name: string; compact?: boolean }) {
  return (
    <DataTable compact={compact} label="Auditoría" rows={rows} rowKey={(a) => String(a.id)} exportName={name} initialSort={{ key: "at", dir: -1 }}
      rowClassName={(a) => (a.detail && (a.detail as Record<string, unknown>).soporte ? "support-row" : "")}
      columns={[
        { key: "at", label: "Fecha", type: "date", value: (a) => a.created_at,
          render: (a) => new Date(a.created_at).toLocaleString("es-CL", { dateStyle: "short", timeStyle: "short" }), className: "small nowrap" },
        { key: "user", label: "Usuario", value: (a) => a.user_email ?? "" },
        { key: "action", label: "Acción", value: (a) => a.action, className: "mono" },
        { key: "project", label: "Proyecto", value: (a) => a.project_id?.slice(0, 8) ?? "", className: "mono small" },
        { key: "version", label: "Versión", type: "num", value: (a) => a.version ?? null },
        { key: "detail", label: "Detalle", value: (a) => auditDetail(a), className: "small" },
      ]} />
  );
}
