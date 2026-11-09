import { useState } from "react";
import { api } from "../api/client";
import { saveNow, simulateNow } from "../state/live";
import { useEditor, writePref } from "../state/store";
import { Modal } from "./Dialogs";
import { Icon } from "./Icons";

const STATUS: Record<string, { label: string; cls: string }> = {
  idle: { label: "Sin cambios", cls: "idle" },
  pending: { label: "Calculando…", cls: "busy" },
  running: { label: "Calculando…", cls: "busy" },
  ok: { label: "Actualizado", cls: "ok" },
  error: { label: "Error", cls: "error" },
};

export function TopBar() {
  const s = useEditor();
  const [saveOpen, setSaveOpen] = useState(false);
  const [label, setLabel] = useState("");
  const st = STATUS[s.simStatus];
  const dirty = s.revision !== s.savedRevision;
  const time = s.lastSavedAt ? new Date(s.lastSavedAt).toLocaleTimeString("es-CL", { hour: "2-digit", minute: "2-digit" }) : "";
  const toggleTheme = () => {
    const theme = s.theme === "dark" ? "light" : "dark";
    s.set({ theme });
    writePref("theme", theme);
  };

  return (
    <header className="topbar">
      <div className="brand" title="Trazo Hidráulico — diseño y simulación de redes de agua potable">
        <svg viewBox="0 0 32 32" aria-hidden><path d="M5 23 L13 12 L19 18 L27 7" /><circle cx="5" cy="23" r="2.6" /><circle cx="13" cy="12" r="2.6" /><circle cx="19" cy="18" r="2.6" /><circle cx="27" cy="7" r="2.6" /></svg>
        <span>Trazo Hidráulico</span>
      </div>
      <button className="project-btn" onClick={() => s.set({ projectsOpen: true })} title="Abrir, crear o importar proyectos">
        <Icon.folder /> <span>{s.project?.name ?? "Sin proyecto"}</span>
      </button>
      <div className="tb-group">
        <button onClick={() => { setLabel(""); setSaveOpen(true); }} disabled={!s.project} title="Guardar versión con nombre (Ctrl+S)"><Icon.save /><span>Guardar</span></button>
        <button onClick={s.undo} disabled={!s.past.length} title="Deshacer (Ctrl+Z)"><Icon.undo /></button>
        <button onClick={s.redo} disabled={!s.future.length} title="Rehacer (Ctrl+Y)"><Icon.redo /></button>
      </div>
      <div className="tb-group">
        <button className="primary" onClick={simulateNow} disabled={!s.project} title="Simular ahora (F5)"><Icon.play /><span>Simular</span></button>
        <a className={`btn ${!s.project || dirty ? "disabled" : ""}`} href={s.project ? api.exportUrl(s.project.id, s.serverVersion ?? undefined) : undefined}
          aria-disabled={!s.project || dirty} title={dirty ? "Esperando guardado" : "Exportar la versión actual como .inp"}><Icon.download /><span>Exportar .inp</span></a>
      </div>
      <div className="tb-spacer" />
      <div className={`status ${st.cls}`} title={s.simError ?? ""} role="status">
        <i />{st.label}
      </div>
      <div className="version-info" title="Cada guardado crea una versión inmutable">
        {s.serverVersion !== null && <>v{s.serverVersion} · {dirty ? "cambios sin guardar" : `${s.lastSaveKind === "manual" ? "guardado" : "autoguardado"} ${time}`}</>}
      </div>
      <button className="ghost" onClick={() => s.set({ versionsOpen: true })} disabled={!s.project} title="Versiones del modelo"><Icon.history /></button>
      <button className="ghost" onClick={toggleTheme} title={s.theme === "dark" ? "Tema claro" : "Tema oscuro"}>{s.theme === "dark" ? <Icon.sun /> : <Icon.moon />}</button>
      {saveOpen && (
        <Modal title="Guardar versión" onClose={() => setSaveOpen(false)}>
          <form onSubmit={(e) => { e.preventDefault(); saveNow(label.trim() || "Guardado manual"); setSaveOpen(false); }}>
            <label className="field"><span>Etiqueta</span><input autoFocus value={label} onChange={(e) => setLabel(e.target.value)} placeholder="Ej.: Alternativa DN 160 en matriz" /></label>
            <p className="muted">Además del guardado automático, esta versión queda marcada como manual en el historial.</p>
            <div className="modal-actions"><button type="button" className="ghost" onClick={() => setSaveOpen(false)}>Cancelar</button><button className="primary">Guardar</button></div>
          </form>
        </Modal>
      )}
    </header>
  );
}
