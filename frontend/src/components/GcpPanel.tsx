// Ajuste de una imagen sin referencia con puntos de control: clic en la imagen y luego en el mapa.
import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { Gcp, GcpFit, OrthophotoOut } from "../api/types";
import { fmt } from "../lib/format";
import { errorText } from "../state/projects";
import { useEditor } from "../state/store";

interface Pt { px: number; py: number; lon: number | null; lat: number | null }

export function GcpPanel({ ortho, onClose }: { ortho: OrthophotoOut; onClose: () => void }) {
  const { project, set, toast } = useEditor();
  const [pts, setPts] = useState<Pt[]>(() => ((ortho as unknown as { gcps?: Gcp[] }).gcps ?? []).map((g) => ({ ...g })));
  const [fit, setFit] = useState<GcpFit | null>(null);
  const [busy, setBusy] = useState(false);
  const imgRef = useRef<HTMLImageElement>(null);
  const complete = pts.filter((p): p is Gcp => p.lon !== null && p.lat !== null);

  useEffect(() => {
    if (!project || complete.length < 2) { setFit(null); return; }
    let alive = true;
    api.gcps(project.id, ortho.id, complete, false).then((f) => alive && setFit(f)).catch(() => alive && setFit(null));
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(complete)]);
  useEffect(() => () => useEditor.getState().set({ mapPick: null }), []);
  if (!project) return null;

  const pickOnMap = (i: number) => {
    set({ mapPick: (pos) => setPts((cur) => cur.map((p, k) => (k === i ? { ...p, lon: pos[0], lat: pos[1] } : p))) });
    toast("Haga clic en el mapa en el punto correspondiente.");
  };
  const onImage = (e: React.MouseEvent<HTMLImageElement>) => {
    const img = imgRef.current!;
    const r = img.getBoundingClientRect();
    const px = ((e.clientX - r.left) * img.naturalWidth) / r.width;
    const py = ((e.clientY - r.top) * img.naturalHeight) / r.height;
    const i = pts.length;
    setPts([...pts, { px: Math.round(px * 10) / 10, py: Math.round(py * 10) / 10, lon: null, lat: null }]);
    pickOnMap(i);
  };
  const apply = async () => {
    setBusy(true);
    try {
      const f = await api.gcps(project.id, ortho.id, complete, true);
      toast(`Ajuste ${f.method} aplicado (RMS ${fmt(f.rms_m, 2)} m): procesando la ortofoto.`);
      onClose();
    } catch (e) { toast(errorText(e), "error"); } finally { setBusy(false); }
  };

  return (
    <div className="float-panel gcp-panel" role="dialog" aria-label="Puntos de control">
      <header><h3>Puntos de control · {ortho.name}</h3><button className="ghost" onClick={onClose} aria-label="Cerrar">✕</button></header>
      <p className="muted small">Clic en un punto reconocible de la imagen y luego en el mismo punto del mapa. Mínimo 2 (similitud); con 3 o más, ajuste afín con error residual.</p>
      <div className="gcp-img">
        <img ref={imgRef} src={api.orthoOriginalUrl(project.id, ortho.id)} alt="Imagen a georreferenciar" onClick={onImage} />
        {pts.map((p, i) => imgRef.current && (
          <span key={i} className="gcp-mark" style={{ left: `${(p.px / imgRef.current.naturalWidth) * 100}%`, top: `${(p.py / imgRef.current.naturalHeight) * 100}%` }}>{i + 1}</span>
        ))}
      </div>
      <table className="tbl compact">
        <thead><tr><th>#</th><th className="num">Columna</th><th className="num">Fila</th><th>Mapa</th><th className="num">Residuo (m)</th><th></th></tr></thead>
        <tbody>
          {pts.map((p, i) => {
            const k = complete.indexOf(p as Gcp);
            return (
              <tr key={i}>
                <td>{i + 1}</td><td className="num">{fmt(p.px, 1)}</td><td className="num">{fmt(p.py, 1)}</td>
                <td>{p.lat !== null ? `${fmt(p.lat, 6)}, ${fmt(p.lon!, 6)}` : <button className="small" onClick={() => pickOnMap(i)}>Marcar en el mapa</button>}</td>
                <td className="num">{fit && k >= 0 ? fmt(fit.residuals_m[k], 2) : "—"}</td>
                <td><button className="small ghost" onClick={() => setPts(pts.filter((_, j) => j !== i))} aria-label="Quitar">✕</button></td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <div className="modal-actions">
        <span className="muted">{fit ? `Ajuste ${fit.method} · error residual RMS ${fmt(fit.rms_m, 2)} m` : "Faltan puntos"}</span>
        <button className="primary" disabled={!fit || busy} onClick={() => void apply()}>{busy ? "Aplicando…" : "Aplicar y procesar"}</button>
      </div>
    </div>
  );
}
