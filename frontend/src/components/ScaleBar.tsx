import type { Camera } from "../lib/geo";
import { scaleBar } from "../lib/geo";

/** Escala gráfica en metros, válida con y sin mapa base (misma proyección Web Mercator). */
export function ScaleBar({ camera }: { camera: Camera }) {
  const s = scaleBar(camera, 120);
  return (
    <div className="scale-bar" aria-label={`Escala: ${s.label}`} title={`Zoom ${camera.zoom}`}>
      <span>{s.label}</span>
      <i style={{ width: `${s.px}px` }} />
    </div>
  );
}
