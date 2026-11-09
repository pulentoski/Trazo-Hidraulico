// Control «Etiquetas» de la barra del mapa (separado de la simbología de la leyenda).
import { useEffect, useRef, useState } from "react";
import type { Labels } from "../state/store";
import { useEditor, writePref } from "../state/store";
import { Icon } from "./Icons";

const GROUPS: { title: string; items: { key: keyof Labels; label: string }[] }[] = [
  { title: "Nudos", items: [{ key: "nodeIds", label: "ID" }, { key: "pressure", label: "Presión (m)" }] },
  { title: "Tramos", items: [
    { key: "linkIds", label: "ID" }, { key: "dn", label: "DN" }, { key: "length", label: "Largo hidráulico" },
    { key: "flow", label: "Caudal (L/s)" }, { key: "velocity", label: "Velocidad (m/s)" }, { key: "headloss", label: "Pérdida unitaria (m/km)" },
  ] },
];

export function LabelsControl() {
  const { labels, set } = useEditor();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const active = Object.values(labels).filter(Boolean).length;
  useEffect(() => {
    if (!open) return;
    const down = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false); };
    const key = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("mousedown", down);
    window.addEventListener("keydown", key);
    return () => { window.removeEventListener("mousedown", down); window.removeEventListener("keydown", key); };
  }, [open]);
  const toggle = (k: keyof Labels, v: boolean) => {
    const next = { ...labels, [k]: v };
    set({ labels: next });
    writePref("labels", next);
  };
  return (
    <div className="labels-ctl" ref={ref}>
      <button className={`map-btn ${open ? "on" : ""}`} onClick={() => setOpen(!open)} aria-expanded={open} title="Etiquetas en el mapa">
        <Icon.tag /><span>Etiquetas</span>{active > 0 && <span className="count">{active}</span>}
      </button>
      {open && (
        <div className="popover labels-pop" role="dialog" aria-label="Etiquetas">
          {GROUPS.map((g) => (
            <fieldset key={g.title}>
              <legend>{g.title}</legend>
              {g.items.map((o) => (
                <label key={o.key} className="check"><input type="checkbox" checked={labels[o.key]} onChange={(e) => toggle(o.key, e.target.checked)} />{o.label}</label>
              ))}
            </fieldset>
          ))}
          <p className="muted small">Presión, caudal, velocidad y pérdida requieren resultados.</p>
        </div>
      )}
    </div>
  );
}
