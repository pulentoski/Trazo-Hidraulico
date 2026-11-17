// Panel admin (/panel-admin, solo Super Admin): resumen de la plataforma, organizaciones con su ficha (datos, plan,
// uso contra límites, usuarios y acciones), planes y límites, usuarios, mapa base y sistema. Las acciones peligrosas
// (suspender y eliminar una organización) piden escribir su nombre; el backend también lo exige.
import type { ReactNode } from "react";
import { Fragment, useCallback, useEffect, useState } from "react";
import { Link, Navigate, NavLink, useNavigate, useParams } from "react-router";
import { api } from "../api/client";
import type { AdminOverview, OrgAdminOut, OrgDetail, PlanName, SystemInfo, UserAdminOut } from "../api/types";
import { AppFrame } from "../components/AppFrame";
import { DataTable } from "../components/DataTable";
import { Modal } from "../components/Dialogs";
import { Icon } from "../components/Icons";
import { MapBaseSection } from "../components/MapBaseSettings";
import { Skeleton } from "../components/Skeleton";
import { fmt } from "../lib/format";
import { PATHS } from "../paths";
import { ROLE_LABEL, useAuth } from "../state/auth";
import { errorText } from "../state/projects";
import { useEditor } from "../state/store";
import { Panel, SaveButton } from "./ajustes/common";
import { AuditTable, LIMIT_ROWS, PLAN_LABEL, UsageBar, UsageCard } from "./ajustes/Organizacion";

const PLANS: PlanName[] = ["basico", "profesional", "ilimitado"];
const KIND_LABEL: Record<string, string> = { apr: "APR", consultora: "Consultora", sanitaria: "Sanitaria", otra: "Otra" };
const INFO_LABEL: Record<string, string> = { rut: "RUT", region: "Región", comuna: "Comuna", address: "Dirección", contact: "Contacto", phone: "Teléfono", email: "Correo" };

export const PANEL_SECTIONS = [
  { id: "resumen", label: "Resumen", icon: Icon.gauge },
  { id: "organizaciones", label: "Organizaciones", icon: Icon.org },
  { id: "planes", label: "Planes y límites", icon: Icon.activity },
  { id: "usuarios", label: "Usuarios", icon: Icon.users },
  { id: "mapa-base", label: "Mapa base", icon: Icon.layers },
  { id: "sistema", label: "Sistema", icon: Icon.zap },
] as const;

/** Confirmación escrita: el botón se habilita solo al escribir el nombre exacto de la organización. */
export function ConfirmByName({ title, name, what, action, danger = true, onConfirm, onClose }: {
  title: string; name: string; what: ReactNode; action: string; danger?: boolean; onConfirm: (typed: string) => Promise<void>; onClose: () => void;
}) {
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const toast = useEditor((s) => s.toast);
  const ok = typed.trim() === name;
  return (
    <Modal title={title} onClose={onClose}>
      <form onSubmit={async (e) => {
        e.preventDefault();
        if (!ok) return;
        setBusy(true);
        try { await onConfirm(typed.trim()); onClose(); } catch (err) { toast(errorText(err), "error"); setBusy(false); }
      }}>
        <div className="danger-note" role="alert"><Icon.alert /><div>{what}</div></div>
        <label className="field stacked"><span>Escriba <b>{name}</b> para confirmar</span>
          <input autoFocus value={typed} onChange={(e) => setTyped(e.target.value)} aria-label="Nombre de la organización" autoComplete="off" spellCheck={false} /></label>
        <div className="modal-actions">
          <button type="button" className="ghost" onClick={onClose}>Cancelar</button>
          <button className={danger ? "danger" : "primary"} disabled={!ok || busy}>{busy ? "Procesando…" : action}</button>
        </div>
      </form>
    </Modal>
  );
}

function Tile({ icon, label, value, sub, tone }: { icon: ReactNode; label: string; value: ReactNode; sub?: ReactNode; tone?: string }) {
  return (
    <article className={`admin-tile ${tone ?? ""}`} aria-label={label}>
      <span className="admin-tile-icon" aria-hidden="true">{icon}</span>
      <div><span className="muted small">{label}</span><b>{value}</b>{sub && <span className="muted small">{sub}</span>}</div>
    </article>
  );
}

function Resumen() {
  const toast = useEditor((s) => s.toast);
  const [ov, setOv] = useState<AdminOverview | null>(null);
  useEffect(() => { api.adminOverview().then(setOv).catch((e) => toast(errorText(e), "error")); }, [toast]);
  if (!ov) return <Skeleton kind="tiles" rows={6} />;
  const diskPct = ov.disk_total_gb ? ((ov.disk_used_gb ?? 0) / ov.disk_total_gb) * 100 : null;
  return (
    <>
      <section className="admin-tiles" aria-label="Indicadores de la plataforma">
        <Tile icon={<Icon.org />} label="Organizaciones activas" value={ov.orgs_active} tone="ok" />
        <Tile icon={<Icon.ban />} label="Suspendidas" value={ov.orgs_suspended} tone={ov.orgs_suspended ? "warn" : ""} />
        <Tile icon={<Icon.users />} label="Usuarios" value={ov.users_total} sub={`${ov.users_active} activos`} />
        <Tile icon={<Icon.folder />} label="Proyectos" value={ov.projects_total} />
        <Tile icon={<Icon.image />} label="Ortofotos" value={ov.ortho_count} sub={`${fmt(ov.ortho_mb / 1024, 2)} GB`} />
        <Tile icon={<Icon.disk />} label="Disco (ortofotos)" value={ov.disk_total_gb != null ? `${fmt(ov.disk_used_gb, 1)} / ${fmt(ov.disk_total_gb, 0)} GB` : "—"}
          sub={diskPct !== null ? <><UsageBar used={ov.disk_used_gb ?? 0} cap={ov.disk_total_gb} /> {fmt(ov.disk_free_gb, 1)} GB libres</> : "sin datos"}
          tone={diskPct !== null && diskPct >= 90 ? "bad" : diskPct !== null && diskPct >= 70 ? "warn" : ""} />
      </section>
      <div className="admin-cols">
        <Panel id="cerca-limite" title="Organizaciones cerca de su límite" description="Uso ≥ 80 % de algún límite del plan (el más exigido).">
          {ov.near_limit.length === 0 ? <p className="all-clear"><Icon.check />Ninguna organización está cerca de sus límites.</p> : (
            <ul className="near-list">
              {ov.near_limit.map((n) => (
                <li key={n.org.id}>
                  <Link to={PATHS.panelOrg(n.org.id)}><b>{n.org.name}</b>
                    <span className="muted small">{n.worst.label}: {fmt(n.worst.used, 0)} de {fmt(n.worst.limit, 0)}</span>
                    <UsageBar used={n.worst.used} cap={n.worst.limit} /><Icon.chevronRight /></Link>
                </li>
              ))}
            </ul>
          )}
        </Panel>
        <Panel id="ultimos-eventos" title="Últimos eventos de auditoría" description="De toda la plataforma, del más reciente al más antiguo.">
          <AuditTable compact rows={ov.recent_audit} name="auditoria-plataforma" />
        </Panel>
      </div>
    </>
  );
}

function Organizaciones() {
  const toast = useEditor((s) => s.toast);
  const navigate = useNavigate();
  const [orgs, setOrgs] = useState<OrgAdminOut[] | null>(null);
  const [name, setName] = useState("");
  const [plan, setPlan] = useState<PlanName>("basico");
  const [adminEmail, setAdminEmail] = useState("");
  const [link, setLink] = useState<string | null>(null);
  const load = useCallback(() => api.adminOrgs().then(setOrgs).catch((e) => toast(errorText(e), "error")), [toast]);
  useEffect(() => { void load(); }, [load]);
  return (
    <Panel id="organizaciones" title="Organizaciones" description="APR, consultoras y sanitarias de la plataforma. Abra la ficha para ver su uso, usuarios y acciones.">
      <h3>Nueva organización</h3>
      <form className="toolbar wrap" onSubmit={async (e) => {
        e.preventDefault();
        try {
          const r = await api.adminCreateOrg({ name, plan, admin_email: adminEmail || null });
          setLink(r.admin_invitation ?? null); setName(""); setAdminEmail(""); toast("Organización creada."); await load();
        } catch (err) { toast(errorText(err), "error"); }
      }}>
        <input required minLength={2} placeholder="Nombre (APR, consultora, sanitaria)" value={name} onChange={(e) => setName(e.target.value)} aria-label="Nombre de la organización" />
        <select value={plan} onChange={(e) => setPlan(e.target.value as PlanName)} aria-label="Plan">{PLANS.map((p) => <option key={p} value={p}>{PLAN_LABEL[p]}</option>)}</select>
        <input type="email" placeholder="Correo del administrador (opcional)" value={adminEmail} onChange={(e) => setAdminEmail(e.target.value)} aria-label="Correo del administrador" />
        <button className="small primary"><Icon.plus /><span>Crear</span></button>
      </form>
      {link && <p className="small">Invitación del administrador: <input className="mono link-box" readOnly value={link} onFocus={(e) => e.target.select()} aria-label="Enlace" /></p>}
      {orgs === null ? <Skeleton /> : (
        <DataTable label="Organizaciones" rows={orgs} rowKey={(o) => o.id} exportName="organizaciones" initialSort={{ key: "name" }}
          onRowClick={(o) => navigate(PATHS.panelOrg(o.id))} rowTitle={(o) => `Abrir la ficha de «${o.name}»`}
          columns={[
            { key: "name", label: "Organización", value: (o) => o.name, render: (o) => <Link to={PATHS.panelOrg(o.id)} onClick={(e) => e.stopPropagation()}>{o.name}</Link> },
            { key: "kind", label: "Tipo", value: (o) => KIND_LABEL[o.kind] ?? o.kind },
            { key: "plan", label: "Plan", value: (o) => PLAN_LABEL[o.plan] ?? o.plan },
            { key: "users", label: "Usuarios", type: "num", value: (o) => o.usage.users ?? o.members,
              render: (o) => { const cap = (o.usage.limits as Record<string, number | null>).max_users; return `${o.usage.users ?? o.members}${cap != null ? ` / ${cap}` : ""}`; } },
            { key: "projects", label: "Proyectos", type: "num", value: (o) => o.usage.projects },
            { key: "ortho", label: "Ortofotos (MB)", type: "num", value: (o) => o.usage.ortho_mb, render: (o) => fmt(o.usage.ortho_mb, 1) },
            { key: "created", label: "Creada", type: "date", value: (o) => o.created_at, render: (o) => new Date(o.created_at).toLocaleDateString("es-CL") },
            { key: "state", label: "Estado", value: (o) => (o.suspended ? "suspendida" : "activa"),
              render: (o) => <span className={`status-pill ${o.suspended ? "warn" : "ok"}`}><i />{o.suspended ? "suspendida" : "activa"}</span> },
          ]} />
      )}
    </Panel>
  );
}

function OrgFicha({ id }: { id: string }) {
  const toast = useEditor((s) => s.toast);
  const refresh = useAuth((s) => s.refresh);
  const navigate = useNavigate();
  const [d, setD] = useState<OrgDetail | null>(null);
  const [plan, setPlan] = useState<PlanName>("basico");
  const [lim, setLim] = useState<Record<string, string>>({});
  const [confirm, setConfirm] = useState<"suspend" | "delete" | null>(null);
  const load = useCallback(() => api.adminOrg(id).then((x) => {
    setD(x);
    setPlan(x.org.plan as PlanName);
    setLim(Object.fromEntries(LIMIT_ROWS.map((r) => [r.key, String((x.org.limits as Record<string, number | null> | null)?.[r.key] ?? "")])));
  }).catch((e) => { toast(errorText(e), "error"); navigate(PATHS.panel("organizaciones"), { replace: true }); }), [id, toast, navigate]);
  useEffect(() => { void load(); }, [load]);
  if (!d) return <Skeleton kind="tiles" rows={4} />;
  const o = d.org;
  const initLim = Object.fromEntries(LIMIT_ROWS.map((r) => [r.key, String((o.limits as Record<string, number | null> | null)?.[r.key] ?? "")]));
  const dirty = plan !== o.plan || JSON.stringify(lim) !== JSON.stringify(initLim);
  const support = async () => {
    try { await api.adminSupport(o.id); await refresh(); toast(`Modo soporte en «${o.name}»: queda registrado en la auditoría.`); navigate(PATHS.home); } catch (e) { toast(errorText(e), "error"); }
  };
  const info = Object.entries((o.info ?? {}) as Record<string, string>).filter(([, v]) => v);
  return (
    <div className="org-ficha">
      <header className="ficha-head">
        <div>
          <p className="muted small"><Link to={PATHS.panel("organizaciones")}><Icon.back /> Organizaciones</Link></p>
          <h2>{o.name} <span className={`status-pill ${o.suspended ? "warn" : "ok"}`}><i />{o.suspended ? "suspendida" : "activa"}</span></h2>
          <p className="muted">{KIND_LABEL[o.kind] ?? o.kind} · plan {PLAN_LABEL[o.plan] ?? o.plan} · creada el {new Date(o.created_at).toLocaleDateString("es-CL")}</p>
        </div>
        <div className="ficha-actions" role="group" aria-label="Acciones de la organización">
          <button className="danger-outline" onClick={() => setConfirm("delete")}><Icon.trash /><span>Eliminar</span></button>
          {o.suspended
            ? <button onClick={async () => { try { await api.adminUpdateOrg(o.id, { suspended: false }); toast("Organización reactivada."); await load(); } catch (e) { toast(errorText(e), "error"); } }}><Icon.resume /><span>Reactivar</span></button>
            : <button className="danger-outline" onClick={() => setConfirm("suspend")}><Icon.ban /><span>Suspender</span></button>}
          <button className="primary" onClick={() => void support()} title="Entra a la organización como administrador; queda en la auditoría"><Icon.support /><span>Entrar como soporte</span></button>
        </div>
      </header>
      <div className="admin-cols">
        <Panel id="ficha-datos" title="Datos" description="Los edita el administrador de la organización.">
          {info.length ? <dl className="kv">{info.map(([k, v]) => <Fragment key={k}><dt>{INFO_LABEL[k] ?? k}</dt><dd>{v}</dd></Fragment>)}</dl>
            : <p className="muted">Sin datos de contacto registrados.</p>}
        </Panel>
        <Panel id="ficha-plan" title="Cambiar plan" description="Plan y límites propios de esta organización (vacío = los del plan).">
          <label className="field"><span>Plan</span>
            <select value={plan} onChange={(e) => setPlan(e.target.value as PlanName)} aria-label={`Plan de ${o.name}`}>
              {PLANS.map((p) => <option key={p} value={p}>{PLAN_LABEL[p]}</option>)}</select></label>
          <div className="form-grid two">
            {LIMIT_ROWS.map((r) => (
              <label key={r.key} className="field stacked"><span className="small">{r.label}{r.unit ? ` (${r.unit.trim()})` : ""}</span>
                <input inputMode="numeric" value={lim[r.key] ?? ""} placeholder="según el plan" onChange={(e) => setLim({ ...lim, [r.key]: e.target.value })} /></label>
            ))}
          </div>
          <SaveButton dirty={dirty} label="Guardar plan" onSave={async () => {
            const limits: Record<string, number> = {};
            for (const r of LIMIT_ROWS) if ((lim[r.key] ?? "").trim() !== "") limits[r.key] = Number(lim[r.key]);
            await api.adminUpdateOrg(o.id, { plan, limits });
            await load();
          }} />
        </Panel>
      </div>
      <Panel id="ficha-uso" title="Uso contra límites" description="Usuarios, proyectos y consumo del mes frente a lo que permite el plan.">
        <UsageCard u={d.usage} />
      </Panel>
      <Panel id="ficha-usuarios" title="Usuarios" description="Miembros de la organización con su rol y último ingreso.">
        <DataTable label="Usuarios de la organización" rows={d.members} rowKey={(m) => m.user_id} exportName={`usuarios-${o.name}`} initialSort={{ key: "email" }}
          columns={[
            { key: "email", label: "Correo", value: (m) => m.email },
            { key: "name", label: "Nombre", value: (m) => m.name },
            { key: "role", label: "Rol", value: (m) => ROLE_LABEL[m.role] },
            { key: "active", label: "Estado", value: (m) => (m.active ? "activo" : "desactivado"),
              render: (m) => <span className={`status-pill ${m.active ? "ok" : "muted"}`}><i />{m.active ? "activo" : "desactivado"}</span> },
            { key: "mfa", label: "TOTP", value: (m) => (m.mfa_enabled ? "sí" : "no") },
            { key: "last", label: "Último ingreso", type: "date", value: (m) => m.last_login_at ?? null,
              render: (m) => (m.last_login_at ? new Date(m.last_login_at).toLocaleString("es-CL", { dateStyle: "short", timeStyle: "short" }) : "nunca"), className: "nowrap" },
          ]} />
      </Panel>
      {confirm === "suspend" && (
        <ConfirmByName title="Suspender organización" name={o.name} action="Suspender" onClose={() => setConfirm(null)}
          what={<>Sus <b>{d.members.length}</b> miembros no podrán ingresar ni ver sus proyectos hasta que la reactive.</>}
          onConfirm={async (typed) => { await api.adminUpdateOrg(o.id, { suspended: true, confirm: typed }); toast(`«${o.name}» suspendida.`); await load(); }} />
      )}
      {confirm === "delete" && (
        <ConfirmByName title="Eliminar organización" name={o.name} action="Eliminar definitivamente" onClose={() => setConfirm(null)}
          what={<>Se eliminan la organización, sus <b>{d.usage.projects}</b> proyectos con todas sus versiones, registros y ortofotos, y las
            membresías. <b>No se puede deshacer.</b> La eliminación queda en la auditoría de la plataforma.</>}
          onConfirm={async (typed) => { await api.adminDeleteOrg(o.id, typed); toast(`«${o.name}» eliminada.`); navigate(PATHS.panel("organizaciones")); }} />
      )}
    </div>
  );
}

function Planes() {
  const toast = useEditor((s) => s.toast);
  const [saved, setSaved] = useState<Record<string, Record<string, number | null>> | null>(null);
  const [form, setForm] = useState<Record<string, Record<string, string>>>({});
  const fill = (p: Record<string, Record<string, number | null>>) => {
    setSaved(p);
    setForm(Object.fromEntries(PLANS.map((pl) => [pl, Object.fromEntries(LIMIT_ROWS.map((r) => [r.key, p[pl]?.[r.key] == null ? "" : String(p[pl][r.key])]))])));
  };
  useEffect(() => { api.adminSystem().then((s: SystemInfo) => fill(s.plans as Record<string, Record<string, number | null>>)).catch((e) => toast(errorText(e), "error")); }, [toast]);
  if (!saved) return <Skeleton />;
  const dirty = PLANS.some((pl) => LIMIT_ROWS.some((r) => (form[pl]?.[r.key] ?? "") !== (saved[pl]?.[r.key] == null ? "" : String(saved[pl][r.key]))));
  return (
    <Panel id="planes" title="Planes y límites" description="Límites de cada plan para todas sus organizaciones (vacío = sin límite). Cada organización puede tener límites propios en su ficha.">
      <div className="dt-scroll">
        <table className="tbl plan-table">
          <thead><tr><th>Límite</th>{PLANS.map((p) => <th key={p} className="num">{PLAN_LABEL[p]}</th>)}</tr></thead>
          <tbody>{LIMIT_ROWS.map((r) => (
            <tr key={r.key}><td>{r.label}{r.unit ? ` (${r.unit.trim()})` : ""}</td>
              {PLANS.map((p) => (
                <td key={p} className="num"><input className="cell-input" inputMode="numeric" value={form[p]?.[r.key] ?? ""} placeholder="sin límite"
                  aria-label={`${r.label}: plan ${PLAN_LABEL[p]}`} onChange={(e) => setForm({ ...form, [p]: { ...form[p], [r.key]: e.target.value } })} /></td>
              ))}</tr>))}</tbody>
        </table>
      </div>
      <p className="muted small">Al llegar al tope de usuarios, «Invitar» queda deshabilitado en la organización con el aviso «Su plan permite N usuarios».
        Las invitaciones vencen a los 7 días.</p>
      <SaveButton dirty={dirty} onSave={async () => {
        const body = Object.fromEntries(PLANS.map((p) => [p, Object.fromEntries(LIMIT_ROWS.map((r) => {
          const v = (form[p]?.[r.key] ?? "").trim();
          return [r.key, v === "" ? null : Number(v)];
        }))]));
        fill(await api.adminPlans(body));
      }} />
    </Panel>
  );
}

function Usuarios() {
  const me = useAuth((s) => s.me);
  const toast = useEditor((s) => s.toast);
  const [users, setUsers] = useState<UserAdminOut[] | null>(null);
  const [link, setLink] = useState<string | null>(null);
  const load = useCallback(() => api.adminUsers().then(setUsers).catch((e) => toast(errorText(e), "error")), [toast]);
  useEffect(() => { void load(); }, [load]);
  const act = async (f: () => Promise<unknown>, ok?: string) => { try { await f(); await load(); if (ok) toast(ok); } catch (e) { toast(errorText(e), "error"); } };
  return (
    <Panel id="usuarios" title="Usuarios" description="Todas las cuentas de la plataforma, sus organizaciones y su estado.">
      {link && <p className="small">Enlace de un solo uso: <input className="mono link-box" readOnly value={link} onFocus={(e) => e.target.select()} aria-label="Enlace" /></p>}
      {users === null ? <Skeleton /> : (
        <DataTable label="Usuarios" rows={users} rowKey={(u) => u.id} exportName="usuarios-plataforma" initialSort={{ key: "email" }}
          rowClassName={(u) => (u.active ? "" : "muted")}
          columns={[
            { key: "email", label: "Correo", value: (u) => u.email },
            { key: "name", label: "Nombre", value: (u) => u.name },
            { key: "orgs", label: "Organizaciones", value: (u) => u.orgs.map((o) => `${o.name} (${ROLE_LABEL[o.role]})`).join(", "), className: "small" },
            { key: "sa", label: "Super Admin", value: (u) => (u.is_superadmin ? "sí" : "no") },
            { key: "mfa", label: "TOTP", value: (u) => (u.mfa_enabled ? "sí" : "no") },
            { key: "last", label: "Último ingreso", type: "date", value: (u) => u.last_login_at ?? null,
              render: (u) => (u.last_login_at ? new Date(u.last_login_at).toLocaleString("es-CL", { dateStyle: "short", timeStyle: "short" }) : "nunca"), className: "nowrap" },
            { key: "state", label: "Estado", value: (u) => (u.active ? (u.locked ? "bloqueada" : "activa") : "suspendida"),
              render: (u) => <span className={`status-pill ${u.active ? (u.locked ? "warn" : "ok") : "bad"}`}><i />{u.active ? (u.locked ? "bloqueada" : "activa") : "suspendida"}</span> },
            { key: "acc", label: "", sortable: false, noExport: true, value: () => "", className: "right nowrap", render: (u) => (<>
              {u.id !== me?.id && <button className={`small ghost ${u.active ? "danger-text" : ""}`} onClick={() => {
                if (u.active && !window.confirm(`¿Suspender la cuenta ${u.email}? Se cierran sus sesiones.`)) return;
                void act(() => api.adminUpdateUser(u.id, { active: !u.active }));
              }}>{u.active ? "Suspender" : "Reactivar"}</button>}
              {u.id !== me?.id && <button className="small ghost" onClick={() => {
                if (!window.confirm(u.is_superadmin ? `¿Quitar el rol Super Admin a ${u.email}?` : `¿Nombrar Super Admin a ${u.email}? Tendrá acceso a toda la plataforma.`)) return;
                void act(() => api.adminUpdateUser(u.id, { is_superadmin: !u.is_superadmin }), "Rol de plataforma actualizado.");
              }}>{u.is_superadmin ? "Quitar Super Admin" : "Nombrar Super Admin"}</button>}
              <button className="small ghost" onClick={async () => { try { setLink((await api.adminResetLink(u.id)).link); } catch (e) { toast(errorText(e), "error"); } }}>Enlace de contraseña</button>
            </>) },
          ]} />
      )}
    </Panel>
  );
}

function MapaBase() {
  return (
    <Panel id="mapa-base" title="Mapa base" description="Proveedor del mapa del editor (OpenStreetMap sin key o Google Maps) y la API key, guardada cifrada.">
      <MapBaseSection />
    </Panel>
  );
}

function Sistema() {
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
      <p className="muted small">OWA-EPANET (licencia MIT, Open Water Analytics) · Tipografías Inter e IBM Plex Mono (SIL OFL). Resultados validados contra
        el ejecutable runepanet compilado del mismo tag (docs/validation).</p>
    </Panel>
  );
}

export function PanelAdmin() {
  const { seccion = "resumen", id } = useParams();
  const me = useAuth((s) => s.me);
  if (!me) return null;
  if (!me.is_superadmin) return <Navigate to={PATHS.home} replace />;
  const cur = PANEL_SECTIONS.find((s) => s.id === seccion);
  if (!cur) return <Navigate to={PATHS.panel()} replace />;
  const crumbs = [{ label: "Panel admin", to: PATHS.panel() }, ...(seccion !== "resumen" ? [{ label: cur.label, to: PATHS.panel(seccion) }] : []),
    ...(id ? [{ label: "Ficha" }] : [])];
  return (
    <AppFrame crumbs={crumbs}>
      <div className="page-body ajustes panel-admin">
        <h1 className="page-title">Panel admin</h1>
        <div className="ajustes-layout">
          <nav className="ajustes-nav" aria-label="Secciones del Panel admin">
            <div className="ajustes-group">
              <h2>Panel admin</h2>
              {PANEL_SECTIONS.map((s) => (
                <NavLink key={s.id} to={s.id === "resumen" ? PATHS.panel() : PATHS.panel(s.id)} end={s.id === "resumen"}
                  className={({ isActive }) => (isActive || (s.id === "organizaciones" && !!id) ? "on" : "")}><s.icon /><span>{s.label}</span></NavLink>
              ))}
            </div>
          </nav>
          <div className="ajustes-content" key={`${seccion}-${id ?? ""}`}>
            {seccion === "resumen" && <Resumen />}
            {seccion === "organizaciones" && (id ? <OrgFicha id={id} /> : <Organizaciones />)}
            {seccion === "planes" && <Planes />}
            {seccion === "usuarios" && <Usuarios />}
            {seccion === "mapa-base" && <MapaBase />}
            {seccion === "sistema" && <Sistema />}
          </div>
        </div>
      </div>
    </AppFrame>
  );
}
