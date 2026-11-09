// Ortofotos bajo la red: teselas XYZ servidas por TiTiler (mismo Web Mercator que la cámara del editor).
import type { Camera, Size } from "../lib/geo";
import { tileUrl, visibleTiles } from "../lib/sig";
import { useEditor } from "../state/store";

export function OrthoLayer({ camera, size }: { camera: Camera; size: Size }) {
  const orthos = useEditor((s) => s.orthos);
  const layers = orthos.filter((o) => o.status === "ready" && o.visible && o.tile_url).reverse(); // la más reciente arriba
  if (!layers.length) return null;
  return (
    <div className="ortho-layer" aria-hidden="true">
      {layers.map((o) => (
        <div key={o.id} className="ortho" style={{ opacity: o.opacity }}>
          {visibleTiles(camera, size, o.bounds).map((t) => (
            <img key={`${t.z}/${t.x}/${t.y}`} src={tileUrl(o.tile_url!, t)} alt="" draggable={false}
              style={{ left: t.left, top: t.top, width: t.size, height: t.size }}
              onError={(e) => { (e.target as HTMLImageElement).style.visibility = "hidden"; }} />
          ))}
        </div>
      ))}
    </div>
  );
}
