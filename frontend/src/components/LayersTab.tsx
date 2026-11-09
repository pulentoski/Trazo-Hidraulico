// Pestaña «Capas»: ortofotos del proyecto (subir, georreferenciar, opacidad, encender/apagar, eliminar).
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { OrthophotoOut } from "../api/types";
import { fmt } from "../lib/format";
import type { LngLat } from "../lib/geo";
import { errorText } from "../state/projects";
import { useEditor } from "../state/store";
import { Help } from "./Fields";
import { GcpPanel } from "./GcpPanel";

const STATUS: Record<OrthophotoOut["status"], string> = {
  uploaded: "sin georreferencia", pending: "en cola", processing: "procesando", ready: "lista", error: "error",
};

export function useOrthos() {
  const project = useEditor((s) => s.project);
  const set = useEditor((s) => s.set);
  const orthos = useEditor((s) => s.orthos);
  const refresh = useCallback(async () => {
    if (!project) return;
    try { set({ orthos: await api.orthos(project.id) }); } catch { /* sin capas */ }
  }, [project, set]);
  useEffect(() => { void refresh(); }, [refresh]);
  const busy = orthos.some((o) => o.status === "pending" || o.status === "processing");
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
  const [meta, setMeta] = useState({ name: "", source: "", captured_on: "", src_crs: "" });
  const [busy, setBusy] = useState(false);
  const [gcpFor, setGcpFor] = useState<OrthophotoOut | null>(null);
  if (!project) return null;

  const upload = async () => {
    const file = fileRef.current?.files?.[0];
    if (!file) return toast("Elija un GeoTIFF, JPG o PNG.", "error");
    setBusy(true);
    try {
      const o = await api.uploadOrtho(project.id, file, worldRef.current?.files?.[0] ?? null,
        { ...meta, src_crs: meta.src_crs || `EPSG:${project.length_srid}` });
      toast(o.georef === "gcp" ? "Imagen subida: georreferénciela con puntos de control." : "Ortofoto subida: se está procesando.");
      if (fileRef.current) fileRef.current.value = "";
      if (worldRef.current) worldRef.current.value = "";
      await refresh();
      if (o.georef === "gcp") setGcpFor(o);
    } catch (e) { toast(errorText(e), "error"); } finally { setBusy(false); }
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
        <label className="field inline"><span>Imagen</span><input ref={fileRef} type="file" accept=".tif,.tiff,.jpg,.jpeg,.png" /></label>
        <label className="field inline"><span>World (opcional)</span><input ref={worldRef} type="file" accept=".jgw,.pgw,.wld,.tfw" /></label>
        <input placeholder="Nombre" value={meta.name} onChange={(e) => setMeta({ ...meta, name: e.target.value })} />
        <input placeholder="Fuente (vuelo, proveedor)" value={meta.source} onChange={(e) => setMeta({ ...meta, source: e.target.value })} />
        <input type="date" value={meta.captured_on} onChange={(e) => setMeta({ ...meta, captured_on: e.target.value })} aria-label="Fecha" />
        <input placeholder={`EPSG:${project.length_srid}`} value={meta.src_crs} onChange={(e) => setMeta({ ...meta, src_crs: e.target.value })} aria-label="Sistema del archivo world" style={{ width: 110 }} />
        <button className="small primary" disabled={busy} onClick={() => void upload()}>{busy ? "Subiendo…" : "Subir"}</button>
        <Help text="GeoTIFF georreferenciado; JPG/PNG con archivo world (.jgw/.pgw/.wld, en el sistema indicado, por defecto el UTM del proyecto); o JPG/PNG sin referencia para ajustar con puntos de control. Se convierte a Cloud Optimized GeoTIFF y se muestra bajo la red, también sin Google Maps." />
      </div>
      {orthos.length === 0 ? <p className="muted pad">Sin ortofotos.</p> : (
        <table className="tbl">
          <thead><tr><th></th><th>Nombre</th><th>Fecha</th><th>Fuente</th><th>Georreferencia</th><th>Estado</th><th>Opacidad</th><th></th></tr></thead>
          <tbody>
            {orthos.map((o) => (
              <tr key={o.id}>
                <td><input type="checkbox" checked={o.visible} disabled={o.status !== "ready"} onChange={(e) => void patch(o, { visible: e.target.checked })} aria-label="Mostrar" /></td>
                <td>{o.name}</td><td>{o.captured_on ?? "—"}</td><td>{o.source ?? "—"}</td>
                <td>{{ geotiff: "GeoTIFF", worldfile: "archivo world", gcp: "puntos de control" }[o.georef]}{o.residual_m != null ? ` (RMS ${fmt(o.residual_m, 2)} m)` : ""}</td>
                <td className={o.status === "error" ? "bad" : ""} title={o.error ?? ""}>{STATUS[o.status]}{o.status === "error" && o.error ? `: ${o.error}` : ""}</td>
                <td><input type="range" min={0} max={1} step={0.05} value={o.opacity} onChange={(e) => void patch(o, { opacity: Number(e.target.value) })} aria-label="Opacidad" /></td>
                <td className="right">
                  {o.bounds && <button className="small ghost" onClick={() => zoomTo(o)}>Ver</button>}
                  {o.georef !== "geotiff" && <button className="small ghost" onClick={() => setGcpFor(o)}>Puntos de control</button>}
                  <button className="small ghost" onClick={() => void remove(o)}>Eliminar</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {gcpFor && <GcpPanel ortho={gcpFor} onClose={() => { setGcpFor(null); void refresh(); }} />}
    </div>
  );
}
