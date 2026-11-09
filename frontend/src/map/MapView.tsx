import { APIProvider } from "@vis.gl/react-google-maps";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Legend } from "../components/Legend";
import type { Camera, LngLat, Size } from "../lib/geo";
import { fitBounds, zoomAt } from "../lib/geo";
import type { MapType } from "../state/store";
import { useEditor, writePref } from "../state/store";
import { BlankBase, GoogleBase, useGeocoder } from "./GoogleBase";
import { NetworkLayer } from "./NetworkLayer";

const API_KEY = import.meta.env.VITE_GOOGLE_MAPS_API_KEY || "";
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
  const useGoogle = Boolean(API_KEY) && !mapFailed;

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
    const c = fitBounds(cameraRequest.points, size, 80);
    if (c) setCamera({ ...c, zoom: Math.min(c.zoom, 19) });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cameraRequest]);

  const zoom = (d: number) => setCamera(zoomAt(camera, size, [size.width / 2, size.height / 2], d));

  const content = (
    <div className="map" ref={ref}>
      {useGoogle ? <GoogleBase camera={camera} mapType={mapType} theme={theme} /> : <BlankBase camera={camera} />}
      <NetworkLayer camera={camera} size={size} setCamera={setCamera} />
      <div className="map-controls top-left">
        {useGoogle ? <AddressSearch onLocate={setCamera} /> : (
          <div className="map-search disabled" title="Requiere la key de Google Maps"><input disabled placeholder="Búsqueda no disponible sin mapa base" /></div>
        )}
      </div>
      <div className="map-controls top-right">
        <div className="seg" role="group" aria-label="Tipo de mapa">
          {MAP_TYPES.map((t) => (
            <button key={t.id} className={mapType === t.id ? "on" : ""} disabled={!useGoogle}
              onClick={() => { setStore({ mapType: t.id }); writePref("mapType", t.id); }}>{t.label}</button>
          ))}
        </div>
        <div className="zoom-btns">
          <button onClick={() => zoom(1)} title="Acercar">+</button>
          <button onClick={() => zoom(-1)} title="Alejar">−</button>
          <button onClick={() => useEditor.getState().fitAll()} title="Ajustar a la red">⤢</button>
        </div>
      </div>
      <Legend />
      {!useGoogle && (
        <div className="map-notice" role="status">
          <strong>Mapa base no disponible.</strong>{" "}
          {API_KEY ? "No se pudo cargar Google Maps (revise la key y sus restricciones)." :
            "Configure VITE_GOOGLE_MAPS_API_KEY en .env y ejecute make up."} El editor y la simulación funcionan igual sobre este lienzo.
        </div>
      )}
      <div className="map-scale">Zoom {camera.zoom}</div>
    </div>
  );

  if (!API_KEY) return content;
  return (
    <APIProvider apiKey={API_KEY} language="es" region="CL" onError={() => setMapFailed(true)}>
      {content}
    </APIProvider>
  );
}
