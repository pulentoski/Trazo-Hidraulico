// Menú principal: encabezado con identidad, accesos rápidos (nuevo, importar .inp/.trazo, desde Excel, último
// proyecto), proyectos como tarjetas con miniatura del trazado, búsqueda y orden, e indicadores y alertas de la
// organización.
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router";
import { api } from "../api/client";
import type { ImportPreview, ProjectOut } from "../api/types";
import { PreviewView } from "../components/ExcelImport";
import { Icon } from "../components/Icons";
import { Modal } from "../components/Dialogs";
import { PageFooter } from "../components/PageFooter";
import { NetPattern } from "../components/NetPattern";
import { Logo, PageHeader } from "../components/PageHeader";
import { fmt, fmtDate, placeText } from "../lib/format";
import { PATHS } from "../paths";
import { ROLE_LABEL, useAuth } from "../state/auth";
import { errorText } from "../state/projects";
import { readPref, useEditor } from "../state/store";

/** Límite de subida de .inp (igual al de la API y de Caddy). */
export const MAX_INP_MB = 20;

export const CRS_OPTIONS = [
  { value: "auto", label: "Detectar (UTM, lat/lon o locales)" },
  { value: "local", label: "Locales: ubicar en el centro configurado" },
  { value: "EPSG:32719", label: "EPSG:32719 (UTM 19S)" },
  { value: "EPSG:32718", label: "EPSG:32718 (UTM 18S)" },
  { value: "EPSG:4326", label: "EPSG:4326 (lon/lat)" },
];

function NewProject() {
  const navigate = useNavigate();
  const toast = useEditor((s) => s.toast);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [touched, setTouched] = useState(false);
  const empty = !name.trim();
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setTouched(true);
    if (empty) return;
    setBusy(true);
    try {
      const p = await api.createProject(name.trim(), "", null); // perfil por defecto de la organización (Ajustes)
      navigate(PATHS.project(p.id));
    } catch (err) {
      toast(errorText(err), "error");
      setBusy(false);
    }
  };
  return (
    <>
      <form onSubmit={submit} noValidate>
        <label className={`field stacked ${touched && empty ? "invalid" : ""}`}>
          <span>Nombre <em className="req" aria-hidden>*</em></span>
          <input autoFocus required value={name} onChange={(e) => setName(e.target.value)} onBlur={() => name && setTouched(true)}
            placeholder="Ej.: Red sector norte" aria-invalid={touched && empty} />
        </label>
        {touched && empty && <p className="field-error">El nombre es obligatorio.</p>}
        <p className="muted small">Enter para crear. Usa los criterios de diseño por defecto de la configuración.</p>
        <div className="modal-actions"><button className="primary" disabled={busy}>Crear proyecto</button></div>
      </form>
    </>
  );
}

function ImportInp() {
  const navigate = useNavigate();
  const toast = useEditor((s) => s.toast);
  const [file, setFile] = useState<File | null>(null);
  const [crs, setCrs] = useState("auto");
  const [busy, setBusy] = useState(false);
  const tooBig = !!file && file.size > MAX_INP_MB * 1024 * 1024;
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file || tooBig) return;
    setBusy(true);
    try {
      if (/\.trazo$/i.test(file.name)) {
        const t = await api.importTrazo(file);
        toast(`Proyecto .trazo importado (versión ${t.version}). ${t.notes.join(" ")}`);
        navigate(PATHS.project(t.project.id));
        return;
      }
      const r = await api.importInp(file, undefined, crs);
      toast(`Importado: ${r.node_count} nudos y ${r.link_count} tramos (${r.georeference}). ${r.notes.join(" ")}`);
      navigate(PATHS.project(r.project.id));
    } catch (err) {
      toast(errorText(err), "error");
      setBusy(false);
    }
  };
  return (
    <>
      <form onSubmit={submit}>
        <label className="field stacked"><span>Archivo</span>
          <input type="file" accept=".inp,.trazo" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </label>
        {tooBig && <p className="field-error">El archivo supera {MAX_INP_MB} MB.</p>}
        <label className="field stacked"><span>Sistema de coordenadas del archivo</span>
          <select value={crs} onChange={(e) => setCrs(e.target.value)}>
            {CRS_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </label>
        <p className="muted small">Las unidades se convierten a SI (L/s). Las cotas quedan con fuente «.inp»; si faltan, se advierte.
          Se conservan [VERTICES], [LABELS] y [TAGS]; las coordenadas UTM, lat/lon o locales se detectan solas. Un .trazo trae el proyecto completo.</p>
        <div className="modal-actions"><button className="primary" disabled={busy || !file || tooBig}>{busy ? "Importando…" : "Importar"}</button></div>
      </form>
    </>
  );
}

function ImportExcel() {
  const navigate = useNavigate();
  const toast = useEditor((s) => s.toast);
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState("");
  const [zone, setZone] = useState("19");
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    try {
      const r = await api.createFromExcel(file, { name: name.trim() || undefined, utm_zone: Number(zone) || null });
      if (!r.preview.ok) { setPreview(r.preview); toast("La planilla tiene errores: no se creó el proyecto.", "error"); return; }
      toast(`Proyecto creado desde la planilla: ${r.preview.new?.length ?? 0} elementos.`);
      navigate(PATHS.project(r.project_id));
    } catch (err) {
      toast(errorText(err), "error");
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <form onSubmit={submit}>
        <label className="field stacked"><span>Planilla (.xlsx)</span>
          <input type="file" accept=".xlsx" onChange={(e) => { setFile(e.target.files?.[0] ?? null); setPreview(null); }} />
        </label>
        <label className="field stacked"><span>Nombre del proyecto (opcional)</span>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Ej.: APR Demo" /></label>
        <label className="field stacked"><span>Huso UTM (hemisferio sur)</span>
          <input type="number" min={1} max={60} value={zone} onChange={(e) => setZone(e.target.value)} /></label>
        <p className="muted small"><a href={api.templateUrl}>Descargar plantilla</a>: una hoja por tipo de elemento, con instrucciones.</p>
        <div className="modal-actions"><button className="primary" disabled={busy || !file}>{busy ? "Creando…" : "Crear proyecto"}</button></div>
      </form>
      {preview && <PreviewView p={preview} />}
    </>
  );
}

type Create = "new" | "import" | "excel" | null;
type Order = "recent" | "name";

const CREATE: { id: Exclude<Create, null>; icon: () => React.ReactElement; title: string; text: string; cls?: string }[] = [
  { id: "new", icon: Icon.plus, title: "Nuevo proyecto", text: "Mapa en blanco: dibuje la red.", cls: "cta" },
  { id: "import", icon: Icon.upload, title: "Importar .inp o .trazo", text: "Modelo de EPANET o proyecto guardado." },
  { id: "excel", icon: Icon.csv, title: "Desde Excel", text: "Nudos, tramos y clientes desde una planilla." },
];

/** Miniatura del trazado de la red (SVG generado desde el listado: coordenadas 0–1000). */
export function NetThumb({ outline, name }: { outline: number[][] | null | undefined; name: string }) {
  return (
    <svg className="net-thumb" viewBox="0 0 1000 1000" preserveAspectRatio="xMidYMid meet" role="img"
      aria-label={outline?.length ? `Trazado de la red de «${name}»` : `«${name}» todavía no tiene tramos`}>
      {outline?.length ? outline.map((l, i) => {
        const pts: string[] = [];
        for (let k = 0; k + 1 < l.length; k += 2) pts.push(`${l[k]},${l[k + 1]}`);
        return <polyline key={i} points={pts.join(" ")} />;
      }) : <g className="net-thumb-empty"><circle cx="500" cy="500" r="60" /><path d="M300 640 L440 520 M560 480 L700 360" /></g>}
    </svg>
  );
}

function ProjectCard({ p, onDelete }: { p: ProjectOut; onDelete: (p: ProjectOut) => Promise<void> }) {
  const navigate = useNavigate();
  const [menu, setMenu] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!menu) return;
    const close = (e: MouseEvent) => { if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenu(false); };
    const key = (e: KeyboardEvent) => e.key === "Escape" && setMenu(false);
    window.addEventListener("mousedown", close);
    window.addEventListener("keydown", key);
    return () => { window.removeEventListener("mousedown", close); window.removeEventListener("keydown", key); };
  }, [menu]);
  const overdue = p.overdue_tasks ?? 0;
  return (
    <article className={`project-card ${confirm ? "confirming" : ""}`} data-card={p.id} aria-label={p.name}>
      <Link className="project-main" to={PATHS.project(p.id)} title={`Abrir «${p.name}» en el editor`}>
        <span className="project-thumb"><NetThumb outline={p.outline} name={p.name} />
          {overdue > 0 && <span className="thumb-badge" title={`${overdue} mantenciones atrasadas`}><Icon.wrench />{overdue}</span>}</span>
        <span className="project-title">{p.name}</span>
        <span className="project-place"><Icon.pin />{placeText(p.center)}</span>
        <span className="project-stats">
          <span><b>{p.client_count ?? 0}</b> clientes</span>
          <span><b>{fmt(p.network_km ?? 0, 2)}</b> km de red</span>
        </span>
        <span className="project-meta"><Icon.clock />v{p.latest_version ?? "—"} · {fmtDate(p.updated_at)}</span>
      </Link>
      {confirm ? (
        <div className="confirm-inline" role="alert">
          <span>¿Eliminar «{p.name}» y sus {p.version_count} versiones? No se puede deshacer.</span>
          <span className="confirm-actions">
            <button className="ghost small" disabled={busy} onClick={() => setConfirm(false)}>Cancelar</button>
            <button className="danger small" disabled={busy} autoFocus onClick={async () => { setBusy(true); await onDelete(p); setBusy(false); setConfirm(false); }}>
              <Icon.trash /><span>Eliminar</span></button>
          </span>
        </div>
      ) : (
        <div className="project-actions">
          <button className="small ghost danger-text icon-btn" onClick={() => setConfirm(true)} aria-label={`Eliminar «${p.name}»`} title="Eliminar el proyecto (pide confirmación)">
            <Icon.trash /></button>
          <span className="spacer" />
          <div className="card-menu menu-wrap" ref={menuRef}>
            <button className="small" onClick={() => setMenu(!menu)} aria-expanded={menu} aria-haspopup="menu" aria-label={`Exportar «${p.name}»`} title="Exportar el proyecto">
              <Icon.download /><Icon.chevronDown /></button>
            {menu && (
              <div className="menu-pop right" role="menu">
                <a className="menu-item" role="menuitem" href={api.trazoUrl(p.id)} onClick={() => setMenu(false)}><Icon.download /><span>Proyecto .trazo</span></a>
                <a className="menu-item" role="menuitem" href={api.exportUrl(p.id)} onClick={() => setMenu(false)}><Icon.download /><span>Modelo .inp (EPANET)</span></a>
                <a className="menu-item" role="menuitem" href={api.excelUrl(p.id)} onClick={() => setMenu(false)}><Icon.download /><span>Planilla Excel</span></a>
              </div>
            )}
          </div>
          <button className="small" onClick={() => navigate(PATHS.gestion(p.id))} title="Indicadores, registros de operación e informe mensual">
            <Icon.gestion /><span>Gestión</span></button>
          <button className="small primary" onClick={() => navigate(PATHS.project(p.id))} title="Abrir en el editor"><Icon.folder /><span>Abrir</span></button>
        </div>
      )}
    </article>
  );
}

function SkeletonCards() {
  return (
    <div className="project-grid" aria-busy="true" aria-label="Cargando proyectos">
      {[0, 1, 2].map((i) => (
        <div key={i} className="project-card skeleton-card" aria-hidden="true">
          <span className="skel skel-thumb" /><span className="skel skel-line w70" /><span className="skel skel-line w50" />
          <span className="skel skel-line w40" />
        </div>
      ))}
    </div>
  );
}

/** Proyecto de ejemplo completo (red y 24 meses de gestión), servido junto a la aplicación. */
export const EXAMPLE_TRAZO = "ejemplos/apr-ejemplo-valle-elqui.trazo";

function LoadExample() {
  const navigate = useNavigate();
  const toast = useEditor((s) => s.toast);
  const [busy, setBusy] = useState(false);
  const load = async () => {
    setBusy(true);
    try {
      const res = await fetch(`${import.meta.env.BASE_URL}${EXAMPLE_TRAZO}`);
      if (!res.ok) throw new Error(`No se encontró el proyecto de ejemplo (${res.status}).`);
      const file = new File([await res.blob()], "apr-ejemplo-valle-elqui.trazo", { type: "application/zip" });
      const t = await api.importTrazo(file);
      toast(`Proyecto de ejemplo cargado: «${t.project.name}».`);
      navigate(PATHS.project(t.project.id));
    } catch (err) {
      toast(errorText(err), "error");
      setBusy(false);
    }
  };
  return (
    <button onClick={load} disabled={busy} title="APR rural ficticio con red completa y 24 meses de registros de gestión">
      <Icon.download /><span>{busy ? "Cargando ejemplo…" : "Cargar proyecto de ejemplo"}</span>
    </button>
  );
}

function EmptyState({ onCreate }: { onCreate: (c: Create) => void }) {
  return (
    <div className="empty-state">
      <svg viewBox="0 0 160 100" aria-hidden="true" className="empty-art">
        <path className="ea-contour" d="M4 70 C 40 52, 70 84, 104 64 S 150 40, 158 52" />
        <path className="ea-contour" d="M4 84 C 44 66, 74 98, 108 78 S 150 56, 158 66" />
        <path className="ea-pipe" d="M22 66 L54 40 L86 56 L120 26" />
        <circle cx="22" cy="66" r="5" /><circle cx="54" cy="40" r="5" /><circle cx="86" cy="56" r="5" /><circle className="warm" cx="120" cy="26" r="6" />
        <path className="ea-drop" d="M138 54c-4 5-7 9-7 12.5a7 7 0 0 0 14 0c0-3.5-3-7.5-7-12.5z" />
      </svg>
      <h3>Todavía no hay proyectos</h3>
      <p className="muted">Tres pasos para tener su primera red simulada:</p>
      <ol className="steps-guide">
        <li><b>1</b><span><strong>Cree o importe</strong> la red: mapa en blanco, modelo .inp/.trazo o planilla Excel.</span></li>
        <li><b>2</b><span><strong>Dibuje y complete</strong> nudos, tuberías, estanques y clientes con las herramientas.</span></li>
        <li><b>3</b><span><strong>Simule</strong> (F5): presiones, velocidades y alertas al instante.</span></li>
      </ol>
      <div className="inline">
        <button onClick={() => onCreate("excel")}><Icon.csv /><span>Desde Excel</span></button>
        <button onClick={() => onCreate("import")}><Icon.upload /><span>Importar</span></button>
        <LoadExample />
        <button className="cta" onClick={() => onCreate("new")}><Icon.plus /><span>Nuevo proyecto</span></button>
      </div>
      <p className="muted small">«Cargar proyecto de ejemplo» importa el APR Ejemplo Valle de Elqui (datos ficticios) con todos
        los datos de gestión; el archivo está en <code>examples/apr-ejemplo-valle-elqui.trazo</code>.</p>
    </div>
  );
}

function OrgPanel({ list, orgName }: { list: ProjectOut[] | null; orgName: string }) {
  const clients = (list ?? []).reduce((a, p) => a + (p.client_count ?? 0), 0);
  const km = (list ?? []).reduce((a, p) => a + (p.network_km ?? 0), 0);
  const late = (list ?? []).filter((p) => (p.overdue_tasks ?? 0) > 0).sort((a, b) => (b.overdue_tasks ?? 0) - (a.overdue_tasks ?? 0));
  return (
    <aside className="org-panel" aria-label="Indicadores de la organización">
      <section className="org-card">
        <h2><Icon.org />{orgName || "Organización"}</h2>
        {list === null ? <div className="org-stats"><span className="skel skel-stat" /><span className="skel skel-stat" /><span className="skel skel-stat" /></div> : (
          <dl className="org-stats">
            <div><dt>Proyectos</dt><dd>{list.length}</dd></div>
            <div><dt>Clientes</dt><dd>{fmt(clients, 0)}</dd></div>
            <div><dt>Km de red</dt><dd>{fmt(km, 1)}</dd></div>
          </dl>
        )}
      </section>
      <section className="org-card" aria-label="Alertas pendientes">
        <h2><Icon.alert />Alertas pendientes {late.length > 0 && <span className="count warn">{late.reduce((a, p) => a + (p.overdue_tasks ?? 0), 0)}</span>}</h2>
        {list === null ? <span className="skel skel-line w70" /> : late.length === 0 ? (
          <p className="all-clear"><Icon.check />Sin mantenciones atrasadas.</p>
        ) : (
          <ul className="alert-items">
            {late.map((p) => (
              <li key={p.id}>
                <Link to={PATHS.gestion(p.id)} title={`Abrir Gestión de «${p.name}»`}>
                  <Icon.wrench /><span><b>{p.name}</b><small>{p.overdue_tasks} {p.overdue_tasks === 1 ? "mantención atrasada" : "mantenciones atrasadas"}</small></span>
                  <Icon.chevronRight />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </aside>
  );
}

export function Home() {
  const me = useAuth((s) => s.me);
  const toast = useEditor((s) => s.toast);
  const navigate = useNavigate();
  const [list, setList] = useState<ProjectOut[] | null>(null);
  const [q, setQ] = useState("");
  const [order, setOrder] = useState<Order>("recent");
  const [create, setCreate] = useState<Create>(null);
  const org = me?.orgs.find((o) => o.id === me.current_org);
  const refresh = () => api.listProjects()
    .then((l) => setList([...l].sort((a, b) => b.updated_at.localeCompare(a.updated_at))))
    .catch((e) => { setList([]); toast(errorText(e), "error"); });
  useEffect(() => { void refresh(); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const remove = async (p: ProjectOut) => {
    try { await api.deleteProject(p.id); toast(`Proyecto «${p.name}» eliminado.`); await refresh(); } catch (e) { toast(errorText(e), "error"); }
  };
  const norm = (t: string) => t.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  const shown = useMemo(() => {
    const f = (list ?? []).filter((p) => !q.trim() || norm(p.name).includes(norm(q.trim())));
    return order === "name" ? [...f].sort((a, b) => a.name.localeCompare(b.name, "es", { numeric: true })) : f;
  }, [list, q, order]);
  const lastId = readPref<string | null>("lastProject", null);
  const last = list?.find((p) => p.id === lastId) ?? list?.[0] ?? null;
  const hour = new Date().getHours();
  const hello = hour < 12 ? "Buenos días" : hour < 20 ? "Buenas tardes" : "Buenas noches";
  const firstName = (me?.name || me?.email || "").split(/[\s@]/)[0];
  const today = new Date().toLocaleDateString("es-CL", { weekday: "long", day: "numeric", month: "long" });

  return (
    <div className="page">
      <PageHeader />
      <section className="home-hero" aria-label="Bienvenida">
        <NetPattern />
        <div className="home-hero-inner">
          <Logo size={52} />
          <div>
            <p className="hero-date">{today}</p>
            <h1>{hello}{firstName ? `, ${firstName}` : ""}</h1>
            <p className="hero-org">{org ? <><Icon.org />{org.name} · {ROLE_LABEL[org.role]}</> : "Diseño y simulación de redes de agua potable"}</p>
          </div>
        </div>
      </section>
      <main className="page-body home">
        <section aria-label="Accesos rápidos" className="quick-grid">
          {CREATE.map((c) => (
            <button key={c.id} className={`quick-card ${c.cls ?? ""}`} onClick={() => setCreate(c.id)}>
              <span className="quick-icon" aria-hidden="true"><c.icon /></span>
              <span className="quick-title">{c.title}</span>
              <span className="quick-text">{c.text}</span>
            </button>
          ))}
          <button className="quick-card" disabled={!last} onClick={() => last && navigate(PATHS.project(last.id))}
            title={last ? `Abrir «${last.name}»` : "Todavía no hay proyectos"}>
            <span className="quick-icon" aria-hidden="true"><Icon.history /></span>
            <span className="quick-title">Abrir el último proyecto</span>
            <span className="quick-text">{last ? last.name : list === null ? "…" : "Todavía no hay proyectos."}</span>
          </button>
        </section>
        <div className="home-layout">
          <section className="projects" aria-label="Proyectos">
            <div className="projects-head">
              <h2>Proyectos {list && list.length > 0 && <span className="count">{list.length}</span>}</h2>
              {list && list.length > 0 && (<>
                <label className="project-search"><Icon.search />
                  <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar proyecto…" aria-label="Buscar proyecto" /></label>
                <div className="seg plain order-seg" role="group" aria-label="Ordenar proyectos">
                  <Icon.sort />
                  <button className={order === "recent" ? "on" : ""} aria-pressed={order === "recent"} onClick={() => setOrder("recent")} title="Los modificados más recientemente primero">Recientes</button>
                  <button className={order === "name" ? "on" : ""} aria-pressed={order === "name"} onClick={() => setOrder("name")} title="Orden alfabético">Nombre</button>
                </div>
              </>)}
            </div>
            {list === null ? <SkeletonCards />
              : list.length === 0 ? <EmptyState onCreate={setCreate} />
                : shown.length === 0 ? <p className="muted pad">Ningún proyecto coincide con «{q}».</p>
                  : <div className="project-grid">{shown.map((p) => <ProjectCard key={p.id} p={p} onDelete={remove} />)}</div>}
          </section>
          <OrgPanel list={list} orgName={org?.name ?? ""} />
        </div>
      </main>
      <PageFooter />
      {create === "new" && <Modal title="Nuevo proyecto" onClose={() => setCreate(null)}><NewProject /></Modal>}
      {create === "import" && <Modal title="Importar .inp (EPANET) o .trazo" onClose={() => setCreate(null)}><ImportInp /></Modal>}
      {create === "excel" && <Modal title="Crear desde Excel" onClose={() => setCreate(null)} wide><ImportExcel /></Modal>}
    </div>
  );
}
