// Escena ilustrada animada (ingreso e inicio, docs/referencias/estilo/): dibujo SVG estático de la maqueta, avisos
// al pasar el mouse por los elementos con data-tip y nubes que se apartan del puntero. Se puede pausar; sin
// movimiento con «Animaciones» desactivado o prefers-reduced-motion. Es decorativa (aria-hidden): los avisos repiten
// información de contexto, no datos del sistema.
import { useEffect, useRef, useState } from "react";
import { animationsOn } from "../state/store";

export function Scene({ svg, viewBox, className, paused, preserve = "xMidYMax slice", onHover }: {
  svg: string; viewBox: string; className?: string; paused?: boolean; preserve?: string; onHover?: (title: string | null) => void;
}) {
  const ref = useRef<SVGSVGElement>(null);
  const [tip, setTip] = useState<{ t: string; d: string; x: number; y: number } | null>(null);
  const hover = useRef(onHover);
  hover.current = onHover;

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    let cur: Element | null = null;
    const place = (e: PointerEvent, t: string, d: string) => setTip({ t, d, x: e.clientX, y: e.clientY });
    const over = (e: PointerEvent) => {
      const hit = (e.target as Element).closest?.("[data-tip]");
      if (!hit || hit === cur) return;
      cur = hit;
      const [t, d = ""] = (hit.getAttribute("data-tip") ?? "").split("|");
      place(e, t, d);
      hover.current?.(t);
    };
    const move = (e: PointerEvent) => {
      if (!cur) return;
      const [t, d = ""] = (cur.getAttribute("data-tip") ?? "").split("|");
      place(e, t, d);
    };
    const out = (e: PointerEvent) => {
      const to = (e.relatedTarget as Element | null)?.closest?.("[data-tip]");
      if (to === cur) return;
      cur = null;
      setTip(null);
      hover.current?.(null);
    };
    el.addEventListener("pointerover", over);
    el.addEventListener("pointermove", move);
    el.addEventListener("pointerout", out);
    return () => { el.removeEventListener("pointerover", over); el.removeEventListener("pointermove", move); el.removeEventListener("pointerout", out); };
  }, [svg]);

  // Nubes que se apartan del puntero (resorte amortiguado). Sin animaciones o en pausa, quietas.
  useEffect(() => {
    const el = ref.current;
    if (!el || paused || !animationsOn() || window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
    const clouds = [...el.querySelectorAll<SVGGElement>(".cw")].map((g) => ({ g, x: Number(g.dataset.x), y: Number(g.dataset.y), px: 0, py: 0, vx: 0, vy: 0 }));
    if (!clouds.length) return;
    let m: DOMPoint | null = null;
    const toSvg = (e: PointerEvent) => {
      const ctm = el.getScreenCTM();
      if (!ctm) return null;
      return new DOMPoint(e.clientX, e.clientY).matrixTransform(ctm.inverse());
    };
    const mv = (e: PointerEvent) => { m = toSvg(e); };
    const leave = () => { m = null; };
    document.addEventListener("pointermove", mv, { passive: true });
    document.addEventListener("mouseleave", leave);
    let raf = 0;
    const R = 170, PUSH = 130;
    const tick = () => {
      for (const c of clouds) {
        let tx = 0, ty = 0;
        if (m) {
          const dx = c.x - m.x, dy = c.y - m.y, d = Math.hypot(dx, dy);
          if (d < R) { const f = (1 - d / R) ** 0.7; tx = (d > 1 ? dx / d : 1) * f * PUSH; ty = (d > 1 ? dy / d : -0.3) * f * PUSH * 0.25; }
        }
        c.vx = (c.vx + (tx - c.px) * 0.08) * 0.85;
        c.vy = (c.vy + (ty - c.py) * 0.08) * 0.85;
        c.px += c.vx;
        c.py += c.vy;
        c.g.setAttribute("transform", `translate(${c.px.toFixed(2)} ${c.py.toFixed(2)})`);
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => { cancelAnimationFrame(raf); document.removeEventListener("pointermove", mv); document.removeEventListener("mouseleave", leave); };
  }, [paused, svg]);

  const w = typeof window === "undefined" ? 1200 : window.innerWidth;
  const left = tip ? (tip.x + 264 > w - 8 ? tip.x - 264 : tip.x + 14) : 0;
  const top = tip ? Math.max(8, tip.y - 70) : 0;
  return (
    <>
      <svg ref={ref} className={`th-scene ${paused ? "paused" : ""} ${className ?? ""}`} viewBox={viewBox} preserveAspectRatio={preserve}
        xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false" dangerouslySetInnerHTML={{ __html: svg }} />
      {tip && <div className="scene-tip" role="tooltip" style={{ left, top }}><b>{tip.t}</b><span>{tip.d}</span></div>}
    </>
  );
}
