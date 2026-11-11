// Vista previa del ajuste por puntos de control: la imagen se dibuja sobre el mapa con la transformación afín que
// lleva sus esquinas a la posición calculada (en el área de una ortofoto, Web Mercator es localmente afín).
import type { Camera, Size } from "../lib/geo";
import { project } from "../lib/geo";
import { useEditor } from "../state/store";

/** Matriz CSS (a, b, c, d, e, f) que lleva (0,0), (w,0) y (0,h) a los puntos de pantalla p0, p1 y p3. */
export function cornerMatrix(w: number, h: number, p0: [number, number], p1: [number, number], p3: [number, number]): number[] {
  return [(p1[0] - p0[0]) / w, (p1[1] - p0[1]) / w, (p3[0] - p0[0]) / h, (p3[1] - p0[1]) / h, p0[0], p0[1]];
}

export function GcpPreviewLayer({ camera, size }: { camera: Camera; size: Size }) {
  const pv = useEditor((s) => s.gcpPreview);
  if (!pv || pv.corners.length < 4) return null;
  const [p0, p1, , p3] = pv.corners.map((c) => project(c, camera, size));
  const m = cornerMatrix(pv.width, pv.height, p0, p1, p3);
  return (
    <div className="gcp-preview" aria-hidden="true">
      <img src={pv.url} alt="" draggable={false} width={pv.width} height={pv.height}
        style={{ opacity: pv.opacity, transform: `matrix(${m.join(",")})` }} />
      <svg width={size.width} height={size.height}>
        <polygon points={pv.corners.map((c) => project(c, camera, size).join(",")).join(" ")} />
      </svg>
    </div>
  );
}
