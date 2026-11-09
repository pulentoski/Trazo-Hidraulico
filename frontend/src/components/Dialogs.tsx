import { useEffect, useState } from "react";
import { api, ApiError } from "../api/client";
import type { ProjectOut, VersionOut } from "../api/types";
import { fmtDate } from "../lib/format";
import { removeElements, useEditor } from "../state/store";

export function Modal({ title, onClose, children, wide }: { title: string; onClose: () => void; children: React.ReactNode; wide?: boolean }) {
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  return (
    <div className="modal-back" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className={`modal ${wide ? "wide" : ""}`} role="dialog" aria-modal="true" aria-label={title}>
        <header><h2>{title}</h2><button className="ghost" onClick={onClose} aria-label="Cerrar">✕</button></header>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  );
}

export function ConfirmDelete() {
  const { pendingDelete, net, confirmDelete, cancelDelete } = useEditor();
  if (!pendingDelete) return null;
  const nodes = pendingDelete.filter((u) => net.nodes[u]).map((u) => net.nodes[u].id);
  const links = pendingDelete.filter((u) => net.links[u]).map((u) => net.links[u].id);
  const after = removeElements(net, pendingDelete);
  const cascade = Object.keys(net.links).length - Object.keys(after.links).length - links.length;
  return (
    <Modal title="Confirmar eliminación" onClose={cancelDelete}>
      <p>
        Se eliminarán {nodes.length > 0 && <>los nudos <strong>{nodes.slice(0, 8).join(", ")}{nodes.length > 8 ? "…" : ""}</strong></>}
        {nodes.length > 0 && links.length > 0 && " y "}
        {links.length > 0 && <>los tramos <strong>{links.slice(0, 8).join(", ")}{links.length > 8 ? "…" : ""}</strong></>}.
      </p>
      {cascade > 0 && <p className="warn-text">También se eliminarán {cascade} tramos conectados a esos nudos.</p>}
      <p className="muted">Puede deshacer la acción con Ctrl+Z.</p>
      <div className="modal-actions">
        <button className="ghost" onClick={cancelDelete}>Cancelar</button>
        <button className="danger" autoFocus onClick={confirmDelete}>Eliminar</button>
      </div>
    </Modal>
  );
}

export async function openProject(id: string, version?: number) {
  const st = useEditor.getState();
  const [project, doc] = await Promise.all([api.getProject(id), api.getNetwork(id, version)]);
  st.loadDocument(project, doc);
  const { simulateVersion } = await import("../state/live");
  if ((doc.network.features ?? []).length) await simulateVersion(doc.version, useEditor.getState().revision).catch(() => undefined);
}

export function ProjectsDialog() {
  const { projectsOpen, project, set, toast } = useEditor();
  const [list, setList] = useState<ProjectOut[] | null>(null);
  const [name, setName] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [crs, setCrs] = useState("auto");
  const [busy, setBusy] = useState(false);
  const [confirmId, setConfirmId] = useState<string | null>(null);

  const refresh = () => api.listProjects().then(setList).catch(() => setList([]));
  useEffect(() => {
    if (projectsOpen) void refresh();
  }, [projectsOpen]);
  if (!projectsOpen) return null;
  const close = () => project && set({ projectsOpen: false });

  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    try {
      await fn();
    } catch (e) {
      const body = e instanceof ApiError ? e.body as { detail?: { engine_messages?: { message: string }[] } } : null;
      const engine = body?.detail?.engine_messages?.map((m) => m.message).join(" ");
      toast(engine || (e instanceof Error ? e.message : "Error"), "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal title="Proyectos" onClose={close} wide>
      <div className="proj-grid">
        <section>
          <h3>Abrir</h3>
          {list === null ? <p className="muted">Cargando…</p> : list.length === 0 ? <p className="muted">Aún no hay proyectos.</p> : (
            <table className="tbl">
              <thead><tr><th>Nombre</th><th>Versión</th><th>Modificado</th><th /></tr></thead>
              <tbody>
                {list.map((p) => (
                  <tr key={p.id} className={p.id === project?.id ? "current" : ""}>
                    <td><button className="link" disabled={busy} onClick={() => run(async () => { await openProject(p.id); set({ projectsOpen: false }); })}>{p.name}</button></td>
                    <td>v{p.latest_version}</td>
                    <td>{fmtDate(p.updated_at)}</td>
                    <td className="right">
                      {confirmId === p.id ? (
                        <>
                          <button className="danger small" onClick={() => run(async () => {
                            await api.deleteProject(p.id);
                            setConfirmId(null);
                            if (project?.id === p.id) useEditor.getState().closeProject();
                            await refresh();
                          })}>Confirmar</button>
                          <button className="ghost small" onClick={() => setConfirmId(null)}>No</button>
                        </>
                      ) : <button className="ghost small" onClick={() => setConfirmId(p.id)}>Eliminar</button>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
        <section>
          <h3>Nuevo proyecto</h3>
          <form onSubmit={(e) => { e.preventDefault(); if (name.trim()) void run(async () => { const p = await api.createProject(name.trim()); await openProject(p.id); setName(""); set({ projectsOpen: false }); }); }}>
            <label className="field"><span>Nombre</span><input value={name} onChange={(e) => setName(e.target.value)} placeholder="Red sector norte" /></label>
            <button className="primary" disabled={busy || !name.trim()}>Crear</button>
          </form>
          <h3>Importar .inp (EPANET)</h3>
          <form onSubmit={(e) => { e.preventDefault(); if (file) void run(async () => {
            const r = await api.importInp(file, undefined, crs);
            await openProject(r.project.id);
            set({ projectsOpen: false });
            toast(`Importado: ${r.node_count} nudos y ${r.link_count} tramos (${r.georeference}). ${r.notes.join(" ")}`);
          }); }}>
            <label className="field"><span>Archivo</span><input type="file" accept=".inp" onChange={(e) => setFile(e.target.files?.[0] ?? null)} /></label>
            <label className="field"><span>Coordenadas del archivo</span>
              <select value={crs} onChange={(e) => setCrs(e.target.value)}>
                <option value="auto">Detectar (UTM 19S o locales)</option>
                <option value="local">Locales: ubicar en el centro configurado</option>
                <option value="EPSG:32719">EPSG:32719 (UTM 19S)</option>
                <option value="EPSG:32718">EPSG:32718 (UTM 18S)</option>
                <option value="EPSG:4326">EPSG:4326 (lon/lat)</option>
              </select>
            </label>
            <p className="muted">Unidades convertidas a SI (L/s) por el motor. Las cotas quedan con fuente «.inp».</p>
            <button className="primary" disabled={busy || !file}>Importar</button>
          </form>
        </section>
      </div>
    </Modal>
  );
}

export function VersionsDialog() {
  const { versionsOpen, project, serverVersion, set, toast } = useEditor();
  const [list, setList] = useState<VersionOut[] | null>(null);
  const [showAuto, setShowAuto] = useState(false);
  useEffect(() => {
    if (versionsOpen && project) api.listVersions(project.id).then(setList).catch(() => setList([]));
  }, [versionsOpen, project, serverVersion]);
  if (!versionsOpen || !project) return null;
  const close = () => set({ versionsOpen: false });
  const rows = (list ?? []).filter((v) => showAuto || v.kind !== "auto" || v.number === serverVersion);

  const restore = async (v: VersionOut) => {
    const st = useEditor.getState();
    if (st.revision !== st.savedRevision) return toast("Espere a que termine el guardado automático.", "error");
    const doc = await api.getNetwork(project.id, v.number);
    const res = await api.saveNetwork(project.id, {
      base_version: st.serverVersion, kind: "manual", label: `Restaurada desde v${v.number}`,
      options: doc.options, aux: doc.aux, network: doc.network,
    });
    await openProject(project.id, res.version);
    toast(`Versión ${v.number} restaurada como v${res.version}.`);
    close();
  };

  return (
    <Modal title={`Versiones de «${project.name}»`} onClose={close} wide>
      <label className="inline"><input type="checkbox" checked={showAuto} onChange={(e) => setShowAuto(e.target.checked)} /> Mostrar guardados automáticos</label>
      <p className="muted">Cada guardado crea una versión inmutable; las simulaciones quedan ligadas a la versión que las generó.</p>
      <table className="tbl">
        <thead><tr><th>Versión</th><th>Tipo</th><th>Etiqueta</th><th>Fecha</th><th>Nudos</th><th>Tramos</th><th>Resultados</th><th /></tr></thead>
        <tbody>
          {rows.map((v) => (
            <tr key={v.number} className={v.number === serverVersion ? "current" : ""}>
              <td>v{v.number}</td>
              <td>{{ auto: "automático", manual: "manual", import: "importación" }[v.kind]}</td>
              <td>{v.label ?? ""}</td>
              <td>{fmtDate(v.created_at)}</td>
              <td className="num">{v.node_count}</td>
              <td className="num">{v.link_count}</td>
              <td>{v.has_results ? "sí" : "—"}</td>
              <td className="right">
                <a className="btn ghost small" href={api.exportUrl(project.id, v.number)}>.inp</a>
                {v.number !== serverVersion && <button className="ghost small" onClick={() => void restore(v)}>Restaurar</button>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Modal>
  );
}

export function Toasts() {
  const { toasts, dismissToast } = useEditor();
  return (
    <div className="toasts" aria-live="polite">
      {toasts.map((t) => <div key={t.id} className={`toast ${t.kind}`} onClick={() => dismissToast(t.id)}>{t.text}</div>)}
    </div>
  );
}
