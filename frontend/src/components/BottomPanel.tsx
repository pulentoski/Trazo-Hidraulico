import { useMemo, useState } from "react";
import { fmt, fmtTime } from "../lib/format";
import { useEditor } from "../state/store";

type Tab = "alerts" | "nodes" | "links" | "engine";
type SortKey = { col: string; dir: 1 | -1 };

interface AlertRow { sev: "error" | "warning"; origin: string; text: string; type?: string | null; id?: string | null }

export function BottomPanel() {
  const { result, validation, period, set, net, simError, focus } = useEditor();
  const [tab, setTab] = useState<Tab>("alerts");
  const [collapsed, setCollapsed] = useState(false);
  const [sort, setSort] = useState<SortKey>({ col: "id", dir: 1 });

  const byLabel = useMemo(() => {
    const m = { node: new Map<string, string>(), link: new Map<string, string>() };
    for (const n of Object.values(net.nodes)) m.node.set(n.id, n.uid);
    for (const l of Object.values(net.links)) m.link.set(l.id, l.uid);
    return m;
  }, [net]);

  const alerts: AlertRow[] = useMemo(() => {
    const rows: AlertRow[] = [];
    for (const i of validation?.errors ?? []) rows.push({ sev: "error", origin: "Validación", text: i.message, type: i.element_type, id: i.element_id });
    for (const m of result?.messages ?? []) rows.push({ sev: m.severity === "error" ? "error" : "warning", origin: "Motor", text: m.message, type: m.element_type, id: m.element_id });
    for (const a of result?.alerts ?? []) rows.push({ sev: "warning", origin: a.code === "BOTTLENECK" ? "Cuello de botella" : "Criterio", text: a.message, type: a.element_type, id: a.element_id });
    for (const i of validation?.warnings ?? []) rows.push({ sev: "warning", origin: "Validación", text: i.message, type: i.element_type, id: i.element_id });
    return rows;
  }, [validation, result]);

  const goto = (type?: string | null, id?: string | null) => {
    if (!id || (type !== "node" && type !== "link")) return;
    const uid = byLabel[type].get(id);
    if (uid) focus([uid]);
  };

  const sorted = <T extends Record<string, unknown>>(rows: T[]): T[] => [...rows].sort((a, b) => {
    const x = a[sort.col];
    const y = b[sort.col];
    if (typeof x === "number" && typeof y === "number") return (x - y) * sort.dir;
    return String(x).localeCompare(String(y), "es", { numeric: true }) * sort.dir;
  });
  const th = (col: string, label: string, num = false) => (
    <th className={num ? "num" : ""} onClick={() => setSort({ col, dir: sort.col === col ? (-sort.dir as 1 | -1) : 1 })}>
      {label}{sort.col === col ? (sort.dir === 1 ? " ▴" : " ▾") : ""}
    </th>
  );

  const nodeRows = useMemo(() => Object.values(net.nodes).map((n) => {
    const r = result?.nodes[n.id];
    return { uid: n.uid, id: n.id, kind: n.kind, elevation: n.props.elevation ?? NaN, demand: r?.demand[period] ?? NaN,
      head: r?.head[period] ?? NaN, pressure: r?.pressure[period] ?? NaN };
  }), [net.nodes, result, period]);
  const linkRows = useMemo(() => Object.values(net.links).map((l) => {
    const r = result?.links[l.id];
    return { uid: l.uid, id: l.id, kind: l.kind, dn: l.props.dn ?? NaN, d: l.props.inner_diameter_mm ?? NaN,
      length: l.props.length_hydraulic_m ?? NaN, flow: r?.flow[period] ?? NaN, velocity: r ? Math.abs(r.velocity[period]) : NaN,
      headloss: r ? Math.abs(r.headloss[period]) : NaN };
  }), [net.links, result, period]);

  const errors = alerts.filter((a) => a.sev === "error").length;
  const kindTxt: Record<string, string> = { junction: "nudo", reservoir: "reservorio", tank: "estanque", pipe: "tubería", pump: "bomba", valve: "válvula" };

  return (
    <section className={`bottom ${collapsed ? "collapsed" : ""}`}>
      <div className="tabs">
        <button className={tab === "alerts" ? "on" : ""} onClick={() => setTab("alerts")}>Alertas <span className={`count ${errors ? "bad" : alerts.length ? "warn" : ""}`}>{alerts.length}</span></button>
        <button className={tab === "nodes" ? "on" : ""} onClick={() => setTab("nodes")}>Nudos <span className="count">{nodeRows.length}</span></button>
        <button className={tab === "links" ? "on" : ""} onClick={() => setTab("links")}>Tramos <span className="count">{linkRows.length}</span></button>
        <button className={tab === "engine" ? "on" : ""} onClick={() => setTab("engine")}>Corrida</button>
        <div className="tabs-spacer" />
        {result && result.times.length > 1 && (
          <label className="period">
            <span>t = {fmtTime(result.times[period])}</span>
            <input type="range" min={0} max={result.times.length - 1} value={period} onChange={(e) => set({ period: Number(e.target.value) })} />
          </label>
        )}
        <button className="ghost small" onClick={() => setCollapsed(!collapsed)}>{collapsed ? "▴" : "▾"}</button>
      </div>
      {!collapsed && (
        <div className="tab-body">
          {tab === "alerts" && (
            alerts.length === 0 ? <p className="muted pad">{simError ?? (result ? "Sin alertas: la red cumple los criterios configurados." : "Sin resultados todavía.")}</p> : (
              <table className="tbl">
                <thead><tr><th style={{ width: 90 }}>Severidad</th><th style={{ width: 140 }}>Origen</th><th>Mensaje</th><th style={{ width: 90 }}>Elemento</th></tr></thead>
                <tbody>
                  {alerts.map((a, i) => (
                    <tr key={i} className={`clickable ${a.sev}`} onClick={() => goto(a.type, a.id)}>
                      <td><span className={`sev ${a.sev}`}>{a.sev === "error" ? "Error" : "Advertencia"}</span></td>
                      <td>{a.origin}</td><td>{a.text}</td><td className="mono">{a.id ?? ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )
          )}
          {tab === "nodes" && (
            <table className="tbl">
              <thead><tr>{th("id", "ID")}{th("kind", "Tipo")}{th("elevation", "Cota (m)", true)}{th("demand", "Demanda (L/s)", true)}{th("head", "Cota piez. (m)", true)}{th("pressure", "Presión (m)", true)}</tr></thead>
              <tbody>
                {sorted(nodeRows).map((r) => (
                  <tr key={r.uid} className="clickable" onClick={() => focus([r.uid])}>
                    <td className="mono">{r.id}</td><td>{kindTxt[r.kind]}</td><td className="num">{fmt(r.elevation, 2)}</td>
                    <td className="num">{fmt(r.demand, 3)}</td><td className="num">{fmt(r.head, 2)}</td>
                    <td className={`num ${r.pressure < 0 ? "bad" : ""}`}>{fmt(r.pressure, 2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {tab === "links" && (
            <table className="tbl">
              <thead><tr>{th("id", "ID")}{th("kind", "Tipo")}{th("dn", "DN", true)}{th("d", "D int. (mm)", true)}{th("length", "Largo (m)", true)}{th("flow", "Caudal (L/s)", true)}{th("velocity", "Velocidad (m/s)", true)}{th("headloss", "Pérdida (m/km)", true)}</tr></thead>
              <tbody>
                {sorted(linkRows).map((r) => (
                  <tr key={r.uid} className="clickable" onClick={() => focus([r.uid])}>
                    <td className="mono">{r.id}</td><td>{kindTxt[r.kind]}</td><td className="num">{Number.isNaN(r.dn) ? "—" : r.dn}</td>
                    <td className="num">{fmt(r.d, 1)}</td><td className="num">{fmt(r.length, 2)}</td><td className="num">{fmt(r.flow, 3)}</td>
                    <td className="num">{fmt(r.velocity, 3)}</td><td className="num">{r.kind === "pipe" ? fmt(r.headloss, 3) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {tab === "engine" && (
            <div className="pad engine-info">
              {result ? (
                <dl>
                  <dt>Versión del modelo</dt><dd>v{result.model_version}</dd>
                  <dt>Corrida</dt><dd className="mono">{result.run_id}{result.cached ? " (reutilizada)" : ""}</dd>
                  <dt>Estado</dt><dd>{{ ok: "correcta", warning: "con advertencias", error: "con errores" }[result.status]}</dd>
                  <dt>Motor</dt><dd>OWA-EPANET {result.engine.wheel_version} · {result.engine.runepanet_banner} · SHA <span className="mono">{result.engine.epanet_sha}</span></dd>
                  <dt>Opciones</dt><dd>{result.options.headloss} · {result.options.demand_model}{result.options.demand_model === "PDA" ? ` (Pmín ${result.options.minimum_pressure} m, Preq ${result.options.required_pressure} m, exp ${result.options.pressure_exponent})` : ""}</dd>
                  <dt>Huella del .inp</dt><dd className="mono">{result.inp_sha256.slice(0, 16)}…</dd>
                  <dt>Pasos de reporte</dt><dd>{result.times.length}</dd>
                  <dt>Tiempo de cálculo</dt><dd>{fmt(result.elapsed_ms, 0)} ms</dd>
                  <dt>Criterios</dt><dd>{result.profile_name ?? "—"} {result.profile_verified ? "" : "(no verificado)"}</dd>
                </dl>
              ) : <p className="muted">{simError ?? "Aún no hay una corrida para la versión actual."}</p>}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
