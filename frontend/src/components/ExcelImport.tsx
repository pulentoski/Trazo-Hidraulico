// Importación desde planilla (Excel o CSV por hoja): vista previa agrupada y aplicación todo o nada.
import { useRef, useState } from "react";
import { api } from "../api/client";
import type { ChangeItem, ImportPreview } from "../api/types";
import { flushPending } from "../state/live";
import { errorText, openProject } from "../state/projects";
import { useEditor } from "../state/store";
import { Modal } from "./Dialogs";

const SHEETS = ["Nudos", "Tramos", "Estanques", "Reservorios", "Válvulas", "Grifos", "Pozos", "Bombas", "Clientes"];

function val(v: unknown): string {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "number") return v.toLocaleString("es-CL", { maximumFractionDigits: 6 });
  return String(v);
}

function Group({ title, items, cls, details }: { title: string; items: ChangeItem[]; cls: string; details?: boolean }) {
  const [open, setOpen] = useState(details ?? false);
  if (!items.length) return null;
  return (
    <section className={`imp-group ${cls}`}>
      <button className="ghost small" onClick={() => setOpen(!open)}>{open ? "▾" : "▸"} {title} <span className="count">{items.length}</span></button>
      {open && (
        <table className="tbl compact">
          <thead><tr><th>Hoja</th><th>Fila</th><th>ID</th>{details && <th>Campo</th>}{details && <th>Antes</th>}{details && <th>Después</th>}</tr></thead>
          <tbody>
            {items.slice(0, 500).flatMap((it) => (details && it.changes?.length ? it.changes.map((c, k) => (
              <tr key={`${it.sheet}-${it.id}-${k}`}>
                {k === 0 ? <><td rowSpan={it.changes!.length}>{it.sheet}</td><td rowSpan={it.changes!.length} className="num">{it.row ?? ""}</td>
                  <td rowSpan={it.changes!.length} className="mono">{it.id}</td></> : null}
                <td>{c.field}</td><td className="old">{val(c.old)}</td><td className="new">{val(c.new)}</td>
              </tr>
            )) : [<tr key={`${it.sheet}-${it.id}`}><td>{it.sheet}</td><td className="num">{it.row ?? ""}</td><td className="mono">{it.id}</td></tr>]))}
          </tbody>
        </table>
      )}
    </section>
  );
}

export function PreviewView({ p }: { p: ImportPreview }) {
  return (
    <div className="imp-preview">
      <table className="tbl compact imp-summary">
        <thead><tr><th>Hoja</th><th className="num">Nuevos</th><th className="num">Modificados</th><th className="num">Sin cambios</th><th className="num">Eliminados</th><th className="num">Errores</th></tr></thead>
        <tbody>{(p.summary ?? []).map((s) => (
          <tr key={s.sheet}><td>{s.sheet}</td><td className="num">{s.new}</td><td className="num">{s.modified}</td><td className="num">{s.unchanged}</td>
            <td className="num">{s.deleted}</td><td className={`num ${s.errors ? "bad" : ""}`}>{s.errors}</td></tr>
        ))}</tbody>
      </table>
      {(p.errors ?? []).length > 0 && (
        <section className="imp-group bad">
          <h4>Errores ({p.errors!.length}) — corrija la planilla; no se aplicará nada</h4>
          <table className="tbl compact"><thead><tr><th>Hoja</th><th>Fila</th><th>ID</th><th>Motivo</th></tr></thead>
            <tbody>{p.errors!.slice(0, 500).map((e, i) => <tr key={i}><td>{e.sheet ?? ""}</td><td className="num">{e.row ?? ""}</td><td className="mono">{e.id ?? ""}</td><td>{e.message}</td></tr>)}</tbody>
          </table>
        </section>
      )}
      {p.ok && <>
        <Group title="Nuevos" items={p.new ?? []} cls="ok" />
        <Group title="Modificados (campo por campo)" items={p.modified ?? []} cls="warn" details />
        <Group title="Eliminados" items={p.deleted ?? []} cls="bad" />
        <Group title="Sin cambios" items={p.unchanged ?? []} cls="muted" />
        {!(p.new?.length || p.modified?.length || p.deleted?.length) && <p className="ok-text">Sin cambios: el proyecto ya coincide con la planilla.</p>}
      </>}
      {(p.notes ?? []).map((n, i) => <p key={i} className="muted small">{n}</p>)}
    </div>
  );
}

export function ExcelImportDialog() {
  const { importOpen, project, set, toast, serverVersion } = useEditor();
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [sheet, setSheet] = useState("Nudos");
  const [del, setDel] = useState(false);
  const [zone, setZone] = useState(() => String(((project?.length_srid ?? 32719) % 100) || 19));
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [busy, setBusy] = useState(false);
  if (!importOpen || !project) return null;
  const isCsv = file ? /\.(csv|txt)$/i.test(file.name) : false;
  const opts = () => ({ sheet: isCsv ? sheet : null, delete_missing: del, utm_zone: Number(zone) || null, hemisphere: "S" });
  const close = () => { set({ importOpen: false }); setPreview(null); setFile(null); };

  const doPreview = async () => {
    if (!file) return;
    setBusy(true);
    try {
      if (!(await flushPending())) throw new Error("No se pudieron guardar los cambios pendientes.");
      setPreview(await api.importPreview(project.id, file, opts()));
    } catch (e) { toast(errorText(e), "error"); } finally { setBusy(false); }
  };
  const doApply = async () => {
    if (!file || !preview) return;
    setBusy(true);
    try {
      const r = await api.importApply(project.id, file, { ...opts(), base_version: preview.base_version ?? serverVersion });
      if (!r.preview.ok) { setPreview(r.preview); toast("La planilla tiene errores: no se aplicó nada.", "error"); return; }
      await openProject(project.id);
      toast(r.created ? `Importación aplicada: versión ${r.version}.` : "Sin cambios que aplicar.");
      close();
    } catch (e) { toast(errorText(e), "error"); } finally { setBusy(false); }
  };

  return (
    <Modal title="Importar planilla (Excel o CSV)" onClose={close} wide>
      <div className="imp-form">
        <label className="field"><span>Archivo</span>
          <input ref={fileRef} type="file" accept=".xlsx,.csv,text/csv" onChange={(e) => { setFile(e.target.files?.[0] ?? null); setPreview(null); }} /></label>
        {isCsv && <label className="field"><span>Hoja del CSV</span>
          <select value={sheet} onChange={(e) => { setSheet(e.target.value); setPreview(null); }}>{SHEETS.map((x) => <option key={x}>{x}</option>)}</select></label>}
        <label className="field"><span>Huso UTM (Este/Norte, hemisferio sur)</span>
          <input type="number" min={1} max={60} value={zone} onChange={(e) => { setZone(e.target.value); setPreview(null); }} /></label>
        <label className="check"><input type="checkbox" checked={del} onChange={(e) => { setDel(e.target.checked); setPreview(null); }} />
          Eliminar los elementos que no estén en la planilla (solo en las hojas incluidas)</label>
        <p className="muted small">Si el ID existe se actualizan solo las columnas presentes; sin ID se crea un elemento con ID generado.
          <a href={api.templateUrl}> Descargar plantilla</a> · <a href={api.excelUrl(project.id)}>Exportar el proyecto</a></p>
      </div>
      {preview && <PreviewView p={preview} />}
      <div className="modal-actions">
        <button className="ghost" onClick={close}>Cancelar</button>
        <button onClick={() => void doPreview()} disabled={!file || busy}>{busy && !preview ? "Leyendo…" : "Vista previa"}</button>
        <button className="primary" onClick={() => void doApply()} disabled={!preview || !preview.ok || busy}>
          {busy && preview ? "Aplicando…" : "Aplicar (crea una versión)"}</button>
      </div>
    </Modal>
  );
}
