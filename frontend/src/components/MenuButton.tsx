// Menú desplegable que se dibuja en una capa propia (portal en <body>, posición fija y z-index sobre el mapa y los
// paneles): no lo recortan los contenedores con overflow y se reubica para no salirse de la ventana (abre hacia
// arriba o se alinea a la derecha si no cabe, con alto máximo y desplazamiento interno).
import type { ReactNode } from "react";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

export interface PlaceInput { trigger: { left: number; right: number; top: number; bottom: number }; menu: { width: number; height: number };
  viewport: { width: number; height: number }; margin?: number; align?: "left" | "right" }
export interface Placement { left: number; top: number; maxHeight: number; up: boolean }

/** Posición del menú dentro de la ventana (pura, probada en lib). */
export function placeMenu({ trigger, menu, viewport, margin = 8, align = "left" }: PlaceInput): Placement {
  const below = viewport.height - trigger.bottom - margin;
  const above = trigger.top - margin;
  const up = menu.height > below && above > below;
  const maxHeight = Math.max(120, (up ? above : below) - 4);
  const h = Math.min(menu.height, maxHeight);
  let left = align === "right" ? trigger.right - menu.width : trigger.left;
  left = Math.min(left, viewport.width - menu.width - margin);
  left = Math.max(margin, left);
  const top = up ? Math.max(margin, trigger.top - 4 - h) : trigger.bottom + 4;
  return { left, top, maxHeight, up };
}

export function MenuButton({ label, title, buttonClass, children, align = "left", menuClass, menuLabel, ariaLabel }: {
  label: ReactNode; title?: string; buttonClass?: string; align?: "left" | "right"; menuClass?: string; menuLabel: string; ariaLabel?: string;
  children: (close: () => void) => ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<Placement | null>(null);
  const btn = useRef<HTMLButtonElement>(null);
  const pop = useRef<HTMLDivElement>(null);
  const close = useCallback(() => setOpen(false), []);
  const place = useCallback(() => {
    if (!btn.current || !pop.current) return;
    const t = btn.current.getBoundingClientRect();
    pop.current.style.maxHeight = "none";
    const m = pop.current.getBoundingClientRect();
    setPos(placeMenu({ trigger: t, menu: { width: m.width, height: pop.current.scrollHeight }, viewport: { width: window.innerWidth, height: window.innerHeight }, align }));
  }, [align]);
  useLayoutEffect(() => { if (open) place(); else setPos(null); }, [open, place]);
  useEffect(() => {
    if (!open) return;
    const down = (e: MouseEvent) => {
      const t = e.target as Node;
      if (!pop.current?.contains(t) && !btn.current?.contains(t)) setOpen(false);
    };
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") { setOpen(false); btn.current?.focus(); } };
    window.addEventListener("mousedown", down);
    window.addEventListener("keydown", key);
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    return () => {
      window.removeEventListener("mousedown", down);
      window.removeEventListener("keydown", key);
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
    };
  }, [open, place]);
  return (
    <>
      <button ref={btn} type="button" className={buttonClass} onClick={() => setOpen(!open)} aria-expanded={open} aria-haspopup="menu" title={title} aria-label={ariaLabel}>
        {label}
      </button>
      {open && createPortal(
        <div ref={pop} className={`menu-pop floating ${pos?.up ? "up" : ""} ${menuClass ?? ""}`} role="menu" aria-label={menuLabel}
          style={{ position: "fixed", left: pos?.left ?? -9999, top: pos?.top ?? -9999, maxHeight: pos?.maxHeight, visibility: pos ? "visible" : "hidden" }}>
          {children(close)}
        </div>, document.body)}
    </>
  );
}
