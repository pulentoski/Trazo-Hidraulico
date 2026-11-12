// Pestaña «Mediciones»: registro de funcionamiento (medidores, presiones, niveles) y comparación con el modelo.
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { MeasureCompare, MeasurementIn, MeasurementOut, MonitoringSettings } from "../api/types";
import { fmt } from "../lib/format";
import { uidOf } from "../lib/sig";
import { errorText } from "../state/projects";
import { useEditor } from "../state/store";
import { Chart } from "./Chart";
import { Help, NumField } from "./Fields";
import { Icon } from "./Icons";

const KIND = { meter: "Medidor (m³)", pressure: "Presión (m)", level: "Nivel (m)" } as const;
const TYPE = { node: "Nudo / estanque", link: "Tramo / bomba", client: "Cliente", well: "Pozo" } as const;
const SHEET = { node: "nudos", link: "tramos", client: "clientes", well: "pozos" } as const;

function localNow(): string {
  const d = new Date();
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 16);
}

export function MeasurementsTab() {
  const { project, net, focus, toast, result } = useEditor();
  const [list, setList] = useState<MeasurementOut[]>([]);
  const [cmp, setCmp] = useState<MeasureCompare | null>(null);
  const [cfg, setCfg] = useState<MonitoringSettings | null>(null);
  const [form, setForm] = useState<MeasurementIn>({ element_type: "node", element_id: "", kind: "pressure", measured_at: localNow(), value: 0 });
  const [sel, setSel] = useState<number>(0);
  const fileRef = useRef<HTMLInputElement>(null);
  const refresh = useCallback(async () => {
    if (!project) return;
    try {
      setList(await api.measurements(project.id));
      setCmp(await api.compareMeasurements(project.id));
    } catch (e) { toast(errorText(e), "error"); }
  }, [project, toast]);
  useEffect(() => { void refresh(); }, [refresh, result?.run_id]);
  useEffect(() => { if (project) api.monitoring(project.id).then(setCfg).catch(() => setCfg(null)); }, [project]);
  if (!project) return null;

  const options = form.element_type === "node" ? Object.values(net.nodes) : form.element_type === "link" ? Object.values(net.links)
    : form.element_type === "client" ? Object.values(net.clients) : Object.values(net.wells);
  const add = async () => {
    if (!form.element_id) return toast("Elija el elemento.", "error");
    try {
      await api.addMeasurements(project.id, [{ ...form, measured_at: new Date(form.measured_at).toISOString() }]);
      await refresh();
    } catch (e) { toast(errorText(e), "error"); }
  };
  const importFile = async (f: File) => {
    try {
      const r = await api.importMeasurements(project.id, f);
      if (r.errors.length) toast(`No se importó nada: ${r.errors.slice(0, 3).join(" ")}`, "error");
      else { toast(`${r.created} mediciones importadas.`); await refresh(); }
    } catch (e) { toast(errorText(e), "error"); } finally { if (fileRef.current) fileRef.current.value = ""; }
  };
  const series = cmp?.series ?? [];
  const cur = series[sel];

  return (
    <div className="meas-tab">
      <div className="meas-form">
        <div className="toolbar wrap">
          <select value={form.element_type} onChange={(e) => setForm({ ...form, element_type: e.target.value as MeasurementIn["element_type"], element_id: "",
            kind: e.target.value === "link" || e.target.value === "well" ? "meter" : form.kind })} aria-label="Tipo de elemento">
            {Object.entries(TYPE).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <select value={form.element_id} onChange={(e) => setForm({ ...form, element_id: e.target.value })} aria-label="Elemento">
            <option value="">Elemento…</option>{options.map((o) => <option key={o.uid} value={o.id}>{o.id}</option>)}
          </select>
          <select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value as MeasurementIn["kind"] })} aria-label="Medición">
            {Object.entries(KIND).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <input type="datetime-local" step={1} value={form.measured_at} onChange={(e) => setForm({ ...form, measured_at: e.target.value })} aria-label="Fecha y hora" />
          <input inputMode="decimal" style={{ width: 110 }} placeholder="Valor" onChange={(e) => setForm({ ...form, value: Number(e.target.value.replace(",", ".")) })} aria-label="Valor" />
          <button className="small primary" onClick={() => void add()}>Agregar</button>
        </div>
        <div className="toolbar wrap">
          <button className="small" onClick={() => fileRef.current?.click()}>Importar Excel/CSV…</button>
          <input ref={fileRef} type="file" accept=".xlsx,.csv" hidden onChange={(e) => e.target.files?.[0] && void importFile(e.target.files[0])} />
          <a className="btn small" href={api.measurementsTemplateUrl(project.id)}>Plantilla</a>
          <Help text="Lecturas de medidor (m³ acumulados): el caudal se calcula entre lecturas consecutivas y como promedio total. Presión en nudos o clientes; nivel en estanques (m sobre el fondo) o pozos (m bajo el terreno). Se compara con el modelo a la misma hora del día." />
        </div>
        {cfg && (
          <fieldset><legend>Tolerancias</legend>
            <div className="grid4">
              <NumField label="Caudal" unit="%" value={cfg.flow_pct} onCommit={async (v) => v && setCfg(await api.saveMonitoring(project.id, { ...cfg, flow_pct: v }))} />
              <NumField label="Presión" unit="m" value={cfg.pressure_m} onCommit={async (v) => v && setCfg(await api.saveMonitoring(project.id, { ...cfg, pressure_m: v }))} />
              <NumField label="Nivel" unit="m" value={cfg.level_m} onCommit={async (v) => v && setCfg(await api.saveMonitoring(project.id, { ...cfg, level_m: v }))} />
            </div>
            <button className="small ghost" onClick={() => void refresh()}>Recalcular comparación</button>
          </fieldset>
        )}
        <p className="muted small">{list.length} mediciones registradas.</p>
        {list.length > 0 && (
          <table className="tbl compact">
            <thead><tr><th>Elemento</th><th>Medición</th><th>Fecha y hora</th><th className="num">Valor</th><th></th></tr></thead>
            <tbody>{list.slice(-200).map((m) => (
              <tr key={m.id}><td className="mono">{m.element_id}</td><td>{KIND[m.kind]}</td><td>{new Date(m.measured_at).toLocaleString("es-CL")}</td>
                <td className="num">{fmt(m.value, 3)}</td>
                <td><button className="small ghost danger-text" aria-label="Eliminar" title="Eliminar la medición (pide confirmación)" onClick={async () => { if (!window.confirm("¿Eliminar esta medición?")) return; await api.deleteMeasurements(project.id, [m.id]); await refresh(); }}><Icon.trash /></button></td></tr>
            ))}</tbody>
          </table>
        )}
      </div>
      <div className="meas-cmp">
        {!series.length ? <p className="muted pad">Agregue mediciones para compararlas con el modelo (versión guardada).</p> : (<>
          <table className="tbl compact">
            <thead><tr><th>Elemento</th><th>Magnitud</th><th className="num">Mediciones</th><th className="num">Dif. máx.</th><th>Resultado</th></tr></thead>
            <tbody>{series.map((s, i) => (
              <tr key={`${s.element_id}-${s.kind}`} className={`clickable ${i === sel ? "current" : ""}`} onClick={() => {
                setSel(i);
                const u = uidOf(net, SHEET[s.element_type], s.element_id);
                if (u) focus([u]);
              }}>
                <td className="mono">{s.element_id}</td><td>{s.quantity} ({s.unit})</td><td className="num">{s.points.length}</td>
                <td className="num">{s.max_abs_diff == null ? "—" : fmt(s.max_abs_diff, 2)}</td>
                <td className={s.alert ? "bad" : ""}>{s.alert ? "▲ " : "✔ "}{s.message}</td>
              </tr>
            ))}</tbody>
          </table>
          {cur && cur.points.length > 0 && (() => {
            const t0 = new Date(cur.points[0].time).getTime();
            const x = cur.points.map((p) => (new Date(p.time).getTime() - t0) / 60000);
            return (<>
              {cur.average_measured != null && <p className="small pad">Caudal medio entre la primera y la última lectura: <b>{fmt(cur.average_measured, 2)} L/s</b>.</p>}
              <Chart title={`${cur.quantity} de ${cur.element_id}: medido y modelo`} x={x} xLabel="Minutos desde la primera medición" xFormat={(v) => fmt(v, 1)}
                yLabel={`${cur.quantity} (${cur.unit})`} fileName={`medicion-${cur.element_id}-${cur.kind}`}
                series={[{ name: "Medido", values: cur.points.map((p) => p.measured) }, { name: "Modelo", values: cur.points.map((p) => p.model ?? null), dashed: true },
                  { name: "Diferencia", values: cur.points.map((p) => p.diff ?? null) }]} />
            </>);
          })()}
        </>)}
      </div>
    </div>
  );
}
