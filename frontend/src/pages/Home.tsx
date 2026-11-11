// Menú principal: saludo, formas de crear un proyecto (nuevo, importar .inp/.trazo, desde Excel) y proyectos con búsqueda.
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router";
import { api } from "../api/client";
import type { ImportPreview, ProjectOut } from "../api/types";
import { PreviewView } from "../components/ExcelImport";
import { Icon } from "../components/Icons";
import { Modal } from "../components/Dialogs";
import { PageHeader } from "../components/PageHeader";
import { fmt, fmtDate } from "../lib/format";
import { PATHS } from "../paths";
import { ROLE_LABEL, useAuth } from "../state/auth";
import { errorText } from "../state/projects";
import { useEditor } from "../state/store";

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
  const { toast, defaultProfileId } = useEditor();
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
      const p = await api.createProject(name.trim(), "", defaultProfileId);
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

const CREATE: { id: Exclude<Create, null>; icon: () => React.ReactElement; title: string; text: string }[] = [
  { id: "new", icon: Icon.plus, title: "Nuevo proyecto", text: "Empiece con un mapa en blanco y dibuje la red." },
  { id: "import", icon: Icon.upload, title: "Importar .inp o .trazo", text: "Abra un modelo de EPANET o un proyecto guardado." },
  { id: "excel", icon: Icon.table, title: "Desde Excel", text: "Cargue nudos, tramos y clientes desde una planilla." },
];

function ProjectCard({ p, onDelete }: { p: ProjectOut; onDelete: (p: ProjectOut) => Promise<void> }) {
  const navigate = useNavigate();
  const [menu, setMenu] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!menu) return;
    const close = (e: MouseEvent) => { if (!(e.target as Element).closest?.(`[data-card="${p.id}"] .card-menu`)) setMenu(false); };
    window.addEventListener("mousedown", close);
    return () => window.removeEventListener("mousedown", close);
  }, [menu, p.id]);
  return (
    <article className={`project-card ${confirm ? "confirming" : ""}`} data-card={p.id} aria-label={p.name}>
      <Link className="project-main" to={PATHS.project(p.id)} title={`Abrir «${p.name}»`}>
        <span className="project-icon" aria-hidden><Icon.pipe /></span>
        <span className="project-title">{p.name}</span>
        <span className="project-meta">v{p.latest_version ?? "—"} · {fmtDate(p.updated_at)}</span>
        <span className="project-stats">
          <span><b>{p.client_count ?? 0}</b> clientes</span>
          <span><b>{fmt(p.network_km ?? 0, 2)}</b> km de red</span>
        </span>
      </Link>
      {confirm ? (
        <div className="confirm-inline" role="alert">
          ¿Eliminar «{p.name}» y sus {p.version_count} versiones?
          <button className="danger small" disabled={busy} autoFocus onClick={async () => { setBusy(true); await onDelete(p); setBusy(false); setConfirm(false); }}>Eliminar</button>
          <button className="ghost small" disabled={busy} onClick={() => setConfirm(false)}>Cancelar</button>
        </div>
      ) : (
        <div className="project-actions">
          <button className="small primary" onClick={() => navigate(PATHS.project(p.id))}>Abrir</button>
          <div className="card-menu menu-wrap">
            <button className="small ghost" onClick={() => setMenu(!menu)} aria-expanded={menu} aria-label={`Más acciones de «${p.name}»`} title="Más acciones">⋯</button>
            {menu && (
              <div className="menu-pop right" role="menu">
                <a className="menu-item" role="menuitem" href={api.trazoUrl(p.id)} onClick={() => setMenu(false)}>Descargar .trazo</a>
                <a className="menu-item" role="menuitem" href={api.excelUrl(p.id)} onClick={() => setMenu(false)}>Exportar Excel</a>
                <button className="menu-item danger-text" role="menuitem" onClick={() => { setMenu(false); setConfirm(true); }}>Eliminar…</button>
              </div>
            )}
          </div>
        </div>
      )}
    </article>
  );
}

function EmptyState({ onCreate }: { onCreate: (c: Create) => void }) {
  return (
    <div className="empty-state">
      <svg viewBox="0 0 120 80" aria-hidden className="empty-art">
        <path d="M10 62 L38 34 L62 50 L92 18" /><circle cx="10" cy="62" r="5" /><circle cx="38" cy="34" r="5" />
        <circle cx="62" cy="50" r="5" /><circle cx="92" cy="18" r="5" /><path d="M100 50c0-6 6-12 6-12s6 6 6 12a6 6 0 0 1-12 0z" />
      </svg>
      <h3>Todavía no hay proyectos</h3>
      <p className="muted">Cree su primera red o importe un modelo existente. La demostración «APR Demo» está en <code>examples/apr-demo.xlsx</code>.</p>
      <div className="inline">
        <button className="primary" onClick={() => onCreate("new")}><Icon.plus /><span>Nuevo proyecto</span></button>
        <button onClick={() => onCreate("import")}><Icon.upload /><span>Importar</span></button>
        <button onClick={() => onCreate("excel")}><Icon.table /><span>Desde Excel</span></button>
      </div>
    </div>
  );
}

export function Home() {
  const me = useAuth((s) => s.me);
  const toast = useEditor((s) => s.toast);
  const [list, setList] = useState<ProjectOut[] | null>(null);
  const [q, setQ] = useState("");
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
  const shown = (list ?? []).filter((p) => !q.trim() || norm(p.name).includes(norm(q.trim())));
  const hour = new Date().getHours();
  const hello = hour < 12 ? "Buenos días" : hour < 20 ? "Buenas tardes" : "Buenas noches";
  const firstName = (me?.name || me?.email || "").split(/[\s@]/)[0];

  return (
    <div className="page">
      <PageHeader />
      <main className="page-body home">
        <section className="home-hero">
          <div>
            <h1>{hello}{firstName ? `, ${firstName}` : ""}</h1>
            <p className="muted">{org ? <>{org.name} · {ROLE_LABEL[org.role]}</> : "Diseño y simulación de redes de agua potable"}</p>
          </div>
        </section>
        <section aria-label="Crear un proyecto" className="create-grid">
          {CREATE.map((c) => (
            <button key={c.id} className="create-card" onClick={() => setCreate(c.id)}>
              <span className="create-icon" aria-hidden><c.icon /></span>
              <span className="create-title">{c.title}</span>
              <span className="create-text">{c.text}</span>
            </button>
          ))}
        </section>
        <section className="projects" aria-label="Proyectos">
          <div className="projects-head">
            <h2>Proyectos {list && list.length > 0 && <span className="count">{list.length}</span>}</h2>
            {list && list.length > 0 && (
              <label className="project-search"><Icon.search />
                <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar proyecto…" aria-label="Buscar proyecto" /></label>
            )}
          </div>
          {list === null ? <p className="muted">Cargando…</p>
            : list.length === 0 ? <EmptyState onCreate={setCreate} />
              : shown.length === 0 ? <p className="muted pad">Ningún proyecto coincide con «{q}».</p>
                : <div className="project-grid">{shown.map((p) => <ProjectCard key={p.id} p={p} onDelete={remove} />)}</div>}
        </section>
      </main>
      {create === "new" && <Modal title="Nuevo proyecto" onClose={() => setCreate(null)}><NewProject /></Modal>}
      {create === "import" && <Modal title="Importar .inp (EPANET) o .trazo" onClose={() => setCreate(null)}><ImportInp /></Modal>}
      {create === "excel" && <Modal title="Crear desde Excel" onClose={() => setCreate(null)} wide><ImportExcel /></Modal>}
    </div>
  );
}
