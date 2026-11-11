import { APIProvider } from "@vis.gl/react-google-maps";
import { Suspense, lazy, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api/client";
import { LabelsControl } from "../components/LabelsControl";
import { Legend } from "../components/Legend";
import { ScaleBar } from "../components/ScaleBar";
import type { BaseKind } from "../lib/mapConfig";
import { baseOf, useMapConfig } from "../lib/mapConfig";
import { nominatim } from "../lib/nominatim";
import type { Camera, LngLat, Size } from "../lib/geo";
import { fitBounds, unproject, zoomAt } from "../lib/geo";
import type { MapType } from "../state/store";
import { useEditor, writePref } from "../state/store";
import { BlankBase, GoogleBase, useGeocoder } from "./GoogleBase";
import { QuickSearch } from "../components/QuickSearch";
import { useOrthos } from "../components/LayersTab";
import { hourLabel } from "../lib/patterns";
import { NetworkLayer } from "./NetworkLayer";
import { GcpPreviewLayer } from "./GcpPreviewLayer";
import { OrthoLayer } from "./OrthoLayer";

const DEFAULT_CENTER: LngLat = [
  Number(import.meta.env.VITE_DEFAULT_MAP_CENTER_LNG || -70.6693),
  Number(import.meta.env.VITE_DEFAULT_MAP_CENTER_LAT || -33.4489),
];
const GOOGLE_TYPES: { id: MapType; label: string }[] = [
  { id: "roadmap", label: "Calle" }, { id: "terrain", label: "Terreno" },
  { id: "satellite", label: "Satélite" }, { id: "hybrid", label: "Híbrido" },
];
/** OpenStreetMap: calle (OSM) o satélite (Esri World Imagery, con su atribución). */
const OSM_TYPES: { id: MapType; label: string }[] = [{ id: "roadmap", label: "Calle" }, { id: "satellite", label: "Satélite" }];
const isSatellite = (t: MapType) => t === "satellite" || t === "hybrid";

type Geocode = (q: string) => Promise<LngLat | null>;

/** Búsqueda de dirección: Geocoder de Google o Nominatim (OpenStreetMap), según el mapa base. */
function AddressSearch({ onLocate, geocode, failText }: { onLocate: (c: Camera) => void; geocode: Geocode | null; failText: string }) {
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const toast = useEditor((s) => s.toast);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!geocode || !q.trim()) return;
    setBusy(true);
    try {
      const pos = await geocode(q.trim());
      if (pos) onLocate({ center: pos, zoom: 17 });
      else toast("No se encontró la dirección.", "error");
    } catch {
      toast(failText, "error");
    } finally {
      setBusy(false);
    }
  };
  return (
    <form className="map-search" onSubmit={submit}>
      <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar dirección…" aria-label="Buscar dirección" />
      <button type="submit" disabled={busy || !geocode}>{busy ? "…" : "Ir"}</button>
    </form>
  );
}

function GoogleAddressSearch({ onLocate }: { onLocate: (c: Camera) => void }) {
  const geocoder = useGeocoder();
  const geocode = useMemo<Geocode | null>(() => geocoder && (async (q) => {
    const { results } = await geocoder.geocode({ address: q, region: "cl", language: "es" });
    const loc = results[0]?.geometry.location;
    return loc ? [loc.lng(), loc.lat()] : null;
  }), [geocoder]);
  return <AddressSearch onLocate={onLocate} geocode={geocode}
    failText="La búsqueda de direcciones no está disponible (revise la API de Geocoding de la key)." />;
}

function OsmAddressSearch({ onLocate }: { onLocate: (c: Camera) => void }) {
  return <AddressSearch onLocate={onLocate} geocode={nominatim}
    failText="La búsqueda de direcciones de OpenStreetMap (Nominatim) no respondió; intente de nuevo en unos segundos." />;
}

const OsmBase = lazy(() => import("./OsmBase"));

/** Última vista del proyecto en este navegador (se restaura al volver a entrar). */
function readView(pid: string): Camera | null {
  try {
    const v = JSON.parse(localStorage.getItem(`trazo.view.${pid}`) ?? "null") as Camera | null;
    return v && Array.isArray(v.center) && v.center.every(Number.isFinite) && Number.isFinite(v.zoom) ? v : null;
  } catch { return null; }
}

/** Tamaño del elemento, medido de nuevo cada vez que el nodo DOM cambia (ref de callback, no un efecto de montaje). */
function useElementSize(): [(el: HTMLDivElement | null) => void, Size, React.RefObject<HTMLDivElement | null>] {
  const [size, setSize] = useState<Size>({ width: 0, height: 0 });
  const elRef = useRef<HTMLDivElement | null>(null);
  const roRef = useRef<ResizeObserver | null>(null);
  const ref = useCallback((el: HTMLDivElement | null) => {
    roRef.current?.disconnect();
    roRef.current = null;
    elRef.current = el;
    if (!el) return;
    const measure = () => {
      const w = el.clientWidth, h = el.clientHeight;
      setSize((s) => (s.width === w && s.height === h ? s : { width: w, height: h }));
    };
    roRef.current = new ResizeObserver(measure);
    roRef.current.observe(el);
    measure();
  }, []);
  return [ref, size, elRef];
}

/** Herramientas que no usan clics sobre el fondo: con mapa base (Google u OSM), el mapa recibe arrastre y rueda. */
const NAV_TOOLS = new Set(["select", "move"]);

export function MapView() {
  const [ref, size, elRef] = useElementSize();
  const { provider, apiKey: API_KEY, loaded: mapConfigLoaded, load: loadMapConfig } = useMapConfig();
  useEffect(() => { if (!mapConfigLoaded) void loadMapConfig(); }, [mapConfigLoaded, loadMapConfig]);
  const [mapFailed, setMapFailed] = useState(false);
  const ready = mapConfigLoaded && size.width > 0 && size.height > 0;
  const wanted = baseOf(provider, API_KEY);
  // Las capas se montan una sola vez, con la configuración y el tamaño ya conocidos: un cambio posterior de
  // proveedor no reemplaza el contenedor medido (antes, la llegada de la key re-montaba .map y dejaba la capa en 0×0).
  return (
    <div className="map" ref={ref}>
      {ready && (wanted === "google"
        ? <APIProvider apiKey={API_KEY} language="es" region="CL" onError={() => setMapFailed(true)}>
            <MapLayers wanted="google" googleFailed={mapFailed} size={size} host={elRef} />
          </APIProvider>
        : <MapLayers wanted="osm" googleFailed={false} size={size} host={elRef} />)}
    </div>
  );
}

/** Mueve el mapa base de forma imperativa (Google: moveCamera; MapLibre: jumpTo). */
interface BaseHandle { move: (c: Camera) => void }

function MapLayers({ wanted, googleFailed, size, host }: { wanted: BaseKind; googleFailed: boolean; size: Size; host: React.RefObject<HTMLDivElement | null> }) {
  const pid = useEditor((s) => s.project?.id ?? "");
  // Vista inicial: la última guardada del proyecto o el encuadre de la red. El encuadre pedido al abrir queda atendido.
  const [initial] = useState<Camera>(() => {
    const st = useEditor.getState();
    const saved = readView(pid);
    if (saved) return saved;
    const c = st.cameraRequest?.points.length ? fitBounds(st.cameraRequest.points, size, 80) : null;
    return c ? { ...c, zoom: Math.min(c.zoom, 19) } : { center: DEFAULT_CENTER, zoom: 16 };
  });
  const handled = useRef(useEditor.getState().cameraRequest?.nonce ?? 0);
  const [camera, setCameraState] = useState<Camera>(initial);
  const cameraRef = useRef(camera);
  cameraRef.current = camera;
  const baseRef = useRef<BaseHandle | null>(null);
  const [quotaDenied, setQuotaDenied] = useState(false);
  const [osmFailed, setOsmFailed] = useState(false);
  const cameraRequest = useEditor((s) => s.cameraRequest);
  const mapType = useEditor((s) => s.mapType);
  const theme = useEditor((s) => s.theme);
  const tool = useEditor((s) => s.tool);
  const picking = useEditor((s) => Boolean(s.mapPick));
  const setStore = useEditor((s) => s.set);
  useEffect(() => {
    if (wanted !== "google") return;
    let alive = true;
    api.mapLoad().then((r) => { if (alive && !r.allowed) setQuotaDenied(true); }).catch(() => undefined);
    return () => { alive = false; };
  }, [wanted]);
  // Google no disponible (script, key o cuota) → OpenStreetMap; sin WebGL → lienzo neutro.
  const googleDown = wanted === "google" && (googleFailed || quotaDenied);
  const base: BaseKind | "blank" = wanted === "google" && !googleDown ? "google" : osmFailed ? "blank" : "osm";
  const { orthos } = useOrthos();
  const [noticeClosed, setNoticeClosed] = useState(() => {
    try { return localStorage.getItem("trazo.hideMapNotice") === "true"; } catch { return false; }
  });
  const hasOrtho = orthos.some((o) => o.status === "ready" && o.visible);

  /** Mueve la cámara: con mapa base, este es la autoridad (movimiento imperativo) y su evento confirma la vista. */
  const setCamera = useCallback((c: Camera) => {
    setCameraState(c);
    baseRef.current?.move(c);
  }, []);
  const onMapCamera = useCallback((c: Camera) => {
    const cur = cameraRef.current;
    if (cur.zoom === c.zoom && Math.abs(cur.center[0] - c.center[0]) < 1e-9 && Math.abs(cur.center[1] - c.center[1]) < 1e-9) return;
    setCameraState(c);
  }, []);
  const onGoogleMap = useCallback((m: google.maps.Map | null) => {
    baseRef.current = m && { move: (c) => m.moveCamera({ center: { lat: c.center[1], lng: c.center[0] }, zoom: c.zoom }) };
  }, []);
  const onOsm = useCallback((h: BaseHandle | null) => { baseRef.current = h; }, []);
  const onWheelStep = useCallback((at: [number, number], d: number) => setCamera(zoomAt(cameraRef.current, size, at, d)), [setCamera, size]);
  const onBackgroundClick = useCallback(() => {
    const st = useEditor.getState();
    if (NAV_TOOLS.has(st.tool) && !st.mapPick) st.select([]);
  }, []);

  // Guarda la última vista del proyecto (para volver a entrar donde se quedó).
  useEffect(() => {
    if (!pid) return;
    const t = window.setTimeout(() => writePref(`view.${pid}`, camera), 400);
    return () => window.clearTimeout(t);
  }, [pid, camera]);

  useEffect(() => {
    if (!cameraRequest || !cameraRequest.points.length || cameraRequest.nonce === handled.current) return;
    handled.current = cameraRequest.nonce;
    // Si un panel tapa el mapa por la izquierda, se encuadra en la parte visible.
    const left = host.current?.getBoundingClientRect().left ?? 0;
    const hidden = Math.max(0, Math.min(size.width - 200, (cameraRequest.coverLeft ?? 0) - left));
    const c = fitBounds(cameraRequest.points, { width: size.width - hidden, height: size.height }, 80);
    if (!c) return;
    const cam = { ...c, zoom: Math.min(c.zoom, cameraRequest.maxZoom ?? 19) };
    setCamera(hidden ? { ...cam, center: unproject([size.width / 2 - hidden / 2, size.height / 2], cam, size) } : cam);
  }, [cameraRequest, size, host, setCamera]);

  const zoom = (d: number) => setCamera(zoomAt(cameraRef.current, size, [size.width / 2, size.height / 2], d));
  // Con mapa base y una herramienta de navegación, el fondo deja pasar los gestos al mapa (greedy); los elementos de
  // la red siguen recibiendo clics. Las herramientas de dibujo, medición o selección de punto capturan el fondo y
  // desplazan/acercan el mapa con la misma cámara.
  const passThrough = base !== "blank" && NAV_TOOLS.has(tool) && !picking;
  const types = base === "google" ? GOOGLE_TYPES : base === "osm" ? OSM_TYPES : [];
  const shownType = base === "osm" ? (isSatellite(mapType) ? "satellite" : "roadmap") : mapType;

  return (
    <>
      {base === "google" && <GoogleBase initial={initial} mapType={mapType} theme={theme} onCamera={onMapCamera} onMap={onGoogleMap}
        onBackgroundClick={onBackgroundClick} />}
      {base === "osm" && (
        <Suspense fallback={<BlankBase camera={camera} />}>
          <OsmBase initial={cameraRef.current} satellite={isSatellite(mapType)} dark={theme === "dark"} onCamera={onMapCamera} onReady={onOsm}
            onBackgroundClick={onBackgroundClick} onWheelStep={onWheelStep} onError={() => setOsmFailed(true)} />
        </Suspense>
      )}
      {base === "blank" && <BlankBase camera={camera} />}
      <OrthoLayer camera={camera} size={size} />
      <GcpPreviewLayer camera={camera} size={size} />
      <NetworkLayer camera={camera} size={size} setCamera={setCamera} passThrough={passThrough} />
      <div className="map-controls top-left">
        {base === "google" && <GoogleAddressSearch onLocate={setCamera} />}
        {base === "osm" && <OsmAddressSearch onLocate={setCamera} />}
        <QuickSearch />
        <LabelsControl />
      </div>
      <div className="map-controls top-right">
        {types.length > 0 && (
          <div className="seg" role="group" aria-label="Tipo de mapa">
            {types.map((t) => (
              <button key={t.id} className={shownType === t.id ? "on" : ""}
                onClick={() => { setStore({ mapType: t.id }); writePref("mapType", t.id); }}>{t.label}</button>
            ))}
          </div>
        )}
        <div className="zoom-btns" role="group" aria-label="Zoom del mapa">
          <button onClick={() => zoom(1)} title="Acercar" aria-label="Acercar">+</button>
          <button onClick={() => zoom(-1)} title="Alejar" aria-label="Alejar">−</button>
          <button onClick={() => useEditor.getState().fitAll()} title="Centrar en la red" aria-label="Centrar en la red">⤢</button>
        </div>
      </div>
      <Legend />
      {(base === "blank" ? !hasOrtho : googleDown) && !noticeClosed && (
        <div className="map-notice" role="status">
          <button className="ghost small notice-close" aria-label="Cerrar aviso" onClick={() => { setNoticeClosed(true); writePref("hideMapNotice", true); }}>✕</button>
          {base === "blank" ? <>
            <strong>Mapa base no disponible.</strong> Este navegador no pudo iniciar el mapa de OpenStreetMap (requiere
            WebGL). El editor y la simulación funcionan igual sobre este lienzo; también puede usar una ortofoto propia como
            fondo (pestaña Capas).
          </> : <>
            <strong>Se usa OpenStreetMap.</strong>{" "}
            {quotaDenied ? "Se alcanzó el límite mensual de cargas de Google Maps del plan de su organización."
              : "No se pudo cargar Google Maps (revise la key y sus restricciones en Configuración → Mapa base)."}
          </>}
        </div>
      )}
      <ScaleBar camera={camera} />
      <HourSlider />
    </>
  );
}

/** Selector de hora sobre el mapa (período extendido): actualiza colores y etiquetas de la red. */
function HourSlider() {
  const result = useEditor((s) => s.result);
  const period = useEditor((s) => s.period);
  const set = useEditor((s) => s.set);
  if (!result || result.times.length < 2) return null;
  const last = result.times.length - 1;
  return (
    <div className="hour-slider" role="group" aria-label="Hora de la simulación">
      <button className="small ghost" onClick={() => set({ period: Math.max(0, period - 1) })} aria-label="Hora anterior">◀</button>
      <input type="range" min={0} max={last} value={period} onChange={(e) => set({ period: Number(e.target.value) })} aria-label="Hora" />
      <button className="small ghost" onClick={() => set({ period: Math.min(last, period + 1) })} aria-label="Hora siguiente">▶</button>
      <b>{hourLabel(result.times[period] ?? 0)}</b>
    </div>
  );
}
