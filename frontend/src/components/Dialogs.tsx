import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { ReviewOut, VersionOut } from "../api/types";
import { canReview, useAuth } from "../state/auth";
import { fmtDate } from "../lib/format";
import { errorText, openProject } from "../state/projects";
import { removeElements, useEditor } from "../state/store";
import { Icon } from "./Icons";

export function Modal({ title, onClose, children, wide }: { title: string; onClose: () => void; children: React.ReactNode; wide?: boolean }) {
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  return (
    <div className="modal-back" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className={`modal ${wide ? "wide" : ""}`} role="dialog" aria-modal="true" aria-label={title}>
        <header><h2>{title}</h2><button className="ghost" onClick={onClose} aria-label="Cerrar"><Icon.close /></button></header>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  );
}

export function ConfirmDelete() {
  const { pendingDelete, net, confirmDelete, cancelDelete } = useEditor();
  if (!pendingDelete) return null;
  const nodes = pendingDelete.filter((u) => net.nodes[u]).map((u) => net.nodes[u].id);
  const links = pendingDelete.filter((u) => net.links[u]).map((u) => net.links[u].id);
  const after = removeElements(net, pendingDelete);
  const cascade = Object.keys(net.links).length - Object.keys(after.links).length - links.length;
  const clients = pendingDelete.filter((u) => net.clients[u]).map((u) => net.clients[u].id);
  const shutoffs = pendingDelete.filter((u) => net.shutoffs[u]).map((u) => net.shutoffs[u].id);
  const lostClients = Object.keys(net.clients).length - Object.keys(after.clients).length - clients.length;
  const lostShutoffs = Object.keys(net.shutoffs).length - Object.keys(after.shutoffs).length - shutoffs.length;
  return (
    <Modal title="Confirmar eliminación" onClose={cancelDelete}>
      <p>
        Se eliminarán {nodes.length > 0 && <>los nudos <strong>{nodes.slice(0, 8).join(", ")}{nodes.length > 8 ? "…" : ""}</strong></>}
        {nodes.length > 0 && links.length > 0 && " y "}
        {links.length > 0 && <>los tramos <strong>{links.slice(0, 8).join(", ")}{links.length > 8 ? "…" : ""}</strong></>}.
      </p>
      {(clients.length > 0 || shutoffs.length > 0) && <p>Elementos: <strong>{[...clients, ...shutoffs].slice(0, 10).join(", ")}</strong>.</p>}
      {cascade > 0 && <p className="warn-text">También se eliminarán {cascade} tramos conectados a esos nudos.</p>}
      {lostClients > 0 && <p className="warn-text">También se eliminarán {lostClients} clientes conectados.</p>}
      {lostShutoffs > 0 && <p className="warn-text">También se eliminarán {lostShutoffs} llaves de corte de esos tramos.</p>}
      <p className="muted">Puede deshacer la acción con Ctrl+Z.</p>
      <div className="modal-actions">
        <button className="ghost" onClick={cancelDelete}>Cancelar</button>
        <button className="danger" autoFocus onClick={confirmDelete}>Eliminar</button>
      </div>
    </Modal>
  );
}

export function VersionsDialog() {
  const [reviewing, setReviewing] = useState<number | null>(null);
  const readOnly = useEditor((x) => x.readOnly);
  const { versionsOpen, project, serverVersion, set, toast } = useEditor();
  const [list, setList] = useState<VersionOut[] | null>(null);
  const [showAuto, setShowAuto] = useState(false);
  useEffect(() => {
    if (versionsOpen && project) api.listVersions(project.id).then(setList).catch(() => setList([]));
  }, [versionsOpen, project, serverVersion]);
  if (!versionsOpen || !project) return null;
  const close = () => set({ versionsOpen: false });
  const rows = (list ?? []).filter((v) => showAuto || v.kind !== "auto" || v.number === serverVersion);

  const restore = async (v: VersionOut) => {
    const st = useEditor.getState();
    if (st.revision !== st.savedRevision) return toast("Espere a que termine el guardado automático.", "error");
    try {
      const doc = await api.getNetwork(project.id, v.number);
      const res = await api.saveNetwork(project.id, {
        base_version: st.serverVersion, kind: "manual", label: `Restaurada desde v${v.number}`,
        options: doc.options, aux: doc.aux, network: doc.network,
      });
      await openProject(project.id, res.version);
      toast(`Versión ${v.number} restaurada como v${res.version}.`);
      close();
    } catch (e) {
      toast(errorText(e), "error");
    }
  };

  return (
    <Modal title={`Versiones de «${project.name}»`} onClose={close} wide>
      <label className="inline"><input type="checkbox" checked={showAuto} onChange={(e) => setShowAuto(e.target.checked)} /> Mostrar guardados automáticos</label>
      <p className="muted">Cada guardado crea una versión inmutable; las simulaciones quedan ligadas a la versión que las generó.</p>
      <table className="tbl">
        <thead><tr><th>Versión</th><th>Tipo</th><th>Etiqueta</th><th>Fecha</th><th>Nudos</th><th>Tramos</th><th>Resultados</th><th /></tr></thead>
        <tbody>
          {rows.map((v) => (
            <tr key={v.number} className={v.number === serverVersion ? "current" : ""}>
              <td>v{v.number}</td>
              <td>{{ auto: "automático", manual: "manual", import: "importación" }[v.kind]}</td>
              <td>{v.label ?? ""}</td>
              <td>{fmtDate(v.created_at)}</td>
              <td className="num">{v.node_count}</td>
              <td className="num">{v.link_count}</td>
              <td>{v.has_results ? "sí" : "—"}</td>
              <td className="right">
                <a className="btn ghost small" href={api.exportUrl(project.id, v.number)}>.inp</a>
                <button className="ghost small" onClick={() => setReviewing(reviewing === v.number ? null : v.number)}>Revisión</button>
                {v.number !== serverVersion && !readOnly && <button className="ghost small" onClick={() => void restore(v)}>Restaurar</button>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {reviewing !== null && <Reviews projectId={project.id} version={reviewing} />}
    </Modal>
  );
}

/** Comentarios y aprobaciones de una versión (revisor o administrador). */
function Reviews({ projectId, version }: { projectId: string; version: number }) {
  const { project, toast } = useEditor();
  const role = useAuth((s) => s.roleIn(project?.org_id));
  const [list, setList] = useState<ReviewOut[]>([]);
  const [comment, setComment] = useState("");
  useEffect(() => { api.reviews(projectId, version).then(setList).catch(() => setList([])); }, [projectId, version]);
  const add = async (status: "comentario" | "aprobada" | "observada") => {
    try { await api.addReview(projectId, version, status, comment); setComment(""); setList(await api.reviews(projectId, version)); }
    catch (e) { toast(errorText(e), "error"); }
  };
  return (
    <section className="reviews">
      <h3>Revisión de la versión {version}</h3>
      {list.length === 0 ? <p className="muted small">Sin comentarios.</p> : (
        <ul className="diag-list">{list.map((r) => (
          <li key={r.id} className={r.status === "aprobada" ? "ok" : r.status === "observada" ? "problem" : ""}>
            <b>{{ aprobada: "✔ Aprobada", observada: "▲ Observada", comentario: "💬" }[r.status] ?? r.status}</b> {r.comment}
            <span className="muted small"> — {r.user_email} · {fmtDate(r.created_at)}</span></li>))}</ul>
      )}
      {canReview(role) && (
        <div className="toolbar wrap">
          <input value={comment} onChange={(e) => setComment(e.target.value)} placeholder="Comentario" aria-label="Comentario" style={{ flex: 1 }} />
          <button className="small" onClick={() => void add("comentario")}>Comentar</button>
          <button className="small primary" onClick={() => void add("aprobada")}>Aprobar</button>
          <button className="small" onClick={() => void add("observada")}>Observar</button>
        </div>
      )}
    </section>
  );
}

export function Toasts() {
  const { toasts, dismissToast } = useEditor();
  return (
    <div className="toasts" aria-live="polite">
      {toasts.map((t) => <div key={t.id} className={`toast ${t.kind}`} onClick={() => dismissToast(t.id)}>{t.text}</div>)}
    </div>
  );
}
