import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router";
import { api } from "../api/client";
import { fmt, fmtDate } from "../lib/format";
import { PATHS } from "../paths";
import { flushPending, saveNow, simulateNow } from "../state/live";
import { useEditor, writePref } from "../state/store";
import { Modal } from "./Dialogs";
import { Icon } from "./Icons";
import { Brand } from "./PageHeader";
import { UserMenu } from "./UserMenu";

const STATUS: Record<string, { label: string; cls: string }> = {
  idle: { label: "Sin cambios", cls: "idle" },
  pending: { label: "Calculando…", cls: "busy" },
  running: { label: "Calculando…", cls: "busy" },
  ok: { label: "Actualizado", cls: "ok" },
  error: { label: "Error", cls: "error" },
};

/** Detalle del último error o de la última corrida (se abre al hacer clic en el indicador de estado). */
function StatusDetail({ onClose }: { onClose: () => void }) {
  const { simStatus, simError, result, validation, serverVersion, revision, savedRevision, focus, net } = useEditor();
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const down = (e: MouseEvent) => { if (ref.current && !ref.current.closest(".status-wrap")?.contains(e.target as Node)) onClose(); };
    const key = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("mousedown", down);
    window.addEventListener("keydown", key);
    return () => { window.removeEventListener("mousedown", down); window.removeEventListener("keydown", key); };
  }, [onClose]);
  const uidOf = (type: string | null | undefined, id: string | null | undefined) => {
    if (!id) return null;
    const pool = type === "link" ? Object.values(net.links) : Object.values(net.nodes);
    return pool.find((e) => e.id === id)?.uid ?? null;
  };
  const errors = validation?.errors ?? [];
  const engineErrors = (result?.messages ?? []).filter((m) => m.severity === "error");
  return (
    <div className="popover status-detail" ref={ref} role="dialog" aria-label="Detalle del cálculo">
      {simStatus === "error" ? (<>
        <h4 className="bad-text">Error en el último cálculo</h4>
        {simError && <p>{simError}</p>}
        {[...errors.map((e) => ({ m: e.message, t: e.element_type, id: e.element_id })),
          ...engineErrors.map((e) => ({ m: e.message, t: e.element_type, id: e.element_id }))].slice(0, 12).map((e, i) => {
          const uid = uidOf(e.t, e.id);
          return <p key={i} className="issue-line">{e.m} {uid && <button className="link" onClick={() => { focus([uid]); onClose(); }}>ver</button>}</p>;
        })}
        {errors.length + engineErrors.length > 12 && <p className="muted small">… y {errors.length + engineErrors.length - 12} más (pestaña Validación).</p>}
      </>) : simStatus === "pending" || simStatus === "running" ? (
        <p>Guardando la versión y calculando con OWA-EPANET…</p>
      ) : result ? (<>
        <h4>Última corrida</h4>
        <dl className="kv compact">
          <dt>Versión del modelo</dt><dd>v{result.model_version}{result.model_version !== serverVersion ? " (anterior)" : ""}</dd>
          <dt>Estado</dt><dd>{{ ok: "correcta", warning: "con advertencias", error: "con errores" }[result.status] ?? result.status}</dd>
          <dt>Origen</dt><dd>{result.cached ? "reutilizada (misma versión ya calculada)" : "calculada ahora"}</dd>
          <dt>Fecha</dt><dd>{fmtDate(result.created_at)}</dd>
          <dt>Tiempo del motor</dt><dd>{fmt(result.elapsed_ms, 0)} ms</dd>
          <dt>Periodos</dt><dd>{result.times.length}</dd>
          <dt>Mensajes del motor</dt><dd>{result.messages.length}</dd>
          <dt>Alertas de criterios</dt><dd>{result.alerts.length}</dd>
          <dt>Motor</dt><dd>OWA-EPANET {result.engine.wheel_version}</dd>
          <dt>Corrida</dt><dd className="mono small">{result.run_id.slice(0, 8)}</dd>
        </dl>
        {result.messages.slice(0, 5).map((m, i) => <p key={i} className={`issue-line ${m.severity}`}>{m.message}</p>)}
        {revision !== savedRevision && <p className="muted small">Hay cambios aún no guardados.</p>}
      </>) : <p className="muted">Aún no hay corridas en esta sesión.</p>}
    </div>
  );
}

function SigMenu({ dirty }: { dirty: boolean }) {
  const s = useEditor();
  const [open, setOpen] = useState(false);
  const pid = s.project?.id;
  if (!pid) return null;
  const item = (href: string, text: string, title: string) => (
    <a className={`menu-item ${dirty ? "disabled" : ""}`} href={href} title={title} onClick={() => setOpen(false)}>{text}</a>
  );
  return (
    <div className="menu-wrap">
      <button onClick={() => setOpen(!open)} aria-expanded={open} aria-label="Planilla y SIG" title="Planillas Excel y exportaciones SIG/CAD"><Icon.table /><span>Planilla y SIG ▾</span></button>
      {open && (
        <div className="menu-pop" onMouseLeave={() => setOpen(false)}>
          <button className="menu-item" onClick={() => { setOpen(false); s.set({ importOpen: true }); }}>Importar Excel o CSV…</button>
          {item(api.excelUrl(pid), "Exportar Excel (planilla completa)", "Misma estructura de la plantilla: se puede editar y volver a importar")}
          {item(api.templateUrl, "Descargar plantilla vacía", "Una hoja por tipo de elemento, con instrucciones y listas")}
          {item(api.reportUrl(pid), "Informe técnico (HTML imprimible)", "Proyecto, criterios, resultados, gráficos y diagnóstico")}
          {item(api.trazoUrl(pid), "Exportar proyecto .trazo", "Zip con el .inp y todos los datos propios (clientes, llaves, escenarios, atributos…)")}
          {item(api.dxfUrl(pid), "Exportar DXF (UTM, por capas)", "Red por diámetro, válvulas, clientes, estanques…")}
          {item(api.gpkgUrl(pid), "Exportar GeoPackage (QGIS)", "Una capa por tipo de elemento, más los cuarteles de corta")}
          {dirty && <p className="muted small pad">Esperando el guardado de los cambios…</p>}
        </div>
      )}
    </div>
  );
}

export function TopBar() {
  const s = useEditor();
  const navigate = useNavigate();
  const [saveOpen, setSaveOpen] = useState(false);
  const [detail, setDetail] = useState(false);
  const [leaving, setLeaving] = useState(false);
  const [label, setLabel] = useState("");
  const st = STATUS[s.simStatus];
  const dirty = s.revision !== s.savedRevision;
  const time = s.lastSavedAt ? new Date(s.lastSavedAt).toLocaleTimeString("es-CL", { hour: "2-digit", minute: "2-digit" }) : "";
  const toggleTheme = () => {
    const theme = s.theme === "dark" ? "light" : "dark";
    s.set({ themePref: theme, theme });
    writePref("theme", theme);
  };
  const back = async () => {
    setLeaving(true);
    const ok = await flushPending();
    setLeaving(false);
    if (ok) navigate(PATHS.home);
    else s.toast("No se pudieron guardar los últimos cambios; revise el estado antes de salir.", "error");
  };

  return (
    <header className="topbar">
      <button className="ghost back-btn" onClick={() => void back()} disabled={leaving} title="Volver al menú principal (guarda los cambios pendientes)">
        <Icon.back /><span>{leaving ? "Guardando…" : "Menú"}</span>
      </button>
      <Brand />
      <div className="project-name" title={s.project?.name ?? ""}>{s.project?.name ?? "…"}</div>
      <div className="tb-group">
        <button onClick={() => { setLabel(""); setSaveOpen(true); }} disabled={!s.project} title="Guardar versión con nombre (Ctrl+S)"><Icon.save /><span>Guardar</span></button>
        <button onClick={s.undo} disabled={!s.past.length} title="Deshacer (Ctrl+Z)"><Icon.undo /></button>
        <button onClick={s.redo} disabled={!s.future.length} title="Rehacer (Ctrl+Y)"><Icon.redo /></button>
      </div>
      <div className="tb-group">
        <button className="primary" onClick={simulateNow} disabled={!s.project} title="Simular ahora (F5)"><Icon.play /><span>Simular</span></button>
        <a className={`btn ${!s.project || dirty ? "disabled" : ""}`} href={s.project ? api.exportUrl(s.project.id, s.serverVersion ?? undefined) : undefined}
          aria-disabled={!s.project || dirty} title={dirty ? "Esperando guardado" : "Exportar la versión actual como .inp"}><Icon.download /><span>Exportar .inp</span></a>
        <SigMenu dirty={dirty} />
      </div>
      <div className="tb-spacer" />
      <div className="status-wrap">
        <button className={`status ${st.cls}`} onClick={() => setDetail(!detail)} aria-expanded={detail} title="Ver detalle del cálculo">
          <i />{st.label}
        </button>
        {detail && <StatusDetail onClose={() => setDetail(false)} />}
      </div>
      <div className="version-info" title="Cada guardado crea una versión inmutable">
        {s.serverVersion !== null && <>v{s.serverVersion} · {dirty ? "cambios sin guardar" : `${s.lastSaveKind === "manual" ? "guardado" : "autoguardado"} ${time}`}</>}
      </div>
      <button className="ghost" onClick={() => s.set({ versionsOpen: true })} disabled={!s.project} title="Versiones del modelo"><Icon.history /></button>
      {s.readOnly && <span className="badge warn" title="Su rol en esta organización no permite editar">solo lectura</span>}
      <UserMenu />
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
