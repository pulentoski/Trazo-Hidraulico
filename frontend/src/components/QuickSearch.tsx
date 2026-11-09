// Búsqueda rápida global: ID, nombre, dirección, N° de medidor o de cliente.
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { SearchHit } from "../api/types";
import { uidOf } from "../lib/sig";
import { useEditor } from "../state/store";

const ELEMENT: Record<string, string> = {
  nudos: "nudo", tramos: "tramo", estanques: "estanque", reservorios: "reservorio", valvulas: "válvula", grifos: "grifo",
  pozos: "pozo", bombas: "bomba", clientes: "cliente",
};

export function QuickSearch() {
  const { project, net, focus, serverVersion } = useEditor();
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (!project || q.trim().length < 1) { setHits([]); return; }
    const t = window.setTimeout(() => { api.search(project.id, q.trim()).then(setHits).catch(() => setHits([])); }, 200);
    return () => window.clearTimeout(t);
  }, [q, project, serverVersion]);
  const go = (h: SearchHit) => {
    const u = uidOf(net, h.element, h.id);
    if (u) focus([u]);
    setOpen(false);
  };
  return (
    <div className="quick-search">
      <input value={q} placeholder="Buscar ID, nombre, dirección, medidor…" aria-label="Búsqueda rápida"
        onChange={(e) => { setQ(e.target.value); setOpen(true); }} onFocus={() => setOpen(true)}
        onKeyDown={(e) => { if (e.key === "Enter" && hits[0]) go(hits[0]); if (e.key === "Escape") setOpen(false); }} />
      {open && hits.length > 0 && (
        <ul className="qs-results" role="listbox">
          {hits.slice(0, 12).map((h) => (
            <li key={`${h.element}-${h.id}`} role="option" aria-selected={false} onMouseDown={() => go(h)}>
              <span className="mono">{h.id}</span> <span className="muted">{ELEMENT[h.element] ?? h.element}</span>
              {h.match !== "ID" && <span className="qs-text"> · {h.match}: {h.text}</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
