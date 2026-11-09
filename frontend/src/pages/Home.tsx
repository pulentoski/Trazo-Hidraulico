// Menú principal: proyectos recientes, nuevo proyecto, importación .inp y accesos a configuración y ayuda.
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router";
import { api } from "../api/client";
import type { ImportPreview, ProjectOut } from "../api/types";
import { PreviewView } from "../components/ExcelImport";
import { Icon } from "../components/Icons";
import { PageHeader } from "../components/PageHeader";
import { fmtDate } from "../lib/format";
import { PATHS } from "../paths";
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

function RecentProjects() {
  const navigate = useNavigate();
  const toast = useEditor((s) => s.toast);
  const [list, setList] = useState<ProjectOut[] | null>(null);
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = () => api.listProjects()
    .then((l) => setList([...l].sort((a, b) => b.updated_at.localeCompare(a.updated_at))))
    .catch((e) => { setList([]); toast(errorText(e), "error"); });
  useEffect(() => { void refresh(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const remove = async (p: ProjectOut) => {
    setBusy(true);
    try {
      await api.deleteProject(p.id);
      toast(`Proyecto «${p.name}» eliminado.`);
      setConfirmId(null);
      await refresh();
    } catch (e) {
      toast(errorText(e), "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="card wide">
      <h2>Proyectos recientes</h2>
      {list === null ? <p className="muted">Cargando…</p> : list.length === 0 ? (
        <p className="muted">Aún no hay proyectos. Cree uno nuevo o importe un archivo .inp.</p>
      ) : (
        <table className="tbl">
          <thead><tr><th>Nombre</th><th>Versión</th><th>Modificado</th><th /></tr></thead>
          <tbody>
            {list.map((p) => (
              <tr key={p.id} className={confirmId === p.id ? "confirming" : ""}>
                <td><Link className="link" to={PATHS.project(p.id)}>{p.name}</Link></td>
                <td>v{p.latest_version}</td>
                <td>{fmtDate(p.updated_at)}</td>
                <td className="right">
                  {confirmId === p.id ? (
                    <span className="confirm-inline" role="alert">
                      ¿Eliminar «{p.name}» y sus {p.version_count} versiones?
                      <button className="danger small" disabled={busy} autoFocus onClick={() => void remove(p)}>Eliminar</button>
                      <button className="ghost small" disabled={busy} onClick={() => setConfirmId(null)}>Cancelar</button>
                    </span>
                  ) : (
                    <>
                      <button className="small" onClick={() => navigate(PATHS.project(p.id))}>Abrir</button>
                      <button className="ghost small" onClick={() => setConfirmId(p.id)}>Eliminar</button>
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

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
    <section className="card">
      <h2><Icon.plus /> Nuevo proyecto</h2>
      <form onSubmit={submit} noValidate>
        <label className={`field stacked ${touched && empty ? "invalid" : ""}`}>
          <span>Nombre <em className="req" aria-hidden>*</em></span>
          <input autoFocus required value={name} onChange={(e) => setName(e.target.value)} onBlur={() => name && setTouched(true)}
            placeholder="Ej.: Red sector norte" aria-invalid={touched && empty} />
        </label>
        {touched && empty && <p className="field-error">El nombre es obligatorio.</p>}
        <p className="muted small">Enter para crear. Usa los criterios de diseño por defecto de la configuración.</p>
        <button className="primary" disabled={busy}>Crear proyecto</button>
      </form>
    </section>
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
    <section className="card">
      <h2><Icon.upload /> Importar .inp (EPANET) o .trazo</h2>
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
        <button className="primary" disabled={busy || !file || tooBig}>{busy ? "Importando…" : "Importar"}</button>
      </form>
    </section>
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
    <section className="card">
      <h2><Icon.table /> Crear desde Excel</h2>
      <form onSubmit={submit}>
        <label className="field stacked"><span>Planilla (.xlsx)</span>
          <input type="file" accept=".xlsx" onChange={(e) => { setFile(e.target.files?.[0] ?? null); setPreview(null); }} />
        </label>
        <label className="field stacked"><span>Nombre del proyecto (opcional)</span>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Ej.: APR Demo" /></label>
        <label className="field stacked"><span>Huso UTM (hemisferio sur)</span>
          <input type="number" min={1} max={60} value={zone} onChange={(e) => setZone(e.target.value)} /></label>
        <p className="muted small"><a href={api.templateUrl}>Descargar plantilla</a>: una hoja por tipo de elemento, con instrucciones.</p>
        <button className="primary" disabled={busy || !file}>{busy ? "Creando…" : "Crear proyecto"}</button>
      </form>
      {preview && <PreviewView p={preview} />}
    </section>
  );
}

export function Home() {
  return (
    <div className="page">
      <PageHeader />
      <main className="page-body home-grid">
        <RecentProjects />
        <div className="stack">
          <NewProject />
          <ImportInp />
          <ImportExcel />
          <section className="card links">
            <Link className="btn ghost" to={PATHS.settings}><Icon.gear /><span>Configuración</span></Link>
            <Link className="btn ghost" to={PATHS.about}><Icon.info /><span>Acerca de</span></Link>
          </section>
        </div>
      </main>
    </div>
  );
}
