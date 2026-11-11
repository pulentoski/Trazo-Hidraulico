// Piezas comunes de Ajustes: marco de sección (título, descripción y acciones) y botón Guardar con confirmación.
import type { ReactNode } from "react";
import { useEffect, useRef, useState } from "react";
import { errorText } from "../../state/projects";
import { useEditor } from "../../state/store";

export function Panel({ title, description, children, id }: { title: string; description: string; children: ReactNode; id?: string }) {
  return (
    <section className="ajustes-panel" aria-labelledby={id ? `${id}-t` : undefined} data-panel={id}>
      <header>
        <h2 id={id ? `${id}-t` : undefined}>{title}</h2>
        <p className="muted">{description}</p>
      </header>
      {children}
    </section>
  );
}

/** Botón Guardar: deshabilitado sin cambios; tras guardar muestra «Guardado» unos segundos. */
export function SaveButton({ dirty, onSave, label = "Guardar" }: { dirty: boolean; onSave: () => Promise<unknown>; label?: string }) {
  const [state, setState] = useState<"idle" | "saving" | "saved">("idle");
  const toast = useEditor((s) => s.toast);
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => () => window.clearTimeout(timer.current), []);
  useEffect(() => { if (dirty && state === "saved") setState("idle"); }, [dirty, state]);
  const click = async () => {
    setState("saving");
    try {
      await onSave();
      setState("saved");
      window.clearTimeout(timer.current);
      timer.current = window.setTimeout(() => setState("idle"), 3000);
    } catch (e) {
      setState("idle");
      toast(errorText(e), "error");
    }
  };
  return (
    <div className="save-bar">
      <button type="button" className="primary" disabled={!dirty || state === "saving"} onClick={() => void click()}>
        {state === "saving" ? "Guardando…" : label}</button>
      {state === "saved" && <span className="saved" role="status">✓ Guardado</span>}
    </div>
  );
}
