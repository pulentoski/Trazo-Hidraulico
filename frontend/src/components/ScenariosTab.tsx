// Pestaña «Escenarios»: llaves de corte, clientes sin suministro o bajo la presión mínima y comparación.
import { useState } from "react";
import { api } from "../api/client";
import type { CompareResult, ScenarioResult } from "../api/types";
import { affectedCsv, compareCsv, downloadText } from "../lib/csv";
import { fmt } from "../lib/format";
import { flushPending } from "../state/live";
import { errorText } from "../state/projects";
import { useEditor } from "../state/store";
import { DataTable } from "./DataTable";

const BUILTIN = [{ id: "normal", name: "Operación normal (todas abiertas)" }, { id: "todas_cerradas", name: "Todas cerradas" },
  { id: "actual", name: "Estado del modelo" }];

export function ScenariosTab() {
  const { scenarios, setScenarios, net, project, set, toast, scenarioView, focus } = useEditor();
  const [current, setCurrent] = useState("normal");
  const [res, setRes] = useState<ScenarioResult | null>(null);
  const [cmp, setCmp] = useState<CompareResult | null>(null);
  const [b, setB] = useState("");
  const [busy, setBusy] = useState(false);
  const all = [...BUILTIN, ...scenarios];
  const custom = scenarios.find((x) => x.id === current);
  const shutoffs = Object.values(net.shutoffs).sort((x, y) => x.id.localeCompare(y.id, "es", { numeric: true }));

  const version = async () => {
    if (!(await flushPending())) throw new Error("No se pudieron guardar los cambios pendientes.");
    return useEditor.getState().serverVersion!;
  };
  const run = async () => {
    if (!project) return;
    setBusy(true);
    try {
      const r = await api.scenario(project.id, await version(), current);
      setRes(r);
      setCmp(null);
      set({ scenarioView: r });
    } catch (e) { toast(errorText(e), "error"); } finally { setBusy(false); }
  };
  const compare = async () => {
    if (!project || !b) return;
    setBusy(true);
    try {
      const r = await api.compareScenarios(project.id, await version(), current, b);
      setCmp(r);
      setRes(r.b);
      set({ scenarioView: r.b });
    } catch (e) { toast(errorText(e), "error"); } finally { setBusy(false); }
  };
  const addScenario = () => {
    const name = window.prompt("Nombre del escenario", "Corte sector norte")?.trim();
    if (!name) return;
    let id = name.toLowerCase().normalize("NFKD").replace(/[^\w-]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 40) || "escenario";
    while (all.some((x) => x.id === id)) id = `${id.slice(0, 36)}-${Math.floor(Math.random() * 900 + 100)}`;
    setScenarios([...scenarios, { id, name, closed: [] }]);
    setCurrent(id);
  };
  const toggle = (sid: string) => custom && setScenarios(scenarios.map((x) => x.id !== custom.id ? x
    : { ...x, closed: (x.closed ?? []).includes(sid) ? (x.closed ?? []).filter((y) => y !== sid) : [...(x.closed ?? []), sid] }));
  const remove = () => {
    if (!custom || !window.confirm(`¿Eliminar el escenario «${custom.name}»?`)) return;
    setScenarios(scenarios.filter((x) => x.id !== custom.id));
    setCurrent("normal");
  };
  const gotoClient = (id: string) => {
    const c = Object.values(net.clients).find((x) => x.id === id);
    if (c) focus([c.uid]);
  };

  return (
    <>
      <div className="toolbar">
        <select value={current} onChange={(e) => setCurrent(e.target.value)} aria-label="Escenario">
          {all.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
        </select>
        <button className="small primary" disabled={busy || !project} onClick={() => void run()}>{busy ? "Simulando…" : "Simular escenario"}</button>
        <button className="small ghost" onClick={addScenario}>+ Nuevo escenario</button>
        {custom && <button className="small ghost" onClick={remove}>Eliminar</button>}
        <span className="muted small">Comparar con</span>
        <select value={b} onChange={(e) => setB(e.target.value)} aria-label="Escenario a comparar">
          <option value="">—</option>{all.filter((x) => x.id !== current).map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
        </select>
        <button className="small" disabled={busy || !b} onClick={() => void compare()}>Comparar</button>
        {scenarioView && <button className="small ghost" onClick={() => set({ scenarioView: null })}>Quitar del mapa</button>}
      </div>
      {custom && (
        <div className="pad">
          <div className="muted small">Llaves cerradas en «{custom.name}» (clic para abrir/cerrar):</div>
          {shutoffs.length === 0 ? <p className="muted small">El proyecto no tiene llaves. Ubíquelas con la herramienta Llave de corte (L).</p> : (
            <div className="chip-list">{shutoffs.map((sh) => (
              <label key={sh.uid} className={(custom.closed ?? []).includes(sh.id) ? "on" : ""}>
                <input type="checkbox" checked={(custom.closed ?? []).includes(sh.id)} onChange={() => toggle(sh.id)} />{sh.id}{sh.props.name ? ` · ${sh.props.name}` : ""}
              </label>))}</div>)}
        </div>
      )}
      {cmp ? (
        <>
          <div className="toolbar"><b>{cmp.a.scenario_name}</b> → <b>{cmp.b.scenario_name}</b>
            <button className="small ghost" onClick={() => downloadText("comparacion-escenarios.csv", compareCsv(cmp))}>Exportar CSV</button></div>
          <DataTable label="Comparación de escenarios" rows={cmp.rows} rowKey={(r) => `${r.kind}-${r.id}`} initialSort={{ key: "diff" }}
            columns={[
              { key: "kind", label: "Tipo", value: (r) => r.kind },
              { key: "id", label: "ID", value: (r) => r.id, className: "mono" },
              { key: "name", label: "Nombre", value: (r) => r.name ?? "" },
              { key: "a", label: "Antes (m)", type: "num", value: (r) => (r.supplied_a ? r.a : null), render: (r) => (r.supplied_a ? fmt(r.a, 2) : "sin agua") },
              { key: "b", label: "Después (m)", type: "num", value: (r) => (r.supplied_b ? r.b : null), render: (r) => (r.supplied_b ? fmt(r.b, 2) : "sin agua"),
                className: (r) => (r.supplied_b ? "" : "bad") },
              { key: "diff", label: "Diferencia (m)", type: "num", value: (r) => r.diff, render: (r) => fmt(r.diff, 2), className: (r) => (r.diff != null && r.diff < 0 ? "bad" : "") },
            ]} />
        </>
      ) : res && (
        <>
          <div className="summary">
            <span>Escenario: <b>{res.scenario_name}</b></span>
            <span>Clientes sin suministro: <b className={res.summary.clientes_sin_suministro ? "bad-text" : ""}>{res.summary.clientes_sin_suministro}</b></span>
            <span>Bajo {fmt(res.pressure_min, 0)} m: <b className={res.summary.clientes_bajo_minimo ? "warn-text" : ""}>{res.summary.clientes_bajo_minimo}</b></span>
            <span>Consumo sin suministro: <b>{fmt(res.summary.consumo_sin_suministro_lps, 3)} L/s</b></span>
            <span>Nudos sin suministro: <b>{res.summary.nudos_sin_suministro}</b></span>
            <button className="small ghost" disabled={!res.summary.afectados} onClick={() => downloadText(`afectados-${res.scenario}.csv`, affectedCsv(res))}>Exportar afectados (CSV)</button>
          </div>
          {res.clients.filter((c) => c.affected).length === 0 ? <p className="muted pad">Ningún cliente afectado.</p> : (
            <DataTable label="Clientes afectados" rows={res.clients.filter((c) => c.affected)} rowKey={(c) => c.id} onRowClick={(c) => gotoClient(c.id)}
              initialSort={{ key: "id" }}
              columns={[
                { key: "id", label: "Cliente", value: (c) => c.id, className: "mono" },
                { key: "name", label: "Nombre", value: (c) => c.name ?? "" },
                { key: "node", label: "Nudo", value: (c) => c.node, className: "mono" },
                { key: "q", label: "Consumo (L/s)", type: "num", value: (c) => c.consumption_lps, render: (c) => fmt(c.consumption_lps, 3) },
                { key: "sit", label: "Situación", value: (c) => (c.supplied ? "bajo la presión mínima" : "sin suministro"), className: (c) => (c.supplied ? "warn-text" : "bad-text") },
                { key: "p", label: "Presión (m)", type: "num", value: (c) => c.pressure, render: (c) => fmt(c.pressure, 2) },
              ]} />)}
        </>
      )}
    </>
  );
}
