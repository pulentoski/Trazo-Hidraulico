// Registro de operación de la página «Gestión» (energía, cloro, cortes, reclamos, mantenciones, lecturas): formulario
// generado desde la especificación del servidor, importación de Excel/CSV con vista previa y errores por fila,
// plantilla, exportación y, en mantenciones, el cumplimiento.
import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { RecordFieldSpec, RecordImportPreview, RecordSpec } from "../api/types";
import { errorText } from "../state/projects";
import { useEditor } from "../state/store";

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

export function RecordsPanel({ pid, spec, readOnly, onChanged, openNonce, openAction }: {
  pid: string; spec: RecordSpec; readOnly: boolean; onChanged: () => void; openNonce?: number; openAction?: "import" | "add";
}) {
  const toast = useEditor((s) => s.toast);
  const [rows, setRows] = useState<Record<string, unknown>[] | null>(null);
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState<Record<string, string>>({});
  const [errors, setErrors] = useState<string[]>([]);
  const [preview, setPreview] = useState<RecordImportPreview | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [all, setAll] = useState(false);
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
      setAdding(false);
      await changed();
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
      if (fileRef.current) fileRef.current.value = "";
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
      await changed();
    } catch (e) { toast(errorText(e), "error"); } finally { setBusy(false); }
  };
  const remove = async (rid: number) => {
    if (!window.confirm("¿Eliminar esta fila del registro?")) return;
    try { await api.deleteRecords(pid, spec.kind, [rid]); await changed(); } catch (e) { toast(errorText(e), "error"); }
  };
  const complete = async (rid: number) => {
    const d = window.prompt("Fecha de cumplimiento (AAAA-MM-DD)", today());
    if (!d) return;
    try {
      const r = await api.completeTask(pid, rid, { done_on: d });
      toast(`Mantención cumplida; próxima fecha: ${String(r.rows[0]?.next_date ?? "—")}.`);
      await changed();
    } catch (e) { toast(errorText(e), "error"); }
  };

  const cols = [...spec.fields.map((f) => ({ key: f.key, label: f.label })), ...(spec.computed ?? []).map((c) => ({ key: c.key, label: c.label }))];
  const shown = all ? rows ?? [] : (rows ?? []).slice(0, 25);
  return (
    <details className="record-panel" ref={ref} data-record={spec.kind}>
      <summary><b>{spec.title}</b> <span className="muted small">{rows ? `${rows.length} filas` : "…"}</span></summary>
      <p className="muted small">{spec.help}</p>
      <div className="toolbar plain">
        {!readOnly && <button className="small" onClick={() => setAdding(!adding)} aria-expanded={adding}>{adding ? "Cerrar formulario" : "Agregar"}</button>}
        {!readOnly && <button className="small" onClick={() => fileRef.current?.click()} disabled={busy}>Importar planilla…</button>}
        <input ref={fileRef} type="file" accept=".xlsx,.csv" hidden aria-label={`Importar ${spec.title}`} onChange={(e) => void pick(e.target.files?.[0])} />
        <a className="btn small ghost" href={api.recordTemplateUrl(pid, spec.kind)}>Plantilla Excel</a>
        <a className="btn small ghost" href={api.recordExportUrl(pid, spec.kind, "xlsx")}>Exportar Excel</a>
        <a className="btn small ghost" href={api.recordExportUrl(pid, spec.kind, "csv")}>CSV</a>
      </div>
      {adding && (
        <form className="record-form" onSubmit={submit} aria-label={`Nueva fila: ${spec.title}`}>
          {spec.fields.map((f) => (
            <label key={f.key} className="field stacked">
              <span>{f.label}{f.required ? " *" : ""}</span>
              {f.type === "choice" ? (
                <select value={form[f.key] ?? ""} onChange={(e) => setForm({ ...form, [f.key]: e.target.value })} required={f.required}>
                  <option value="">—</option>{(f.choices ?? []).map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
              ) : (
                <input type={inputType(f)} inputMode={f.type === "float" || f.type === "int" ? "decimal" : undefined}
                  value={form[f.key] ?? ""} onChange={(e) => setForm({ ...form, [f.key]: e.target.value })} required={f.required}
                  placeholder={f.help} title={f.help} />
              )}
            </label>
          ))}
          {errors.length > 0 && <ul className="bad-text small">{errors.map((x) => <li key={x}>{x}</li>)}</ul>}
          <div className="modal-actions left"><button className="primary small" disabled={busy}>Guardar fila</button></div>
        </form>
      )}
      {preview && (
        <div className="import-preview" role="region" aria-label="Vista previa de la importación">
          <p><b>{preview.valid}</b> filas válidas · <b className={preview.invalid ? "bad-text" : ""}>{preview.invalid}</b> con errores
            {file ? <span className="muted"> · {file.name}</span> : null}</p>
          <div className="table-scroll">
            <table className="tbl compact">
              <thead><tr><th>Fila</th>{spec.fields.map((f) => <th key={f.key}>{f.label}</th>)}<th>Errores</th></tr></thead>
              <tbody>{preview.rows.slice(0, 60).map((r) => (
                <tr key={r.row} className={r.errors.length ? "row-error" : ""}>
                  <td>{r.row}</td>{spec.fields.map((f) => <td key={f.key}>{show((r.values as Record<string, unknown>)[f.key])}</td>)}
                  <td className="bad-text">{r.errors.join(" · ")}</td>
                </tr>))}</tbody>
            </table>
          </div>
          {preview.rows.length > 60 && <p className="muted small">… {preview.rows.length - 60} filas más.</p>}
          <div className="modal-actions left">
            <button className="primary small" disabled={busy || !preview.valid} onClick={() => void applyImport()}>Importar {preview.valid} filas válidas</button>
            <button className="ghost small" onClick={() => { setPreview(null); setFile(null); }}>Cancelar</button>
          </div>
        </div>
      )}
      {rows && rows.length > 0 ? (
        <div className="table-scroll">
          <table className="tbl compact">
            <thead><tr>{cols.map((c) => <th key={c.key}>{c.label}</th>)}<th /></tr></thead>
            <tbody>{shown.map((r) => (
              <tr key={String(r.id)}>
                {cols.map((c) => <td key={c.key} className={c.key === "status" ? `${STATUS_CLS[String(r[c.key])] ?? ""}-text` : ""}>{show(r[c.key])}</td>)}
                <td className="row-actions">
                  {spec.kind === "mantenciones" && !readOnly && r.status !== "hecha" &&
                    <button className="ghost small" onClick={() => void complete(Number(r.id))}>Cumplir</button>}
                  {!readOnly && <button className="ghost small" aria-label="Eliminar fila" onClick={() => void remove(Number(r.id))}>✕</button>}
                </td>
              </tr>))}</tbody>
          </table>
          {!all && (rows?.length ?? 0) > 25 && <button className="ghost small" onClick={() => setAll(true)}>Ver las {rows!.length} filas</button>}
        </div>
      ) : rows ? <p className="muted small">Sin filas. Agregue una con el formulario o importe la plantilla.</p> : null}
    </details>
  );
}
