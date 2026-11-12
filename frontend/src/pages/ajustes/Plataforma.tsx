// Ajustes → Plataforma (superadministrador): organizaciones y cuentas, mapa base, planes y límites, y sistema.
import { useCallback, useEffect, useState } from "react";
import { api } from "../../api/client";
import type { OrgAdminOut, SystemInfo, UserAdminOut } from "../../api/types";
import { MapBaseSection } from "../../components/MapBaseSettings";
import { ROLE_LABEL } from "../../state/auth";
import { errorText } from "../../state/projects";
import { useEditor } from "../../state/store";
import { Panel, SaveButton } from "./common";
import { UsageCard } from "./Organizacion";

type Plan = "basico" | "profesional" | "ilimitado";
const PLAN_LABEL: Record<Plan, string> = { basico: "Básico", profesional: "Profesional", ilimitado: "Ilimitado" };
const LIMITS: [string, string][] = [["max_projects", "Proyectos"], ["max_simulations_month", "Simulaciones por mes"],
  ["max_map_loads_month", "Cargas del mapa de Google por mes"], ["max_ortho_mb", "Ortofotos (MB)"]];

function useAdmin() {
  const toast = useEditor((s) => s.toast);
  const [orgs, setOrgs] = useState<OrgAdminOut[]>([]);
  const [users, setUsers] = useState<UserAdminOut[]>([]);
  const load = useCallback(async () => {
    try { const [o, u] = await Promise.all([api.adminOrgs(), api.adminUsers()]); setOrgs(o); setUsers(u); } catch (e) { toast(errorText(e), "error"); }
  }, [toast]);
  useEffect(() => { void load(); }, [load]);
  const act = async (f: () => Promise<unknown>) => { try { await f(); await load(); } catch (e) { toast(errorText(e), "error"); } };
  return { orgs, users, act, toast };
}

export function Organizaciones() {
  const { orgs, users, act, toast } = useAdmin();
  const [name, setName] = useState("");
  const [adminEmail, setAdminEmail] = useState("");
  const [link, setLink] = useState<string | null>(null);
  return (
    <Panel id="organizaciones" title="Organizaciones" description="Organizaciones de la plataforma (APR, consultoras, sanitarias), su estado y las cuentas de usuario.">
      <h3>Nueva organización</h3>
      <form className="toolbar wrap" onSubmit={(e) => { e.preventDefault(); void act(async () => { const r = await api.adminCreateOrg({ name, admin_email: adminEmail || null }); setLink(r.admin_invitation ?? null); setName(""); setAdminEmail(""); toast("Organización creada."); }); }}>
        <input required placeholder="Nombre (APR, consultora, sanitaria)" value={name} onChange={(e) => setName(e.target.value)} aria-label="Nombre de la organización" />
        <input type="email" placeholder="Correo del administrador (opcional)" value={adminEmail} onChange={(e) => setAdminEmail(e.target.value)} aria-label="Correo del administrador" />
        <button className="small primary">Crear</button>
      </form>
      {link && <p className="small">Invitación del administrador: <input className="mono link-box" readOnly value={link} onFocus={(e) => e.target.select()} aria-label="Enlace" /></p>}
      <div className="table-scroll">
        <table className="tbl compact">
          <thead><tr><th>Organización</th><th>Plan</th><th className="num">Miembros</th><th className="num">Proyectos</th><th>Estado</th><th /></tr></thead>
          <tbody>{orgs.map((o) => (
            <tr key={o.id} className={o.suspended ? "muted" : ""}><td>{o.name}</td><td>{PLAN_LABEL[o.plan as Plan] ?? o.plan}</td>
              <td className="num">{o.members}</td><td className="num">{o.usage.projects}</td>
              <td>{o.suspended ? <span className="badge warn">suspendida</span> : "activa"}</td>
              <td className="right"><button className={`small ghost ${o.suspended ? "" : "danger-text"}`} onClick={() => { if (!o.suspended && !window.confirm(`¿Suspender la organización «${o.name}»? Sus miembros no podrán ingresar.`)) return; void act(() => api.adminUpdateOrg(o.id, { suspended: !o.suspended })); }}>{o.suspended ? "Reactivar" : "Suspender"}</button></td></tr>
          ))}</tbody>
        </table>
      </div>
      <h3>Cuentas</h3>
      <div className="table-scroll">
        <table className="tbl compact">
          <thead><tr><th>Correo</th><th>Organizaciones</th><th>TOTP</th><th>Estado</th><th /></tr></thead>
          <tbody>{users.map((u) => (
            <tr key={u.id} className={u.active ? "" : "muted"}>
              <td>{u.email}{u.is_superadmin ? " · superadmin" : ""}</td>
              <td className="small">{u.orgs.map((o) => `${o.name} (${ROLE_LABEL[o.role]})`).join(", ")}</td>
              <td>{u.mfa_enabled ? "sí" : "no"}</td>
              <td>{u.active ? (u.locked ? "bloqueada" : "activa") : "suspendida"}</td>
              <td className="right">
                <button className={`small ghost ${u.active ? "danger-text" : ""}`} onClick={() => { if (u.active && !window.confirm(`¿Suspender la cuenta ${u.email}?`)) return; void act(() => api.adminUpdateUser(u.id, !u.active)); }}>{u.active ? "Suspender" : "Reactivar"}</button>
                <button className="small ghost" onClick={async () => { try { setLink((await api.adminResetLink(u.id)).link); } catch (e) { toast(errorText(e), "error"); } }}>Enlace de contraseña</button>
              </td>
            </tr>
          ))}</tbody>
        </table>
      </div>
    </Panel>
  );
}

export function MapaBase() {
  return (
    <Panel id="mapa-base" title="Mapa base" description="Proveedor del mapa del editor (OpenStreetMap sin key o Google Maps) y la API key, guardada cifrada.">
      <MapBaseSection />
    </Panel>
  );
}

function OrgPlan({ o, onSave }: { o: OrgAdminOut; onSave: (body: { plan?: Plan; limits?: Record<string, number> }) => Promise<void> }) {
  const [plan, setPlan] = useState<Plan>(o.plan as Plan);
  const init = Object.fromEntries(LIMITS.map(([k]) => [k, String((o.limits as Record<string, number> | null)?.[k] ?? "")]));
  const [lim, setLim] = useState<Record<string, string>>(init);
  const dirty = plan !== o.plan || JSON.stringify(lim) !== JSON.stringify(init);
  return (
    <section className={`card plan-card ${o.suspended ? "suspended" : ""}`} aria-label={`Plan de ${o.name}`}>
      <h3>{o.name} {o.suspended && <span className="badge warn">suspendida</span>}</h3>
      <label className="field"><span>Plan</span>
        <select value={plan} onChange={(e) => setPlan(e.target.value as Plan)} aria-label={`Plan de ${o.name}`}>
          {(Object.keys(PLAN_LABEL) as Plan[]).map((p) => <option key={p} value={p}>{PLAN_LABEL[p]}</option>)}</select></label>
      <div className="form-grid">
        {LIMITS.map(([k, l]) => (
          <label key={k} className="field stacked"><span className="small">{l}</span>
            <input inputMode="numeric" value={lim[k]} placeholder="según el plan" onChange={(e) => setLim({ ...lim, [k]: e.target.value })} /></label>
        ))}
      </div>
      <UsageCard u={o.usage} />
      <SaveButton dirty={dirty} onSave={() => {
        const limits: Record<string, number> = {};
        for (const [k] of LIMITS) if (lim[k].trim() !== "") limits[k] = Number(lim[k]);
        return onSave({ plan, limits });
      }} />
    </section>
  );
}

export function Planes() {
  const { orgs, act } = useAdmin();
  const [sys, setSys] = useState<SystemInfo | null>(null);
  useEffect(() => { api.adminSystem().then(setSys).catch(() => undefined); }, []);
  return (
    <Panel id="planes" title="Planes y límites" description="Límites de cada plan y, por organización, el plan asignado y límites personalizados (vacío = los del plan).">
      {sys && (
        <table className="tbl compact">
          <thead><tr><th>Plan</th>{LIMITS.map(([k, l]) => <th key={k} className="num">{l}</th>)}</tr></thead>
          <tbody>{(Object.keys(PLAN_LABEL) as Plan[]).map((p) => (
            <tr key={p}><td>{PLAN_LABEL[p]}</td>{LIMITS.map(([k]) => {
              const v = (sys.plans[p] as Record<string, number | null>)?.[k];
              return <td key={k} className="num">{v == null ? "sin límite" : v.toLocaleString("es-CL")}</td>;
            })}</tr>))}</tbody>
        </table>
      )}
      <div className="plan-grid">
        {orgs.map((o) => <OrgPlan key={`${o.id}-${o.plan}-${JSON.stringify(o.limits)}`} o={o} onSave={(body) => act(() => api.adminUpdateOrg(o.id, body))} />)}
      </div>
    </Panel>
  );
}

export function Sistema() {
  const engine = useEditor((s) => s.engine);
  const toast = useEditor((s) => s.toast);
  const [sys, setSys] = useState<SystemInfo | null>(null);
  const load = useCallback(() => api.adminSystem().then(setSys).catch((e) => toast(errorText(e), "error")), [toast]);
  useEffect(() => { void load(); }, [load]);
  const e = (sys?.engine ?? engine) as Record<string, string | null> | null;
  const b = sys?.last_backup as Record<string, string> | null | undefined;
  return (
    <Panel id="sistema" title="Sistema" description="Versión de la aplicación, motor hidráulico, estado de los servicios y último respaldo automático.">
      <dl className="kv">
        <dt>Aplicación</dt><dd className="mono">{__APP_VERSION__} · API {sys?.api_version ?? "…"}</dd>
        <dt>Motor</dt><dd>{e ? <>OWA-EPANET {e.wheel_version} (único motor, ejecutado en el servidor)</> : "…"}</dd>
        <dt>Fuente</dt><dd>{e ? <>github.com/OpenWaterAnalytics/EPANET, tag <span className="mono">{e.epanet_tag}</span></> : "…"}</dd>
        <dt>SHA del tag</dt><dd className="mono break">{e?.epanet_sha ?? "—"}</dd>
        <dt>EN_getversion</dt><dd className="mono">{e?.en_getversion ?? "—"}</dd>
      </dl>
      <h3>Servicios <button className="ghost small" onClick={() => void load()}>Actualizar</button></h3>
      <ul className="service-list">
        {sys?.services.map((s) => (
          <li key={s.name}><span className={`dot ${s.status === "ok" ? "ok" : s.status === "error" ? "bad" : "warn"}`} aria-hidden />
            <b>{s.name}</b> <span className="muted small">{s.status === "ok" ? "en servicio" : s.status === "error" ? "con error" : "sin datos"}{s.detail ? ` · ${s.detail}` : ""}</span></li>
        )) ?? <li className="muted">Consultando…</li>}
      </ul>
      <h3>Último respaldo</h3>
      {b ? <p>{new Date(b.fecha).toLocaleString("es-CL")} · carpeta <span className="mono">{b.carpeta}</span> · {b.tamano}</p>
        : <p className="muted">Sin respaldos registrados. El servicio de respaldo diario corre en la publicación (make up-public); en local use make backup.</p>}
      <h3>Créditos</h3>
      <p className="credits">Daniel Ruz Moreno · pulentoski</p>
      <p className="muted small">OWA-EPANET (licencia MIT, Open Water Analytics) · Tipografía IBM Plex (SIL OFL). Resultados validados contra
        el ejecutable runepanet compilado del mismo tag (docs/validation).</p>
    </Panel>
  );
}
