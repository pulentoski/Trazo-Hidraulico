// Registro de operación de la página «Gestión» (energía, cloro, cortes, reclamos, mantenciones, lecturas): formulario
// generado desde la especificación del servidor, importación de Excel/CSV con vista previa y errores por fila,
// plantilla, exportación y, en mantenciones, el cumplimiento.
import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { RecordFieldSpec, RecordImportPreview, RecordSpec } from "../api/types";
import { errorText } from "../state/projects";
import { useEditor } from "../state/store";
import { Icon } from "./Icons";
import { Modal } from "./Dialogs";
import type { CellType } from "../lib/table";
import { DataTable } from "./DataTable";

const today = () => new Date().toISOString().slice(0, 10);

function inputType(f: RecordFieldSpec): string {
  return { date: "date", datetime: "datetime-local", month: "month" }[f.type as string] ?? "text";
}

function show(v: unknown): string {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "number") return v.toLocaleString("es-CL", { maximumFractionDigits: 3 });
  return String(v);
}

const STATUS_CLS: Record<string, string> = { atrasada: "bad", pendiente: "ok", hecha: "muted" };

/** Formulario de una fila nueva y planilla con vista previa: lo comparten el panel de registros y «Ingresar datos». */
function useRecordEntry(pid: string, spec: RecordSpec, onSaved: () => Promise<void> | void) {
  const toast = useEditor((s) => s.toast);
  const [form, setForm] = useState<Record<string, string>>({});
  const [errors, setErrors] = useState<string[]>([]);
  const [preview, setPreview] = useState<RecordImportPreview | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErrors([]);
    try {
      const row: Record<string, unknown> = {};
      for (const f of spec.fields) if (form[f.key] !== undefined && form[f.key] !== "") row[f.key] = form[f.key];
      await api.addRecords(pid, spec.kind, [row]);
      toast(`${spec.title}: fila agregada.`);
      setForm({});
      await onSaved();
    } catch (err) {
      const body = (err as { body?: { detail?: { rows?: { errors: string[] }[] } } }).body;
      const list = body?.detail?.rows?.flatMap((r) => r.errors);
      if (list?.length) setErrors(list);
      else toast(errorText(err), "error");
    } finally { setBusy(false); }
  };
  const pick = async (f: File | undefined) => {
    if (!f) return;
    setFile(f);
    setBusy(true);
    try { setPreview(await api.importRecords(pid, spec.kind, f, false)); } catch (e) { toast(errorText(e), "error"); setFile(null); } finally {
      setBusy(false);
    }
  };
  const applyImport = async () => {
    if (!file || !preview) return;
    setBusy(true);
    try {
      const r = await api.importRecords(pid, spec.kind, file, true, true);
      toast(`${spec.title}: ${r.created} filas nuevas${r.updated ? `, ${r.updated} actualizadas` : ""}${r.invalid ? `; ${r.invalid} con errores omitidas` : ""}.`);
      setPreview(null);
      setFile(null);
      await onSaved();
    } catch (e) { toast(errorText(e), "error"); } finally { setBusy(false); }
  };
  const cancelImport = () => { setPreview(null); setFile(null); };
  return { form, setForm, errors, preview, file, busy, submit, pick, applyImport, cancelImport };
}

type Entry = ReturnType<typeof useRecordEntry>;

function RecordForm({ spec, e, onCancel }: { spec: RecordSpec; e: Entry; onCancel: () => void }) {
  return (
    <form className="record-form" onSubmit={e.submit} aria-label={`Nueva fila: ${spec.title}`}>
      {spec.fields.map((f) => (
        <label key={f.key} className="field stacked">
          <span>{f.label}{f.required ? " *" : ""}</span>
          {f.type === "choice" ? (
            <select value={e.form[f.key] ?? ""} onChange={(ev) => e.setForm({ ...e.form, [f.key]: ev.target.value })} required={f.required}>
              <option value="">—</option>{(f.choices ?? []).map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          ) : (
            <input type={inputType(f)} inputMode={f.type === "float" || f.type === "int" ? "decimal" : undefined}
              value={e.form[f.key] ?? ""} onChange={(ev) => e.setForm({ ...e.form, [f.key]: ev.target.value })} required={f.required}
              placeholder={f.help} title={f.help} />
          )}
        </label>
      ))}
      {e.errors.length > 0 && <ul className="bad-text small">{e.errors.map((x) => <li key={x}>{x}</li>)}</ul>}
      <div className="modal-actions"><button type="button" className="ghost small" onClick={onCancel}>Cancelar</button><button className="primary small" disabled={e.busy}><Icon.save /><span>Guardar fila</span></button></div>
    </form>
  );
}

function ImportPreviewView({ spec, e }: { spec: RecordSpec; e: Entry }) {
  const p = e.preview;
  if (!p) return null;
  return (
    <div className="import-preview" role="region" aria-label="Vista previa de la importación">
      <p><b>{p.valid}</b> filas válidas · <b className={p.invalid ? "bad-text" : ""}>{p.invalid}</b> con errores
        {e.file ? <span className="muted"> · {e.file.name}</span> : null}</p>
      <DataTable compact label="Vista previa" rows={p.rows} rowKey={(r) => String(r.row)} pageSize={25} rowClassName={(r) => (r.errors.length ? "row-error" : "")}
        columns={[
          { key: "row", label: "Fila", type: "num", value: (r) => r.row },
          ...spec.fields.map((f) => ({ key: f.key, label: f.label, value: (r: (typeof p.rows)[number]) => show((r.values as Record<string, unknown>)[f.key]) })),
          { key: "err", label: "Errores", value: (r) => r.errors.join(" · "), className: "bad-text" },
        ]} />
      <div className="modal-actions">
        <button className="ghost small" onClick={e.cancelImport}>Cancelar</button>
        <button className="primary small" disabled={e.busy || !p.valid} onClick={() => void e.applyImport()}>Importar {p.valid} filas válidas</button>
      </div>
    </div>
  );
}

/** «Ingresar datos» desde un cuadro vacío de Gestión: abre directo el formulario o la planilla del registro y, al
 * guardar, se cierra y vuelve a Gestión (que recarga los indicadores). */
export function RecordEntryDialog({ pid, spec, mode: initial, onClose, onSaved }: {
  pid: string; spec: RecordSpec; mode: "add" | "import"; onClose: () => void; onSaved: () => void;
}) {
  const [mode, setMode] = useState(initial);
  const fileRef = useRef<HTMLInputElement>(null);
  const e = useRecordEntry(pid, spec, () => { onSaved(); onClose(); });
  useEffect(() => { if (initial === "import") fileRef.current?.click(); }, [initial]);
  return (
    <Modal title={`Ingresar datos · ${spec.title}`} onClose={onClose} wide>
      <p className="muted small">{spec.help}</p>
      <div className="seg" role="group" aria-label="Forma de ingreso">
        <button type="button" className={mode === "add" ? "on" : ""} aria-pressed={mode === "add"} onClick={() => setMode("add")}><Icon.edit /><span>Formulario</span></button>
        <button type="button" className={mode === "import" ? "on" : ""} aria-pressed={mode === "import"} onClick={() => setMode("import")}><Icon.upload /><span>Planilla</span></button>
      </div>
      {mode === "add" ? <RecordForm spec={spec} e={e} onCancel={onClose} /> : (
        <div className="record-import">
          <div className="toolbar plain">
            <button className="small primary" onClick={() => fileRef.current?.click()} disabled={e.busy}><Icon.upload /><span>Elegir planilla (.xlsx o .csv)…</span></button>
            <a className="btn small ghost" href={api.recordTemplateUrl(pid, spec.kind)}><Icon.download /><span>Plantilla Excel</span></a>
          </div>
          <ImportPreviewView spec={spec} e={e} />
        </div>
      )}
      <input ref={fileRef} type="file" accept=".xlsx,.csv" hidden aria-label={`Importar ${spec.title}`}
        onChange={(ev) => { setMode("import"); void e.pick(ev.target.files?.[0]); ev.target.value = ""; }} />
    </Modal>
  );
}

export function RecordsPanel({ pid, spec, readOnly, onChanged, openNonce, openAction }: {
  pid: string; spec: RecordSpec; readOnly: boolean; onChanged: () => void; openNonce?: number; openAction?: "import" | "add";
}) {
  const toast = useEditor((s) => s.toast);
  const [rows, setRows] = useState<Record<string, unknown>[] | null>(null);
  const [adding, setAdding] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const ref = useRef<HTMLDetailsElement>(null);

  const load = () => api.records(pid, spec.kind).then((r) => setRows(r.rows)).catch((e) => toast(errorText(e), "error"));
  useEffect(() => { void load(); }, [pid, spec.kind]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!openNonce || !ref.current) return;
    ref.current.open = true;
    ref.current.scrollIntoView({ block: "center" });
    if (readOnly) return;
    if (openAction === "import") fileRef.current?.click();
    else setAdding(true);
  }, [openNonce]); // eslint-disable-line react-hooks/exhaustive-deps
  const changed = async () => { await load(); onChanged(); };
  const e = useRecordEntry(pid, spec, async () => { setAdding(false); await changed(); });

  const remove = async (rid: number) => {
    if (!window.confirm("¿Eliminar esta fila del registro?")) return;
    try { await api.deleteRecords(pid, spec.kind, [rid]); await changed(); } catch (err) { toast(errorText(err), "error"); }
  };
  const complete = async (rid: number) => {
    const d = window.prompt("Fecha de cumplimiento (AAAA-MM-DD)", today());
    if (!d) return;
    try {
      const r = await api.completeTask(pid, rid, { done_on: d });
      toast(`Mantención cumplida; próxima fecha: ${String(r.rows[0]?.next_date ?? "—")}.`);
      await changed();
    } catch (err) { toast(errorText(err), "error"); }
  };

  const typeOf = (t: string): CellType => (t === "float" || t === "int" ? "num" : t === "date" || t === "datetime" || t === "month" ? "date" : "text");
  const cols = [...spec.fields.map((f) => ({ key: f.key, label: f.label, type: typeOf(f.type) })),
    ...(spec.computed ?? []).map((c) => ({ key: c.key, label: c.unit ? `${c.label} (${c.unit})` : c.label, type: (c.num ? "num" : "text") as CellType }))];
  return (
    <details className="record-panel" ref={ref} data-record={spec.kind}>
      <summary><b>{spec.title}</b> <span className="muted small">{rows ? `${rows.length} filas` : "…"}</span></summary>
      <p className="muted small">{spec.help}</p>
      <div className="toolbar plain">
        {!readOnly && <button className="small" onClick={() => setAdding(!adding)} aria-expanded={adding}>{adding ? <><Icon.close /><span>Cerrar formulario</span></> : <><Icon.plus /><span>Agregar</span></>}</button>}
        {!readOnly && <button className="small" onClick={() => fileRef.current?.click()} disabled={e.busy}><Icon.upload /><span>Importar planilla…</span></button>}
        <input ref={fileRef} type="file" accept=".xlsx,.csv" hidden aria-label={`Importar ${spec.title}`} onChange={(ev) => { void e.pick(ev.target.files?.[0]); ev.target.value = ""; }} />
        <a className="btn small ghost" href={api.recordTemplateUrl(pid, spec.kind)}>Plantilla Excel</a>
        <a className="btn small ghost" href={api.recordExportUrl(pid, spec.kind, "xlsx")}>Exportar Excel</a>
        <a className="btn small ghost" href={api.recordExportUrl(pid, spec.kind, "csv")}>CSV</a>
      </div>
      {adding && <RecordForm spec={spec} e={e} onCancel={() => setAdding(false)} />}
      <ImportPreviewView spec={spec} e={e} />
      {rows && (
        <DataTable compact label={spec.title} rows={rows} rowKey={(r) => String(r.id)} pageSize={25} exportName={`${spec.kind}`}
          empty={<p className="muted small">Sin filas. Agregue una con el formulario o importe la plantilla.</p>}
          initialSort={cols.find((c) => c.type === "date") ? { key: cols.find((c) => c.type === "date")!.key, dir: -1 } : undefined}
          columns={[
            ...cols.map((c) => ({ key: c.key, label: c.label, type: c.type,
              value: (r: Record<string, unknown>) => r[c.key] as string | number | null | undefined,
              render: (r: Record<string, unknown>) => show(r[c.key]),
              className: (r: Record<string, unknown>) => (c.key === "status" ? `${STATUS_CLS[String(r[c.key])] ?? ""}-text` : "") })),
            { key: "_acc", label: "", sortable: false, noExport: true, value: () => "", className: "row-actions",
              render: (r: Record<string, unknown>) => (<>
                {spec.kind === "mantenciones" && !readOnly && r.status !== "hecha" &&
                  <button className="ghost small" onClick={() => void complete(Number(r.id))}>Cumplir</button>}
                {!readOnly && <button className="ghost small danger-text" title="Eliminar la fila (pide confirmación)" aria-label="Eliminar fila" onClick={() => void remove(Number(r.id))}><Icon.close /></button>}
              </>) },
          ]} />
      )}
    </details>
  );
}
