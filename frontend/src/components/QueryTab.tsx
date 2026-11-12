// Pestaña «Consultas»: filtros por tipo de elemento y atributos (Y/O), resultados en mapa y tabla, guardar y exportar.
import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { Condition, QueryDef, QueryElement, QueryResult, SavedQueryOut } from "../api/types";
import { fmt } from "../lib/format";
import { uidOf } from "../lib/sig";
import { errorText } from "../state/projects";
import { useEditor } from "../state/store";
import { Icon } from "./Icons";

const OPS: { id: Condition["op"]; label: string; noValue?: boolean }[] = [
  { id: "eq", label: "=" }, { id: "ne", label: "≠" }, { id: "lt", label: "<" }, { id: "le", label: "≤" }, { id: "gt", label: ">" },
  { id: "ge", label: "≥" }, { id: "contains", label: "contiene" }, { id: "starts", label: "empieza con" },
  { id: "in", label: "en lista (a, b, c)" }, { id: "empty", label: "vacío", noValue: true }, { id: "not_empty", label: "no vacío", noValue: true },
];
const SUM_LABEL: Record<string, string> = { length_hydraulic_m: "m de red", _consumption_lps: "L/s", consumption_m3_mes: "m³/mes" };

function download(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

export function QueryTab() {
  const { project, net, set, focus, toast, highlight } = useEditor();
  const [meta, setMeta] = useState<QueryElement[]>([]);
  const [element, setElement] = useState("tramos");
  const [logic, setLogic] = useState<"and" | "or">("and");
  const [conds, setConds] = useState<Condition[]>([]);
  const [res, setRes] = useState<QueryResult | null>(null);
  const [saved, setSaved] = useState<SavedQueryOut[]>([]);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { api.queryFields().then(setMeta).catch(() => setMeta([])); }, []);
  useEffect(() => { if (project) api.savedQueries(project.id).then(setSaved).catch(() => setSaved([])); }, [project]);
  const fields = useMemo(() => meta.find((m) => m.key === element)?.fields ?? [], [meta, element]);
  if (!project) return null;
  const def = (): QueryDef => ({ element, where: { logic, conditions: conds } });

  const run = async (d: QueryDef = def()) => {
    setBusy(true);
    try {
      const r = await api.query(project.id, d);
      setRes(r);
      const uids = r.rows.map((row) => uidOf(net, r.element, String(row.id))).filter((u): u is string => !!u);
      set({ highlight: uids });
      if (uids.length) useEditor.getState().frame(uids);
    } catch (e) { toast(errorText(e), "error"); } finally { setBusy(false); }
  };
  const load = (q: SavedQueryOut) => {
    setElement(q.definition.element);
    setLogic((q.definition.where?.logic as "and" | "or") ?? "and");
    setConds((q.definition.where?.conditions ?? []) as Condition[]);
    setName(q.name);
    void run(q.definition);
  };
  const save = async () => {
    if (!name.trim()) return toast("Indique un nombre para la consulta.", "error");
    try {
      await api.saveQuery(project.id, name.trim(), def());
      setSaved(await api.savedQueries(project.id));
      toast(`Consulta «${name.trim()}» guardada.`);
    } catch (e) { toast(errorText(e), "error"); }
  };
  const exportAs = async (fmtType: "csv" | "xlsx") => {
    try { download(await api.queryExport(project.id, def(), fmtType), `consulta-${element}.${fmtType}`); } catch (e) { toast(errorText(e), "error"); }
  };
  const upd = (i: number, patch: Partial<Condition>) => setConds(conds.map((c, k) => (k === i ? { ...c, ...patch } : c)));
  const fieldOf = (key: string) => fields.find((f) => f.key === key);

  return (
    <div className="query-tab">
      <div className="query-form">
        <div className="toolbar">
          <select value={element} onChange={(e) => { setElement(e.target.value); setConds([]); setRes(null); }} aria-label="Tipo de elemento">
            {meta.map((m) => <option key={m.key} value={m.key}>{m.label}</option>)}
          </select>
          <div className="seg" role="group" aria-label="Combinar condiciones">
            <button className={logic === "and" ? "on" : ""} onClick={() => setLogic("and")}>Y (todas)</button>
            <button className={logic === "or" ? "on" : ""} onClick={() => setLogic("or")}>O (alguna)</button>
          </div>
          <button className="small" onClick={() => setConds([...conds, { field: fields[1]?.key ?? "id", op: "eq", value: "" }])}>+ Condición</button>
          <button className="small primary" disabled={busy} onClick={() => void run()}>{busy ? "…" : "Consultar"}</button>
          {highlight.length > 0 && <button className="small ghost" onClick={() => set({ highlight: [] })}>Quitar resaltado</button>}
        </div>
        {conds.map((c, i) => {
          const f = fieldOf(c.field);
          const op = OPS.find((o) => o.id === c.op);
          return (
            <div key={i} className="cond">
              <select value={c.field} onChange={(e) => upd(i, { field: e.target.value, value: "" })}>
                {fields.map((x) => <option key={x.key} value={x.key}>{x.label}</option>)}
              </select>
              <select value={c.op} onChange={(e) => upd(i, { op: e.target.value as Condition["op"] })}>
                {OPS.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
              </select>
              {!op?.noValue && (f?.choices && c.op !== "in" ? (
                <select value={String(c.value ?? "")} onChange={(e) => upd(i, { value: e.target.value })}>
                  <option value="">—</option>
                  {f.choices.map(([k, label]) => <option key={k} value={k}>{label}</option>)}
                </select>
              ) : (
                <input value={String(c.value ?? "")} placeholder="valor" onChange={(e) => upd(i, { value: e.target.value })}
                  onKeyDown={(e) => e.key === "Enter" && void run()} />
              ))}
              <button className="small ghost" onClick={() => setConds(conds.filter((_, k) => k !== i))} aria-label="Quitar condición"><Icon.close /></button>
            </div>
          );
        })}
        <div className="toolbar">
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Nombre para guardar" aria-label="Nombre de la consulta" />
          <button className="small" onClick={() => void save()}>Guardar</button>
          {saved.length > 0 && (
            <select value="" onChange={(e) => { const q = saved.find((x) => String(x.id) === e.target.value); if (q) load(q); }} aria-label="Consultas guardadas">
              <option value="">Consultas guardadas…</option>
              {saved.map((q) => <option key={q.id} value={q.id}>{q.name}</option>)}
            </select>
          )}
          {saved.some((q) => q.name === name) && (
            <button className="small ghost" onClick={async () => {
              const q = saved.find((x) => x.name === name)!;
              await api.deleteQuery(project.id, q.id);
              setSaved(saved.filter((x) => x.id !== q.id));
            }}>Eliminar guardada</button>
          )}
        </div>
      </div>
      {res && (
        <div className="query-res">
          <div className="toolbar">
            <strong>{res.count} de {res.total}</strong>
            {Object.entries(res.sums ?? {}).map(([k, v]) => <span key={k} className="muted">· {fmt(v, k === "_consumption_lps" ? 3 : 1)} {SUM_LABEL[k] ?? k}</span>)}
            <button className="small" onClick={() => void exportAs("xlsx")}>Excel</button>
            <button className="small" onClick={() => void exportAs("csv")}>CSV</button>
          </div>
          <table className="tbl compact">
            <thead><tr>{res.columns.map((c) => <th key={c.key}>{c.label}</th>)}</tr></thead>
            <tbody>
              {res.rows.slice(0, 1000).map((r) => (
                <tr key={String(r.id)} className="clickable" onClick={() => { const u = uidOf(net, res.element, String(r.id)); if (u) focus([u]); }}>
                  {res.columns.map((c) => <td key={c.key} className={typeof r[c.key] === "number" ? "num" : ""}>{r[c.key] === null || r[c.key] === undefined ? "" : typeof r[c.key] === "number" ? fmt(r[c.key] as number, 3) : String(r[c.key])}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
