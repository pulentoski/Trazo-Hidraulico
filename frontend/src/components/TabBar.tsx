// Barra de pestañas sin desplazamiento horizontal: las pestañas que no caben (las últimas, menos usadas) pasan a
// un menú «Más». Los anchos se miden con una copia oculta de los botones.
import type { ReactNode } from "react";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Icon } from "./Icons";

export interface TabDef { id: string; label: string; count?: number; countCls?: string }

function TabLabel({ t }: { t: TabDef }) {
  return <>{t.label}{t.count !== undefined && <> <span className={`count ${t.countCls ?? ""}`}>{t.count}</span></>}</>;
}

export function TabBar({ tabs, active, onPick, controls }: { tabs: TabDef[]; active: string; onPick: (id: string) => void; controls?: ReactNode }) {
  const barRef = useRef<HTMLDivElement>(null);
  const measureRef = useRef<HTMLDivElement>(null);
  const ctlRef = useRef<HTMLDivElement>(null);
  const [fit, setFit] = useState(tabs.length);
  const [open, setOpen] = useState(false);
  const sig = tabs.map((t) => `${t.label}${t.count ?? ""}`).join("|") + active;
  const activeRef = useRef(active);
  activeRef.current = active;

  useLayoutEffect(() => {
    const compute = () => {
      const bar = barRef.current;
      const m = measureRef.current;
      if (!bar || !m) return;
      const widths = Array.from(m.children).map((c) => (c as HTMLElement).getBoundingClientRect().width + 2);
      const moreLong = widths.pop() ?? 150;
      const morePlain = widths.pop() ?? 70;
      const avail = bar.clientWidth - (ctlRef.current?.getBoundingClientRect().width ?? 0) - 12;
      const count = (more: number) => {
        let used = 0;
        let n = 0;
        for (let i = 0; i < widths.length; i++) {
          const rest = i < widths.length - 1 ? more : 0;  // si quedan pestañas, hace falta lugar para «Más»
          if (used + widths[i] + rest > avail) break;
          used += widths[i];
          n++;
        }
        return n;
      };
      let n = count(morePlain);
      const idx = tabs.findIndex((t) => t.id === activeRef.current);
      if (n < tabs.length && idx >= n) n = count(moreLong);  // la activa va en «Más: …»
      setFit(Math.max(1, n));
    };
    compute();
    const ro = new ResizeObserver(compute);
    if (barRef.current) ro.observe(barRef.current);
    return () => ro.disconnect();
  }, [sig]);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => { if (!(e.target as Element).closest?.(".tabs-more-wrap")) setOpen(false); };
    const key = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("mousedown", close);
    window.addEventListener("keydown", key);
    return () => { window.removeEventListener("mousedown", close); window.removeEventListener("keydown", key); };
  }, [open]);

  const shown = tabs.slice(0, fit);
  const hidden = tabs.slice(fit);
  const activeHidden = hidden.find((t) => t.id === active);
  return (
    <>
      <div className="tabs" ref={barRef} role="tablist" aria-label="Pestañas del panel inferior">
        {shown.map((t) => (
          <button key={t.id} role="tab" aria-selected={active === t.id} className={active === t.id ? "on" : ""} onClick={() => onPick(t.id)}>
            <TabLabel t={t} />
          </button>
        ))}
        {hidden.length > 0 && (
          <div className="tabs-more-wrap">
            <button className={`tabs-more ${activeHidden ? "on" : ""}`} aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(!open)}
              title="Más pestañas">{activeHidden ? <>Más: <TabLabel t={activeHidden} /></> : "Más"} <Icon.chevronDown /></button>
            {open && (
              <div className="menu-pop tabs-more-pop" role="menu">
                {hidden.map((t) => (
                  <button key={t.id} role="menuitem" className={`menu-item ${active === t.id ? "on" : ""}`} onClick={() => { onPick(t.id); setOpen(false); }}>
                    <TabLabel t={t} />
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
        <div className="tabs-spacer" />
        <div ref={ctlRef} className="tabs-controls">{controls}</div>
      </div>
      <div className="tabs-measure" ref={measureRef} aria-hidden="true">
        {tabs.map((t) => <button key={t.id} tabIndex={-1}><TabLabel t={t} /></button>)}
        <button tabIndex={-1}>Más <Icon.chevronDown /></button>
        <button tabIndex={-1}>Más: Mediciones <Icon.chevronDown /></button>
      </div>
    </>
  );
}
