// Sección plegable (acordeón) de un panel: encabezado clicable con flecha y apertura animada.
import type { ReactNode } from "react";
import { useEffect } from "react";
import { allOpen, useSections } from "../state/sections";
import { Icon } from "./Icons";

export function Section({ id, title, extra, primary = false, className = "", children }: {
  /** Identificador estable («ámbito.sección»): el estado se recuerda por usuario. */
  id: string; title: ReactNode; extra?: ReactNode;
  /** Abierta por defecto (la sección más usada del panel). */
  primary?: boolean; className?: string; children: ReactNode;
}) {
  const open = useSections((s) => s.open[id] ?? primary);
  const toggle = useSections((s) => s.toggle);
  const mount = useSections((s) => s.mount);
  const unmount = useSections((s) => s.unmount);
  useEffect(() => {
    mount(id, primary);
    return () => unmount(id);
  }, [id, primary, mount, unmount]);
  const bodyId = `sec-${id.replace(/[^\w-]/g, "_")}`;
  return (
    <section className={`sec ${open ? "open" : ""} ${className}`} data-section={id}>
      <div className="sec-head">
        <button type="button" className="sec-toggle" aria-expanded={open} aria-controls={bodyId} onClick={() => toggle(id, primary)}>
          <span className="sec-arrow"><Icon.chevronRight /></span>
          <span>{title}</span>
        </button>
        {extra}
      </div>
      <div className="sec-body" id={bodyId} role="region" inert={!open}>
        <div className="sec-inner">{children}</div>
      </div>
    </section>
  );
}

/** Botón «Expandir todo / Contraer todo» para las secciones visibles del panel. */
export function ExpandAll() {
  const all = useSections(allOpen);
  const any = useSections((s) => Object.keys(s.mounted).length > 0);
  const setAll = useSections((s) => s.setAll);
  if (!any) return null;
  return (
    <button type="button" className="ghost small expand-all" onClick={() => setAll(!all)} title={all ? "Contraer todas las secciones" : "Expandir todas las secciones"}>
      {all ? "Contraer todo" : "Expandir todo"}
    </button>
  );
}
