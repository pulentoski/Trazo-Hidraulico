// Coordenadas en el editor: barra con la coordenada del cursor (lat/lon y UTM, con copiar), creación de elementos por
// coordenadas ingresadas y edición de las coordenadas de un elemento (lat/lon o UTM). Igual con Google, OSM o lienzo.
import { useEffect, useRef, useState } from "react";
import type { Camera, LngLat, Size } from "../lib/geo";
import { unproject } from "../lib/geo";
import type { Utm } from "../lib/coords";
import { DEFAULT_SOUTH, DEFAULT_ZONE, formatLatLon, formatUtm, fromUtm, parseCoordinates, toDms, toUtm } from "../lib/coords";
import { linkCoords, nearestJunction, nearestPipe, pointAlong, projectOnLink } from "../lib/network";
import type { Network } from "../lib/network";
import { parseNum } from "../lib/format";
import { useEditor } from "../state/store";
import { Modal } from "./Dialogs";
import { Section } from "./Section";

/** Herramientas que crean un elemento en un punto (admiten «Ingresar coordenadas»). */
export const POINT_TOOLS = new Set(["junction", "tank", "reservoir", "client", "shutoff", "hydrant", "well"]);

function zoneLabel(u: Utm): string {
  return `${u.zone}${u.south ? "S" : "N"}`;
}

/** Posición de un elemento puntual (nudo, cliente, grifo, pozo) o de una llave sobre su tubería. */
export function positionOf(net: Network, uid: string): LngLat | null {
  const p = net.nodes[uid]?.pos ?? net.clients[uid]?.pos ?? net.hydrants[uid]?.pos ?? net.wells[uid]?.pos;
  if (p) return p;
  const sh = net.shutoffs[uid];
  if (sh && net.links[sh.link]) return pointAlong(linkCoords(net, net.links[sh.link]), sh.position);
  return null;
}

/** Mueve un elemento a una coordenada: los tramos siguen a sus nudos (los largos se recalculan al guardar), el
 *  cliente se vuelve a proyectar sobre la tubería más cercana y la llave se ubica en el punto más cercano de su tubería. */
export function moveElement(net: Network, uid: string, pos: LngLat): Network {
  if (net.nodes[uid]) return { ...net, nodes: { ...net.nodes, [uid]: { ...net.nodes[uid], pos } } };
  if (net.hydrants[uid]) return { ...net, hydrants: { ...net.hydrants, [uid]: { ...net.hydrants[uid], pos } } };
  if (net.wells[uid]) return { ...net, wells: { ...net.wells, [uid]: { ...net.wells[uid], pos } } };
  const c = net.clients[uid];
  if (c) {
    const pr = nearestPipe(net, pos);
    let node = c.node;
    if (pr && c.props.connection_mode === "nearest") node = nearestJunction(net, pr)?.node ?? node;
    return { ...net, clients: { ...net.clients, [uid]: { ...c, pos, node, ...(pr ? { link: pr.link, connection: pr.point } : {}) } } };
  }
  const sh = net.shutoffs[uid];
  if (sh) {
    const pr = projectOnLink(net, sh.link, pos);
    return { ...net, shutoffs: { ...net.shutoffs, [uid]: { ...sh, position: Math.round(pr.fraction * 1000) / 1000 } } };
  }
  return net;
}

/** Vista previa de una coordenada en los tres formatos. */
function Preview({ pos }: { pos: LngLat }) {
  const u = toUtm(pos, DEFAULT_ZONE, DEFAULT_SOUTH);
  return (
    <dl className="kv compact coord-preview">
      <dt>Lat/lon</dt><dd className="mono">{formatLatLon(pos)}</dd>
      <dt>GMS</dt><dd className="mono">{toDms(pos)}</dd>
      <dt>UTM</dt><dd className="mono">{formatUtm(u)}</dd>
    </dl>
  );
}

// ── Crear por coordenadas ──

export function CoordInputDialog({ tool, label, onClose }: { tool: string; label: string; onClose: () => void }) {
  const [text, setText] = useState("");
  const parsed = parseCoordinates(text);
  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!parsed) return;
    const st = useEditor.getState();
    if (st.tool !== tool) st.setTool(tool as never);
    st.set({ cameraRequest: { points: [parsed.pos], nonce: Date.now(), maxZoom: 18 }, pin: parsed.pos,
      placeRequest: { pos: parsed.pos, nonce: Date.now() } });
    onClose();
  };
  return (
    <Modal title={`${label}: ingresar coordenadas`} onClose={onClose}>
      <form onSubmit={submit}>
        <label className={`field stacked ${text && !parsed ? "invalid" : ""}`}>
          <span>Coordenadas</span>
          <input autoFocus value={text} onChange={(e) => setText(e.target.value)} aria-label="Coordenadas del elemento"
            placeholder="-29.9420, -71.1450 · 29°56′31″S 71°08′42″W · 292975 6685706 19S" />
        </label>
        <p className="muted small">Lat/lon decimal, grados-minutos-segundos o UTM (Este, Norte y huso; sin huso se usa
          {` ${DEFAULT_ZONE}${DEFAULT_SOUTH ? "S" : "N"}`}).</p>
        {parsed ? <Preview pos={parsed.pos} /> : text ? <p className="bad-text small">No se reconoce la coordenada.</p> : null}
        <div className="modal-actions">
          <button type="button" className="ghost" onClick={onClose}>Cancelar</button>
          <button className="primary" disabled={!parsed}>Crear {label.toLowerCase()}</button>
        </div>
      </form>
    </Modal>
  );
}

// ── Editar coordenadas de un elemento ──

export function CoordinatesSection({ uid }: { uid: string }) {
  const net = useEditor((s) => s.net);
  const readOnly = useEditor((s) => s.readOnly);
  const pos = positionOf(net, uid);
  const [mode, setMode] = useState<"geo" | "utm">("geo");
  const [lat, setLat] = useState("");
  const [lon, setLon] = useState("");
  const [e, setE] = useState("");
  const [n, setN] = useState("");
  const [zone, setZone] = useState(String(DEFAULT_ZONE));
  const [south, setSouth] = useState(DEFAULT_SOUTH);
  const key = pos ? `${pos[0]},${pos[1]}` : "";
  useEffect(() => {
    if (!pos) return;
    const u = toUtm(pos, Number(zone) || DEFAULT_ZONE, south);
    setLat(pos[1].toFixed(7));
    setLon(pos[0].toFixed(7));
    setE(u.e.toFixed(2));
    setN(u.n.toFixed(2));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, uid]);
  if (!pos) return null;
  let target: LngLat | null = null;
  if (mode === "geo") {
    const a = parseNum(lat);
    const b = parseNum(lon);
    if (a !== null && b !== null && Math.abs(a) <= 90 && Math.abs(b) <= 180) target = [b, a];
  } else {
    const x = parseNum(e);
    const y = parseNum(n);
    const z = Number(zone);
    if (x !== null && y !== null && z >= 1 && z <= 60 && x > 100000 && x < 900000) target = fromUtm({ e: x, n: y, zone: z, south });
  }
  const moved = !!target && (Math.abs(target[0] - pos[0]) > 1e-9 || Math.abs(target[1] - pos[1]) > 1e-9);
  const apply = (ev: React.FormEvent) => {
    ev.preventDefault();
    if (!target || !moved) return;
    const st = useEditor.getState();
    st.commit((nn) => moveElement(nn, uid, target!));
    st.toast("Elemento movido a las coordenadas: los largos y conexiones se recalculan.");
  };
  const isShutoff = !!net.shutoffs[uid];
  return (
    <Section id="elemento.coordenadas" title="Coordenadas" primary>
      <form className="coord-edit" onSubmit={apply}>
        <div className="seg small" role="group" aria-label="Formato de coordenadas">
          <button type="button" className={mode === "geo" ? "on" : ""} onClick={() => setMode("geo")}>Lat/lon</button>
          <button type="button" className={mode === "utm" ? "on" : ""} onClick={() => setMode("utm")}>UTM</button>
        </div>
        {mode === "geo" ? (<>
          <label className="field"><span>Latitud</span><input inputMode="decimal" value={lat} onChange={(x) => setLat(x.target.value)} aria-label="Latitud" disabled={readOnly} /></label>
          <label className="field"><span>Longitud</span><input inputMode="decimal" value={lon} onChange={(x) => setLon(x.target.value)} aria-label="Longitud" disabled={readOnly} /></label>
        </>) : (<>
          <label className="field"><span>Este (m)</span><input inputMode="decimal" value={e} onChange={(x) => setE(x.target.value)} aria-label="Este UTM" disabled={readOnly} /></label>
          <label className="field"><span>Norte (m)</span><input inputMode="decimal" value={n} onChange={(x) => setN(x.target.value)} aria-label="Norte UTM" disabled={readOnly} /></label>
          <label className="field"><span>Huso</span>
            <div className="with-unit">
              <input inputMode="numeric" value={zone} onChange={(x) => setZone(x.target.value)} aria-label="Huso UTM" disabled={readOnly} />
              <select value={south ? "S" : "N"} onChange={(x) => setSouth(x.target.value === "S")} aria-label="Hemisferio" disabled={readOnly}>
                <option value="S">Sur</option><option value="N">Norte</option>
              </select>
            </div>
          </label>
        </>)}
        <p className="muted small mono">{toDms(pos)} · {formatUtm(toUtm(pos, Number(zone) || DEFAULT_ZONE, south))}</p>
        {isShutoff && <p className="muted small">La llave se ubica en el punto más cercano de su tubería.</p>}
        {!readOnly && <button className="small" disabled={!moved}>Mover a estas coordenadas</button>}
      </form>
    </Section>
  );
}

// ── Coordenada del cursor ──

export function CoordBar({ host, camera, size }: { host: React.RefObject<HTMLDivElement | null>; camera: Camera; size: Size }) {
  const [cur, setCur] = useState<LngLat | null>(null);
  const cam = useRef(camera);
  cam.current = camera;
  const sz = useRef(size);
  sz.current = size;
  const pin = useEditor((s) => s.pin);
  const toast = useEditor((s) => s.toast);
  useEffect(() => {
    const el = host.current;
    if (!el) return;
    let raf = 0;
    const move = (e: PointerEvent) => {
      if ((e.target as Element | null)?.closest?.(".coord-bar, .map-controls, .legend, .hour-slider")) return;
      const r = el.getBoundingClientRect();
      const p: [number, number] = [e.clientX - r.left, e.clientY - r.top];
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => setCur(unproject(p, cam.current, sz.current)));
    };
    el.addEventListener("pointermove", move);
    return () => { el.removeEventListener("pointermove", move); cancelAnimationFrame(raf); };
  }, [host]);
  const pos = cur ?? camera.center;
  const u = toUtm(pos, DEFAULT_ZONE, DEFAULT_SOUTH);
  const text = `${formatLatLon(pos)} (UTM ${zoneLabel(u)} E ${u.e.toFixed(1)} N ${u.n.toFixed(1)})`;
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      toast("Coordenada copiada.");
    } catch {
      toast(text);
    }
  };
  return (
    <div className="coord-bar" role="status" aria-label="Coordenada del cursor">
      <span className="mono" data-latlon={formatLatLon(pos)}>{formatLatLon(pos, 6)}</span>
      <span className="mono muted">UTM {formatUtm(u)}</span>
      <button type="button" className="ghost small" onClick={() => void copy()} title="Copiar la coordenada del cursor">Copiar</button>
      {pin && <button type="button" className="ghost small" onClick={() => useEditor.getState().set({ pin: null })} title="Quitar la marca de la coordenada buscada">Quitar marca</button>}
    </div>
  );
}
