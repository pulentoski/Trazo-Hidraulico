// Pestaña «Capas»: ortofotos del proyecto (subir, georreferenciar, opacidad, encender/apagar, eliminar).
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { OrthophotoOut } from "../api/types";
import { fmt } from "../lib/format";
import type { LngLat } from "../lib/geo";
import { errorText } from "../state/projects";
import { useEditor } from "../state/store";
import type { Progress } from "../lib/upload";
import { UploadError, fmtBytes, fmtEta, rememberedUpload, uploadInParts } from "../lib/upload";
import { Help } from "./Fields";
import { GeorefWizard } from "./GeorefWizard";

const STATUS: Record<OrthophotoOut["status"], string> = {
  uploading: "subiendo", uploaded: "sin ubicar en el mapa", pending: "en cola", processing: "procesando", ready: "lista", error: "error",
};
const RESOLUTIONS: [string, string][] = [["", "Resolución original"], ["10", "Reducir a 10 cm/píxel"], ["20", "Reducir a 20 cm/píxel"], ["50", "Reducir a 50 cm/píxel"]];

interface Job { file: File; progress: Progress; ctrl: AbortController; state: "subiendo" | "pausada" | "error"; message?: string; oid?: string }

export function useOrthos() {
  const project = useEditor((s) => s.project);
  const set = useEditor((s) => s.set);
  const orthos = useEditor((s) => s.orthos);
  const refresh = useCallback(async () => {
    if (!project) return;
    try { set({ orthos: await api.orthos(project.id) }); } catch { /* sin capas */ }
  }, [project, set]);
  useEffect(() => { void refresh(); }, [refresh]);
  const busy = orthos.some((o) => o.status === "pending" || o.status === "processing" || o.status === "uploading");
  useEffect(() => {
    if (!busy) return;
    const t = window.setInterval(() => void refresh(), 3000);
    return () => window.clearInterval(t);
  }, [busy, refresh]);
  return { orthos, refresh };
}

export function LayersTab() {
  const { project, toast, set } = useEditor();
  const { orthos, refresh } = useOrthos();
  const fileRef = useRef<HTMLInputElement>(null);
  const worldRef = useRef<HTMLInputElement>(null);
  const [meta, setMeta] = useState({ name: "", source: "", captured_on: "", src_crs: "", res: "" });
  const [job, setJob] = useState<Job | null>(null);
  const [resumable, setResumable] = useState<string | null>(null);
  const [gcpFor, setGcpFor] = useState<OrthophotoOut | null>(null);
  const jobRef = useRef<Job | null>(null);
  jobRef.current = job;
  useEffect(() => () => jobRef.current?.ctrl.abort(), []);  // al salir de la pestaña la subida queda en pausa
  if (!project) return null;
  const busy = job?.state === "subiendo";

  const onPick = () => {
    const f = fileRef.current?.files?.[0];
    setResumable(f && rememberedUpload(project.id, f) ? f.name : null);
  };
  const upload = async (file = fileRef.current?.files?.[0]) => {
    if (!file) return toast("Elija un GeoTIFF, JPG o PNG.", "error");
    const ctrl = new AbortController();
    const start: Job = { file, ctrl, state: "subiendo", progress: { sent: 0, total: file.size, speed: 0, eta: null, retrying: 0 } };
    setJob(start);
    try {
      const wf = worldRef.current?.files?.[0];
      const world = wf ? await wf.text() : undefined;
      const st = await uploadInParts(project.id, file, {
        name: meta.name || undefined, source: meta.source || undefined, captured_on: meta.captured_on || undefined,
        src_crs: meta.src_crs || `EPSG:${project.length_srid}`, world, target_res_cm: meta.res ? Number(meta.res) : null,
      }, (progress) => setJob((j) => (j && j.ctrl === ctrl ? { ...j, progress } : j)), ctrl.signal);
      setJob(null);
      setResumable(null);
      if (fileRef.current) fileRef.current.value = "";
      if (worldRef.current) worldRef.current.value = "";
      await refresh();
      const o = st.ortho;
      if (o.status === "error") toast(o.error ?? "La ortofoto no se pudo procesar.", "error");
      else if (o.georef === "gcp") { toast("Imagen subida: ubíquela en el mapa con el asistente."); setGcpFor(o); }
      else toast("Ortofoto subida: se está procesando.");
    } catch (e) {
      const err = e as UploadError;
      setJob((j) => (j && j.ctrl === ctrl ? { ...j, state: err.status === -1 ? "pausada" : "error", message: errorText(e) } : j));
      void refresh();
    }
  };
  const cancel = async () => {
    if (!job) return;
    job.ctrl.abort();
    const id = rememberedUpload(project.id, job.file);
    setJob(null);
    if (id && window.confirm("¿Descartar la subida? Se elimina lo ya recibido.")) {
      try { await api.deleteOrtho(project.id, id); } catch { /* ya no existe */ }
      try { localStorage.removeItem(`trazo.upload.${project.id}.${job.file.name}.${job.file.size}.${job.file.lastModified}`); } catch { /* sin almacenamiento */ }
    }
    void refresh();
  };
  const patch = async (o: OrthophotoOut, body: Parameters<typeof api.updateOrtho>[2]) => {
    set({ orthos: orthos.map((x) => (x.id === o.id ? { ...x, ...body } as OrthophotoOut : x)) });
    try { await api.updateOrtho(project.id, o.id, body); } catch (e) { toast(errorText(e), "error"); void refresh(); }
  };
  const remove = async (o: OrthophotoOut) => {
    if (!window.confirm(`¿Eliminar la ortofoto «${o.name}» y sus archivos?`)) return;
    try { await api.deleteOrtho(project.id, o.id); await refresh(); } catch (e) { toast(errorText(e), "error"); }
  };
  const zoomTo = (o: OrthophotoOut) => {
    if (!o.bounds) return;
    const [w, s, e, n] = o.bounds;
    set({ cameraRequest: { points: [[w, s], [e, n]] as LngLat[], nonce: Date.now() } });
  };

  return (
    <div className="layers-tab">
      <div className="toolbar wrap">
        <label className="field inline"><span>Imagen</span><input ref={fileRef} type="file" accept=".tif,.tiff,.jpg,.jpeg,.png" onChange={onPick} /></label>
        <label className="field inline"><span>World (opcional)</span><input ref={worldRef} type="file" accept=".jgw,.pgw,.wld,.tfw" /></label>
        <input placeholder="Nombre" value={meta.name} onChange={(e) => setMeta({ ...meta, name: e.target.value })} />
        <input placeholder="Fuente (vuelo, proveedor)" value={meta.source} onChange={(e) => setMeta({ ...meta, source: e.target.value })} />
        <input type="date" value={meta.captured_on} onChange={(e) => setMeta({ ...meta, captured_on: e.target.value })} aria-label="Fecha" />
        <input placeholder={`EPSG:${project.length_srid}`} value={meta.src_crs} onChange={(e) => setMeta({ ...meta, src_crs: e.target.value })} aria-label="Sistema del archivo world" style={{ width: 110 }} />
        <select value={meta.res} onChange={(e) => setMeta({ ...meta, res: e.target.value })} aria-label="Resolución">
          {RESOLUTIONS.map(([v, t]) => <option key={v} value={v}>{t}</option>)}</select>
        <button className="small primary" disabled={busy} onClick={() => void upload()}>{busy ? "Subiendo…" : resumable ? "Retomar subida" : "Subir"}</button>
        <Help text="GeoTIFF georreferenciado; JPG/PNG con archivo world (.jgw/.pgw/.wld, en el sistema indicado, por defecto el UTM del proyecto); o JPG/PNG sin referencia para ubicar con el asistente de puntos de control. Se sube por partes (si se corta, vuelva a elegir el mismo archivo para retomar), se convierte a Cloud Optimized GeoTIFF y se muestra bajo la red, también sin Google Maps. «Reducir resolución» aliviana fotos muy pesadas." />
      </div>
      {resumable && !job && <p className="small pad-x warn-text">Hay una subida interrumpida de «{resumable}»: «Retomar subida» sigue desde la última parte recibida.</p>}
      {job && (
        <div className="upload-job" role="status" aria-label="Progreso de la subida">
          <div className="upload-head">
            <b>{job.file.name}</b>
            <span className="muted small">{fmtBytes(job.progress.sent)} de {fmtBytes(job.progress.total)}</span>
            {job.state === "subiendo" && <span className="muted small">· {fmtBytes(job.progress.speed)}/s · quedan {fmtEta(job.progress.eta)}</span>}
            {job.progress.retrying > 0 && job.state === "subiendo" && <span className="warn-text small">· conexión inestable, reintentando ({job.progress.retrying})…</span>}
            <span className="tabs-spacer" />
            {job.state === "subiendo" && <button className="small" onClick={() => job.ctrl.abort()}>Pausar</button>}
            {job.state !== "subiendo" && <button className="small primary" onClick={() => void upload(job.file)}>Reanudar</button>}
            <button className="small ghost" onClick={() => void cancel()}>Cancelar</button>
          </div>
          <div className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round((job.progress.sent / job.progress.total) * 100)}>
            <i style={{ width: `${(job.progress.sent / job.progress.total) * 100}%` }} /><span>{Math.floor((job.progress.sent / job.progress.total) * 100)} %</span>
          </div>
          {job.state === "pausada" && <p className="small muted">Subida en pausa: «Reanudar» sigue desde la última parte recibida.</p>}
          {job.state === "error" && <p className="small bad-text">{job.message}</p>}
        </div>
      )}
      {orthos.length === 0 ? <p className="muted pad">Sin ortofotos.</p> : (
        <table className="tbl">
          <thead><tr><th></th><th>Nombre</th><th>Fecha</th><th>Fuente</th><th>Georreferencia</th><th>Estado</th><th>Opacidad</th><th></th></tr></thead>
          <tbody>
            {orthos.map((o) => (
              <tr key={o.id}>
                <td><input type="checkbox" checked={o.visible} disabled={o.status !== "ready"} onChange={(e) => void patch(o, { visible: e.target.checked })} aria-label="Mostrar" /></td>
                <td>{o.name}</td><td>{o.captured_on ?? "—"}</td><td>{o.source ?? "—"}</td>
                <td>{{ geotiff: "GeoTIFF", worldfile: "archivo world", gcp: "puntos de control" }[o.georef]}{o.residual_m != null ? ` (RMS ${fmt(o.residual_m, 2)} m)` : ""}</td>
                <td className={o.status === "error" ? "bad" : ""} title={o.error ?? ""}>
                  {o.status === "uploading" ? `${STATUS.uploading} ${Math.floor(((o.upload_offset ?? 0) / o.size_bytes) * 100)} %${job?.state === "subiendo" ? "" : " (interrumpida: elija el mismo archivo para retomar)"}`
                    : o.status === "processing" || o.status === "pending" ? <span className="busy-text">{STATUS[o.status]}…</span>
                      : <>{STATUS[o.status]}{o.status === "error" && o.error ? `: ${o.error}` : ""}</>}
                  {o.target_res_m ? <span className="muted small"> · {fmt(o.target_res_m * 100, 0)} cm/píxel</span> : null}
                  <span className="muted small"> · {fmtBytes(o.size_bytes)}</span>
                </td>
                <td><input type="range" min={0} max={1} step={0.05} value={o.opacity} onChange={(e) => void patch(o, { opacity: Number(e.target.value) })} aria-label="Opacidad" /></td>
                <td className="right">
                  {o.bounds && <button className="small ghost" onClick={() => zoomTo(o)}>Ver</button>}
                  {o.georef !== "geotiff" && o.status !== "uploading" && o.status !== "processing" && <button className="small ghost" onClick={() => setGcpFor(o)}>{o.status === "uploaded" ? "Ubicar en el mapa" : "Ajustar ubicación"}</button>}
                  <button className="small ghost" onClick={() => void remove(o)}>Eliminar</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {gcpFor && <GeorefWizard ortho={gcpFor} onClose={() => { setGcpFor(null); void refresh(); }} />}
    </div>
  );
}
