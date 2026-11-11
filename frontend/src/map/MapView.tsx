import { APIProvider } from "@vis.gl/react-google-maps";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { api } from "../api/client";
import { LabelsControl } from "../components/LabelsControl";
import { Legend } from "../components/Legend";
import { ScaleBar } from "../components/ScaleBar";
import { GOOGLE_MAPS_API_KEY as API_KEY } from "../lib/mapConfig";
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
const MAP_TYPES: { id: MapType; label: string }[] = [
  { id: "roadmap", label: "Calle" }, { id: "terrain", label: "Terreno" },
  { id: "satellite", label: "Satélite" }, { id: "hybrid", label: "Híbrido" },
];

function AddressSearch({ onLocate }: { onLocate: (c: Camera) => void }) {
  const geocoder = useGeocoder();
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const toast = useEditor((s) => s.toast);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!geocoder || !q.trim()) return;
    setBusy(true);
    try {
      const { results } = await geocoder.geocode({ address: q, region: "cl", language: "es" });
      const loc = results[0]?.geometry.location;
      if (loc) onLocate({ center: [loc.lng(), loc.lat()], zoom: 17 });
      else toast("No se encontró la dirección.", "error");
    } catch {
      toast("La búsqueda de direcciones no está disponible (revise la API de Geocoding de la key).", "error");
    } finally {
      setBusy(false);
    }
  };
  return (
    <form className="map-search" onSubmit={submit}>
      <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar dirección…" aria-label="Buscar dirección" />
      <button type="submit" disabled={busy || !geocoder}>{busy ? "…" : "Ir"}</button>
    </form>
  );
}

export function MapView() {
  const ref = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState<Size>({ width: 800, height: 600 });
  const [camera, setCamera] = useState<Camera>({ center: DEFAULT_CENTER, zoom: 16 });
  const [mapFailed, setMapFailed] = useState(false);
  const cameraRequest = useEditor((s) => s.cameraRequest);
  const mapType = useEditor((s) => s.mapType);
  const theme = useEditor((s) => s.theme);
  const setStore = useEditor((s) => s.set);
  const [quotaDenied, setQuotaDenied] = useState(false);
  useEffect(() => {
    if (!API_KEY) return;
    api.mapLoad().then((r) => { if (!r.allowed) setQuotaDenied(true); }).catch(() => undefined);
  }, []);
  const useGoogle = Boolean(API_KEY) && !mapFailed && !quotaDenied;
  const { orthos } = useOrthos();
  const [noticeClosed, setNoticeClosed] = useState(() => {
    try { return localStorage.getItem("trazo.hideMapNotice") === "true"; } catch { return false; }
  });
  const hasOrtho = orthos.some((o) => o.status === "ready" && o.visible);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setSize({ width: el.clientWidth, height: el.clientHeight }));
    ro.observe(el);
    setSize({ width: el.clientWidth, height: el.clientHeight });
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    if (!cameraRequest || !cameraRequest.points.length) return;
    // Si un panel tapa el mapa por la izquierda, se encuadra en la parte visible.
    const left = ref.current?.getBoundingClientRect().left ?? 0;
    const hidden = Math.max(0, Math.min(size.width - 200, (cameraRequest.coverLeft ?? 0) - left));
    const c = fitBounds(cameraRequest.points, { width: size.width - hidden, height: size.height }, 80);
    if (!c) return;
    const cam = { ...c, zoom: Math.min(c.zoom, 19) };
    setCamera(hidden ? { ...cam, center: unproject([size.width / 2 - hidden / 2, size.height / 2], cam, size) } : cam);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cameraRequest]);

  const zoom = (d: number) => setCamera(zoomAt(camera, size, [size.width / 2, size.height / 2], d));

  const content = (
    <div className="map" ref={ref}>
      {useGoogle ? <GoogleBase camera={camera} mapType={mapType} theme={theme} /> : <BlankBase camera={camera} />}
      <OrthoLayer camera={camera} size={size} />
      <GcpPreviewLayer camera={camera} size={size} />
      <NetworkLayer camera={camera} size={size} setCamera={setCamera} />
      <div className="map-controls top-left">
        {useGoogle && <AddressSearch onLocate={setCamera} />}
        <QuickSearch />
        <LabelsControl />
      </div>
      <div className="map-controls top-right">
        {useGoogle && (
          <div className="seg" role="group" aria-label="Tipo de mapa">
            {MAP_TYPES.map((t) => (
              <button key={t.id} className={mapType === t.id ? "on" : ""}
                onClick={() => { setStore({ mapType: t.id }); writePref("mapType", t.id); }}>{t.label}</button>
            ))}
          </div>
        )}
        <div className="zoom-btns">
          <button onClick={() => zoom(1)} title="Acercar">+</button>
          <button onClick={() => zoom(-1)} title="Alejar">−</button>
          <button onClick={() => useEditor.getState().fitAll()} title="Ajustar a la red">⤢</button>
        </div>
      </div>
      <Legend />
      {!useGoogle && !hasOrtho && !noticeClosed && (
        <div className="map-notice" role="status">
          <button className="ghost small notice-close" aria-label="Cerrar aviso" onClick={() => { setNoticeClosed(true); writePref("hideMapNotice", true); }}>✕</button>
          <strong>Mapa base no disponible.</strong>{" "}
          {quotaDenied ? "Se alcanzó el límite mensual de cargas del mapa del plan de su organización." : API_KEY ? "No se pudo cargar Google Maps (revise la key y sus restricciones)." :
            "Configure VITE_GOOGLE_MAPS_API_KEY en .env y ejecute make up."} El editor y la simulación funcionan igual sobre este lienzo; también puede usar una ortofoto propia como fondo (pestaña Capas).
        </div>
      )}
      <ScaleBar camera={camera} />
      <HourSlider />
    </div>
  );

  if (!API_KEY) return content;
  return (
    <APIProvider apiKey={API_KEY} language="es" region="CL" onError={() => setMapFailed(true)}>
      {content}
    </APIProvider>
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
