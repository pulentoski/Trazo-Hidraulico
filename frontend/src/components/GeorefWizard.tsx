// Asistente de georreferenciación de una foto sin coordenadas: la foto a la izquierda y el mapa a la derecha.
// Cada punto de control se marca con un clic en la foto y otro en el mapa (o escribiendo sus coordenadas).
// Con 2 puntos: escala, giro y posición; con 3 o más: ajuste afín con el error de cada punto en metros.
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api/client";
import type { Gcp, GcpFit, OrthophotoOut } from "../api/types";
import { fmt, parseNum } from "../lib/format";
import type { LngLat } from "../lib/geo";
import { errorText } from "../state/projects";
import { useEditor } from "../state/store";
import { Icon } from "./Icons";

type CoordMode = "latlon" | "utm";
interface Pt { px: number; py: number; lon: number | null; lat: number | null; e?: number | null; n?: number | null; zone?: number | null; south?: boolean }
type Await = { kind: "map" | "photo"; index: number } | null;

/** Borde derecho del asistente: el mapa se encuadra en la parte que queda visible. */
const coverLeft = () => document.querySelector(".georef-wizard")?.getBoundingClientRect().right ?? 0;

const complete = (p: Pt) => (p.lon !== null && p.lat !== null) || (p.e != null && p.n != null && p.zone != null);

function toGcp(p: Pt): Gcp {
  return p.lon !== null && p.lat !== null
    ? { px: p.px, py: p.py, lon: p.lon, lat: p.lat, south: true }
    : { px: p.px, py: p.py, e: p.e!, n: p.n!, zone: p.zone!, south: p.south ?? true };
}

export function GeorefWizard({ ortho, onClose }: { ortho: OrthophotoOut; onClose: () => void }) {
  const { project, set, toast } = useEditor();
  const srid = project?.length_srid ?? 32719;
  const defZone = srid > 32700 ? srid - 32700 : srid > 32600 ? srid - 32600 : 19;
  const [pts, setPts] = useState<Pt[]>(() => (ortho.gcps ?? []).map((g) => ({
    px: g.px, py: g.py, lon: g.lon ?? null, lat: g.lat ?? null, e: g.e, n: g.n, zone: g.zone, south: g.south })));
  const [fit, setFit] = useState<GcpFit | null>(null);
  const [fitError, setFitError] = useState<string | null>(null);
  const [awaiting, setAwaiting] = useState<Await>(null);
  const [zoom, setZoom] = useState(1);
  const [natural, setNatural] = useState<{ w: number; h: number } | null>(ortho.width && ortho.height ? { w: ortho.width, h: ortho.height } : null);
  const [preview, setPreview] = useState(true);
  const [opacity, setOpacity] = useState(0.7);
  const [busy, setBusy] = useState(false);
  const [guide, setGuide] = useState(!(ortho.gcps?.length));
  const [typed, setTyped] = useState<{ mode: CoordMode; a: string; b: string; zone: string; south: boolean }>({ mode: "latlon", a: "", b: "", zone: String(defZone), south: srid > 32700 });
  const imgRef = useRef<HTMLImageElement>(null);
  const url = project ? api.orthoOriginalUrl(project.id, ortho.id) : "";
  const ready = pts.filter(complete);
  const key = JSON.stringify(ready.map(toGcp));

  // Ajuste en vivo (sin guardar) cada vez que cambian los puntos completos.
  useEffect(() => {
    if (!project || ready.length < 2) { setFit(null); setFitError(null); return; }
    let alive = true;
    api.gcps(project.id, ortho.id, ready.map(toGcp), false)
      .then((f) => { if (alive) { setFit(f); setFitError(null); } })
      .catch((e) => { if (alive) { setFit(null); setFitError(errorText(e)); } });
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  // Al obtener la primera ubicación, el mapa se centra en la vista previa.
  const centered = useRef(false);
  useEffect(() => {
    if (fit?.corners && !centered.current) {
      centered.current = true;
      set({ cameraRequest: { points: fit.corners as LngLat[], nonce: Date.now(), coverLeft: coverLeft() } });
    }
  }, [fit, set]);

  // Vista previa sobre el mapa.
  useEffect(() => {
    const corners = fit?.corners;
    if (preview && corners && natural) set({ gcpPreview: { url, width: natural.w, height: natural.h, corners: corners as LngLat[], opacity } });
    else set({ gcpPreview: null });
  }, [fit, preview, opacity, natural, url, set]);
  useEffect(() => () => useEditor.getState().set({ gcpPreview: null, mapPick: null }), []);

  // Esperando un clic en el mapa para el punto activo.
  useEffect(() => {
    if (awaiting?.kind !== "map") { set({ mapPick: null }); return; }
    const i = awaiting.index;
    set({ mapPick: (pos) => {
      setPts((cur) => cur.map((p, k) => (k === i ? { ...p, lon: pos[0], lat: pos[1], e: null, n: null, zone: null } : p)));
      setAwaiting(null);
    } });
  }, [awaiting, set]);

  // Encuadre inicial: los puntos guardados, o la red.
  useEffect(() => {
    const done = (ortho.gcps ?? []).filter((g) => g.lon != null && g.lat != null).map((g) => [g.lon!, g.lat!] as LngLat);
    if (done.length) set({ cameraRequest: { points: done, nonce: Date.now(), coverLeft: coverLeft() } });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Con 2 puntos (o 3 en el ajuste afín) la transformación pasa exacta por ellos: no hay error que comparar.
  const exact = !fit || Math.max(0, ...fit.residuals_m) < 0.01;
  const worst = exact ? null : fit?.worst ?? null;
  const resIndex = useMemo(() => { const m = new Map<Pt, number>(); ready.forEach((p, i) => m.set(p, i)); return m; }, [ready]);
  if (!project) return null;

  const onPhoto = (ev: React.MouseEvent<HTMLImageElement>) => {
    const img = imgRef.current!;
    const r = img.getBoundingClientRect();
    const px = Math.round(((ev.clientX - r.left) * img.naturalWidth / r.width) * 10) / 10;
    const py = Math.round(((ev.clientY - r.top) * img.naturalHeight / r.height) * 10) / 10;
    if (awaiting?.kind === "photo") {
      const i = awaiting.index;
      setPts(pts.map((p, k) => (k === i ? { ...p, px, py } : p)));
      setAwaiting(null);
      return;
    }
    setPts([...pts, { px, py, lon: null, lat: null }]);
    setAwaiting({ kind: "map", index: pts.length });
    setTyped({ ...typed, a: "", b: "" });
  };
  const useTyped = () => {
    if (awaiting === null) return;
    const a = parseNum(typed.a);
    const b = parseNum(typed.b);
    const i = awaiting.index;
    if (a === null || b === null) return toast("Escriba las dos coordenadas.", "error");
    if (typed.mode === "latlon") {
      if (Math.abs(a) > 90 || Math.abs(b) > 180) return toast("Latitud entre −90 y 90, longitud entre −180 y 180.", "error");
      setPts(pts.map((p, k) => (k === i ? { ...p, lat: a, lon: b, e: null, n: null, zone: null } : p)));
    } else {
      const z = Number(typed.zone);
      if (!(z >= 1 && z <= 60)) return toast("El huso UTM va de 1 a 60.", "error");
      setPts(pts.map((p, k) => (k === i ? { ...p, lat: null, lon: null, e: a, n: b, zone: z, south: typed.south } : p)));
    }
    setAwaiting(null);
  };
  const remove = (i: number) => { setPts(pts.filter((_, k) => k !== i)); setAwaiting(null); };
  const save = async () => {
    setBusy(true);
    try {
      const f = await api.gcps(project.id, ortho.id, ready.map(toGcp), false, true);
      toast(`Puntos guardados (${ready.length}). Error medio ${fmt(f.rms_m, 2)} m: puede seguir ajustando después.`);
    } catch (e) { toast(errorText(e), "error"); } finally { setBusy(false); }
  };
  const apply = async () => {
    setBusy(true);
    try {
      const f = await api.gcps(project.id, ortho.id, ready.map(toGcp), true);
      toast(`Ubicación aplicada (error medio ${fmt(f.rms_m, 2)} m): la imagen se está procesando.`);
      onClose();
    } catch (e) { toast(errorText(e), "error"); } finally { setBusy(false); }
  };
  const step = ready.length < 2 ? 2 : 3;
  const pending = awaiting?.kind === "map" ? awaiting.index : null;

  return (
    <div className="georef-wizard" role="dialog" aria-label="Asistente de ubicación de la foto">
      <header>
        <h3>Ubicar la foto en el mapa · {ortho.name}</h3>
        <ol className="steps">
          <li className={guide ? "on" : "done"}>1. Guía</li>
          <li className={!guide && step === 2 ? "on" : step === 3 ? "done" : ""}>2. Marcar puntos</li>
          <li className={!guide && step === 3 ? "on" : ""}>3. Revisar y aplicar</li>
        </ol>
        <button className="ghost" onClick={onClose} aria-label="Cerrar asistente"><Icon.close /></button>
      </header>
      {guide ? (
        <div className="wizard-guide">
          <p><b>Cómo funciona:</b> va a marcar el mismo lugar dos veces: primero en la foto (izquierda) y luego en el mapa (derecha).</p>
          <ul>
            <li>Elija puntos fáciles de reconocer y separados entre sí: esquinas de casas, postes, el estanque, cruces de calles.</li>
            <li>Marque al menos <b>2 puntos</b>. Con <b>3 o más</b> el sistema le dice cuánto se equivoca cada punto, en metros.</li>
            <li>Si no ve el lugar en el mapa, puede escribir sus coordenadas (latitud y longitud, o UTM).</li>
            <li>Antes de aplicar verá la foto encima del mapa para comprobar que calza.</li>
          </ul>
          <button className="primary" onClick={() => setGuide(false)}>Comenzar</button>
        </div>
      ) : (<>
        <div className="wizard-hint" aria-live="polite">
          {awaiting?.kind === "photo" ? <>Haga clic en la foto donde está el punto {awaiting.index + 1}.</>
            : pending !== null ? <>Punto {pending + 1}: ahora haga clic en <b>el mismo lugar en el mapa</b> (a la derecha), o escriba sus coordenadas abajo.</>
              : ready.length < 2 ? <>Haga clic en un lugar reconocible de la foto ({2 - ready.length} {2 - ready.length === 1 ? "punto más" : "puntos"} como mínimo).</>
                : <>Puede agregar más puntos con un clic en la foto, o revisar y aplicar.</>}
        </div>
        <div className="wizard-photo">
          <div className="photo-tools">
            <button className="small" onClick={() => setZoom(Math.max(0.5, zoom / 1.5))} aria-label="Alejar la foto">−</button>
            <button className="small" onClick={() => setZoom(1)}>Ajustar</button>
            <button className="small" onClick={() => setZoom(Math.min(8, zoom * 1.5))} aria-label="Acercar la foto">+</button>
            <button className="small ghost" onClick={() => setGuide(true)}>Ver guía</button>
          </div>
          <div className="photo-scroll">
            <div className="photo-box" style={{ width: `${zoom * 100}%` }}>
              <img ref={imgRef} src={url} alt="Foto a ubicar" onClick={onPhoto} draggable={false}
                onLoad={(e) => setNatural({ w: e.currentTarget.naturalWidth, h: e.currentTarget.naturalHeight })} />
              {natural && pts.map((p, i) => (
                <span key={i} className={`gcp-mark ${pending === i ? "active" : ""} ${worst !== null && resIndex.get(p) === worst ? "worst" : ""}`}
                  style={{ left: `${(p.px / natural.w) * 100}%`, top: `${(p.py / natural.h) * 100}%` }}>{i + 1}</span>
              ))}
            </div>
          </div>
        </div>
        {pending !== null && (
          <div className="typed-coords">
            <select value={typed.mode} onChange={(e) => setTyped({ ...typed, mode: e.target.value as CoordMode })} aria-label="Tipo de coordenadas">
              <option value="latlon">Latitud / longitud</option><option value="utm">UTM Este / Norte</option></select>
            <input value={typed.a} onChange={(e) => setTyped({ ...typed, a: e.target.value })} placeholder={typed.mode === "latlon" ? "Latitud (ej. -29,9402)" : "Este (m)"} aria-label={typed.mode === "latlon" ? "Latitud" : "Este"} />
            <input value={typed.b} onChange={(e) => setTyped({ ...typed, b: e.target.value })} placeholder={typed.mode === "latlon" ? "Longitud (ej. -71,1418)" : "Norte (m)"} aria-label={typed.mode === "latlon" ? "Longitud" : "Norte"} />
            {typed.mode === "utm" && (<>
              <input className="zone" value={typed.zone} onChange={(e) => setTyped({ ...typed, zone: e.target.value })} aria-label="Huso" title="Huso UTM" />
              <select value={typed.south ? "S" : "N"} onChange={(e) => setTyped({ ...typed, south: e.target.value === "S" })} aria-label="Hemisferio"><option value="S">Sur</option><option value="N">Norte</option></select>
            </>)}
            <button className="small primary" onClick={useTyped}>Usar coordenadas</button>
          </div>
        )}
        <div className="gcp-table"><table className="tbl compact">
          <thead><tr><th>#</th><th>En la foto</th><th>En el terreno</th><th className="num">Error (m)</th><th /></tr></thead>
          <tbody>
            {pts.map((p, i) => {
              const k = resIndex.get(p);
              const res = fit && k !== undefined ? fit.residuals_m[k] : null;
              const isWorst = worst !== null && k === worst;
              return (
                <tr key={i} className={`${pending === i ? "current" : ""} ${isWorst ? "worst-row" : ""}`}>
                  <td>{i + 1}</td>
                  <td className="mono small">{fmt(p.px, 0)}, {fmt(p.py, 0)}</td>
                  <td className="small">{p.lat !== null ? `${fmt(p.lat, 6)}, ${fmt(p.lon!, 6)}`
                    : p.e != null ? `E ${fmt(p.e, 1)} · N ${fmt(p.n!, 1)} · huso ${p.zone}${p.south === false ? "N" : "S"}`
                      : <span className="warn-text">falta ubicarlo en el mapa</span>}</td>
                  <td className={`num ${isWorst ? "bad" : ""}`}>{res !== null ? fmt(res, 2) : "—"}{isWorst && <span className="badge warn">mayor error</span>}</td>
                  <td className="right">
                    <button className="small ghost" onClick={() => setAwaiting({ kind: "photo", index: i })} title="Volver a marcar en la foto">Foto</button>
                    <button className="small ghost" onClick={() => { setAwaiting({ kind: "map", index: i }); setTyped({ ...typed, a: "", b: "" }); }} title="Volver a marcar en el mapa o escribir coordenadas">Mapa</button>
                    <button className="small ghost" onClick={() => remove(i)} aria-label={`Borrar punto ${i + 1}`}><Icon.close /></button>
                  </td>
                </tr>
              );
            })}
            {!pts.length && <tr><td colSpan={5} className="muted">Todavía no hay puntos.</td></tr>}
          </tbody>
        </table></div>
        {fitError && <p className="bad-text small">{fitError}</p>}
        <footer className="wizard-foot">
          <div className="fit-summary">
            {fit ? <><b>{fit.method === "afín" ? "Ajuste con 3 o más puntos" : "Ajuste con 2 puntos"}</b> · error medio (RMS) <b>{fmt(fit.rms_m, 2)} m</b>
              {exact && <span className="muted"> · {ready.length < 4 ? `con ${ready.length} puntos la ubicación pasa exacta por ellos: agregue otro punto para medir el error` : "todos los puntos calzan"}</span>}</>
              : <span className="muted">Faltan puntos para calcular la ubicación.</span>}
          </div>
          <label className="check small"><input type="checkbox" checked={preview} onChange={(e) => setPreview(e.target.checked)} />Vista previa en el mapa</label>
          <label className="inline small">Opacidad<input type="range" min={0.1} max={1} step={0.05} value={opacity} onChange={(e) => setOpacity(Number(e.target.value))} aria-label="Opacidad de la vista previa" /></label>
          <span className="tabs-spacer" />
          <button disabled={!fit || busy} onClick={() => void save()}>Guardar puntos</button>
          <button className="primary" disabled={!fit || busy} onClick={() => void apply()}>{busy ? "Aplicando…" : "Aplicar"}</button>
        </footer>
      </>)}
    </div>
  );
}
