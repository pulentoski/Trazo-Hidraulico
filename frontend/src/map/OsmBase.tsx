// Mapa base OpenStreetMap con MapLibre (sin key): teselas raster de OSM y, opcional, imágenes satelitales de Esri,
// cada una con su atribución. Igual que Google: cámara no controlada (se crea en la vista inicial), arrastre propio
// del mapa e informe de cada cambio de cámara a la capa de la red. MapLibre usa teselas de 512 px por nivel, por lo
// que su zoom es el de Web Mercator de 256 px (el del editor) menos 1. La rueda acerca en pasos enteros, como en
// Google, para que las teselas raster se vean nítidas. Se carga bajo demanda (import dinámico desde MapView).
import { Map as MlMap, setWorkerUrl } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import { useEffect, useRef } from "react";
import type { Camera } from "../lib/geo";

setWorkerUrl(workerUrl);

export const OSM_ATTRIBUTION = '© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">Colaboradores de OpenStreetMap</a>';
export const ESRI_ATTRIBUTION = 'Imágenes © <a href="https://www.esri.com/" target="_blank" rel="noopener">Esri</a> — Fuente: Esri, Maxar, Earthstar Geographics y la comunidad de usuarios GIS';

/** Diferencia entre el zoom del editor (teselas de 256 px) y el de MapLibre (512 px). */
const Z = 1;

export interface OsmHandle { move: (c: Camera) => void }

interface Props {
  initial: Camera;
  satellite: boolean;
  dark: boolean;
  onCamera: (c: Camera) => void;
  onReady: (h: OsmHandle | null) => void;
  onBackgroundClick: () => void;
  /** Rueda sobre el mapa: punto (px relativos al mapa) y sentido (+1 acercar, −1 alejar). */
  onWheelStep: (at: [number, number], delta: number) => void;
  onError: () => void;
}

export default function OsmBase({ initial, satellite, dark, onCamera, onReady, onBackgroundClick, onWheelStep, onError }: Props) {
  const el = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MlMap | null>(null);
  const cb = useRef({ onCamera, onBackgroundClick, onWheelStep, onError });
  cb.current = { onCamera, onBackgroundClick, onWheelStep, onError };

  useEffect(() => {
    if (!el.current) return;
    let map: MlMap;
    try {
      map = new MlMap({
        container: el.current,
        style: {
          version: 8,
          sources: {
            osm: { type: "raster", tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"], tileSize: 256, maxzoom: 19 },
            esri: {
              type: "raster", tileSize: 256, maxzoom: 19,
              tiles: ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"],
            },
          },
          layers: [
            { id: "osm", type: "raster", source: "osm", layout: { visibility: satellite ? "none" : "visible" } },
            { id: "esri", type: "raster", source: "esri", layout: { visibility: satellite ? "visible" : "none" } },
          ],
        },
        center: initial.center,
        zoom: initial.zoom - Z,
        minZoom: 1,
        maxZoom: 22 - Z,
        attributionControl: false,
        scrollZoom: false,
        boxZoom: false,
        dragRotate: false,
        pitchWithRotate: false,
        doubleClickZoom: false,
        keyboard: false,
        touchPitch: false,
        renderWorldCopies: false,
      });
    } catch {
      cb.current.onError(); // sin WebGL: el editor sigue sobre el lienzo neutro
      return;
    }
    mapRef.current = map;
    map.touchZoomRotate.disableRotation();
    const report = () => {
      const c = map.getCenter();
      cb.current.onCamera({ center: [c.lng, c.lat], zoom: map.getZoom() + Z });
    };
    map.on("move", report);
    map.on("click", () => cb.current.onBackgroundClick());
    // Rueda: un paso entero por gesto (los paneles táctiles envían muchos eventos pequeños; se acumulan).
    let acc = 0;
    const wheel = (e: WheelEvent) => {
      e.preventDefault();
      acc += e.deltaY;
      if (Math.abs(acc) < 40) return;
      const r = map.getContainer().getBoundingClientRect();
      cb.current.onWheelStep([e.clientX - r.left, e.clientY - r.top], acc < 0 ? 1 : -1);
      acc = 0;
    };
    const canvas = map.getCanvasContainer();
    canvas.addEventListener("wheel", wheel, { passive: false });
    onReady({ move: (c) => map.jumpTo({ center: c.center, zoom: c.zoom - Z }) });
    return () => {
      onReady(null);
      canvas.removeEventListener("wheel", wheel);
      map.remove();
      mapRef.current = null;
    };
    // El mapa se crea una vez por montaje (cámara no controlada); los cambios de capa se aplican abajo.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const apply = () => {
      map.setLayoutProperty("osm", "visibility", satellite ? "none" : "visible");
      map.setLayoutProperty("esri", "visibility", satellite ? "visible" : "none");
    };
    if (map.isStyleLoaded()) apply();
    else map.once("load", apply);
  }, [satellite]);

  // Atribución propia (la del control de MapLibre no se actualiza al volver de satélite a calle con teselas en caché).
  return (
    <>
      <div className={`map-base osm${dark && !satellite ? " osm-dark" : ""}`} ref={el} />
      <div className="osm-attrib" role="contentinfo" aria-label="Atribución del mapa base"
        dangerouslySetInnerHTML={{ __html: `${satellite ? ESRI_ATTRIBUTION : OSM_ATTRIBUTION} · <a href="https://maplibre.org/" target="_blank" rel="noopener">MapLibre</a>` }} />
    </>
  );
}
