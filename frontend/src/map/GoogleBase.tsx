// Mapa base de Google. La cámara la controla el editor (misma proyección Web Mercator), por lo que el mapa
// no recibe gestos propios: toda la interacción ocurre en la capa SVG de la red.
import { Map as GMap, useMap, useMapsLibrary } from "@vis.gl/react-google-maps";
import { useEffect, useState } from "react";
import type { Camera } from "../lib/geo";
import type { MapType, Theme } from "../state/store";

import { useMapConfig } from "../lib/mapConfig";

function CameraSync({ camera, mapType }: { camera: Camera; mapType: MapType }) {
  const map = useMap();
  useEffect(() => {
    map?.moveCamera({ center: { lat: camera.center[1], lng: camera.center[0] }, zoom: camera.zoom, tilt: 0, heading: 0 });
  }, [map, camera]);
  useEffect(() => {
    map?.setMapTypeId(mapType);
  }, [map, mapType]);
  return null;
}

export function GoogleBase({ camera, mapType, theme }: { camera: Camera; mapType: MapType; theme: Theme }) {
  const MAP_ID = useMapConfig((s) => s.mapId) || undefined;
  return (
    <div className="map-base">
      <GMap
        mapId={MAP_ID}
        defaultCenter={{ lat: camera.center[1], lng: camera.center[0] }}
        defaultZoom={camera.zoom}
        mapTypeId={mapType}
        gestureHandling="none"
        disableDefaultUI
        keyboardShortcuts={false}
        clickableIcons={false}
        isFractionalZoomEnabled={false}
        colorScheme={MAP_ID ? (theme === "dark" ? "DARK" : "LIGHT") : undefined}
        style={{ position: "absolute", inset: 0 }}
      >
        <CameraSync camera={camera} mapType={mapType} />
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
