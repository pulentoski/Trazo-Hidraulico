// Mapa base de Google, con cámara no controlada: se crea en la vista inicial (defaultCenter/defaultZoom), recibe
// rueda y arrastre directamente (gestureHandling "greedy") e informa cada cambio de cámara a la capa de la red, que
// usa la misma proyección Web Mercator. El editor lo mueve de forma imperativa (moveCamera) al encuadrar o al
// desplazar desde una herramienta de dibujo. Se crea y se destruye con el editor (sin reutilizar instancias).
import type { MapCameraChangedEvent } from "@vis.gl/react-google-maps";
import { Map as GMap, useMap, useMapsLibrary } from "@vis.gl/react-google-maps";
import { useEffect, useState } from "react";
import type { Camera } from "../lib/geo";
import type { MapType, Theme } from "../state/store";

import { useMapConfig } from "../lib/mapConfig";

/** Entrega la instancia al editor y la retira al desmontar (sin referencias a mapas destruidos). */
function MapHandle({ onMap }: { onMap: (m: google.maps.Map | null) => void }) {
  const map = useMap();
  useEffect(() => {
    if (!map) return;
    onMap(map);
    return () => onMap(null);
  }, [map, onMap]);
  return null;
}

interface Props {
  initial: Camera;
  mapType: MapType;
  theme: Theme;
  onCamera: (c: Camera) => void;
  onMap: (m: google.maps.Map | null) => void;
  /** Clic sobre el fondo del mapa (fuera de los elementos de la red). */
  onBackgroundClick: () => void;
}

export function GoogleBase({ initial, mapType, theme, onCamera, onMap, onBackgroundClick }: Props) {
  const MAP_ID = useMapConfig((s) => s.mapId) || undefined;
  const changed = (e: MapCameraChangedEvent) => onCamera({ center: [e.detail.center.lng, e.detail.center.lat], zoom: e.detail.zoom });
  return (
    <div className="map-base">
      <GMap
        mapId={MAP_ID}
        defaultCenter={{ lat: initial.center[1], lng: initial.center[0] }}
        defaultZoom={initial.zoom}
        mapTypeId={mapType}
        gestureHandling="greedy"
        disableDefaultUI
        keyboardShortcuts={false}
        clickableIcons={false}
        disableDoubleClickZoom
        isFractionalZoomEnabled={false}
        colorScheme={MAP_ID ? (theme === "dark" ? "DARK" : "LIGHT") : undefined}
        onCameraChanged={changed}
        onClick={onBackgroundClick}
        style={{ position: "absolute", inset: 0 }}
      >
        <MapHandle onMap={onMap} />
      </GMap>
    </div>
  );
}

/** Búsqueda de dirección con el Geocoder de Google (requiere la API de Geocoding habilitada en la key). */
export function useGeocoder() {
  const lib = useMapsLibrary("geocoding");
  const [geocoder, setGeocoder] = useState<google.maps.Geocoder | null>(null);
  useEffect(() => {
    if (lib) setGeocoder(new lib.Geocoder());
  }, [lib]);
  return geocoder;
}

export function BlankBase({ camera }: { camera: Camera }) {
  // Grilla neutra cuya separación sigue el zoom (referencia visual sin mapa base).
  const step = 32 * 2 ** ((camera.zoom % 2) / 2);
  return <div className="map-base blank" style={{ backgroundSize: `${step}px ${step}px, ${step * 4}px ${step * 4}px` }} />;
}
