// Esqueletos animados mientras carga (en vez de pantallas vacías). El texto queda para lectores de pantalla.
export function Skeleton({ kind = "lines", rows = 4, label = "Cargando…" }: { kind?: "lines" | "tiles" | "map" | "page"; rows?: number; label?: string }) {
  return (
    <div className={`skeleton skeleton-${kind}`} role="status" aria-live="polite" aria-busy="true">
      <span className="sr-only">{label}</span>
      {kind === "lines" && Array.from({ length: rows }, (_, i) => <span key={i} className="skel skel-row" style={{ width: `${92 - ((i * 17) % 40)}%` }} />)}
      {kind === "tiles" && <div className="skel-tiles">{Array.from({ length: rows }, (_, i) => <span key={i} className="skel skel-block" />)}</div>}
      {kind === "map" && (<>
        <svg className="skel-net" viewBox="0 0 400 240" aria-hidden="true">
          <path d="M40 190 L120 110 L200 150 L280 70 L360 110 M200 150 L230 210 M120 110 L110 40" />
          {[[40, 190], [120, 110], [200, 150], [280, 70], [360, 110], [230, 210], [110, 40]].map(([x, y], i) => <circle key={i} cx={x} cy={y} r="7" />)}
        </svg>
        <p className="skel-caption">{label}</p>
      </>)}
      {kind === "page" && (<>
        <span className="skel skel-header" />
        <div className="skel-page-body">
          <span className="skel skel-row" style={{ width: "40%" }} />
          <div className="skel-tiles">{[0, 1, 2, 3].map((i) => <span key={i} className="skel skel-block" />)}</div>
          <span className="skel skel-row" style={{ width: "70%" }} /><span className="skel skel-row" style={{ width: "55%" }} />
        </div>
      </>)}
    </div>
  );
}
