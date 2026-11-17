import { useEffect, useMemo, useState } from "react";
import { fmt } from "../lib/format";
import { useAuth } from "../state/auth";
import type { DataColumn } from "./DataTable";
import { DataTable } from "./DataTable";
import { useEditor } from "../state/store";
import { DEFAULT_H, MIN_H, clampH, maxH, usePanelSize } from "./panelSize";
import type { TabDef } from "./TabBar";
import { TabBar } from "./TabBar";
import { Icon } from "./Icons";
import { SummaryTab } from "./SummaryTab";
import { ChartsTab } from "./ChartsTab";
import { ClientsTab } from "./ClientsTab";
import { DemandTab } from "./DemandTab";
import { DiagnosisTab } from "./DiagnosisTab";
import { MeasurementsTab } from "./MeasurementsTab";
import { SimulationTab } from "./SimulationTab";
import { HydrantsTab } from "./HydrantsTab";
import { LayersTab } from "./LayersTab";
import { QueryTab } from "./QueryTab";
import { ScenariosTab } from "./ScenariosTab";
import { SectorsTab } from "./SectorsTab";

type Tab = "summary" | "alerts" | "nodes" | "links" | "clients" | "scenarios" | "sectors" | "query" | "hydrants" | "layers" | "engine"
  | "simulation" | "demand" | "charts" | "diagnosis" | "measurements";
interface AlertRow { sev: "error" | "warning"; origin: string; text: string; type?: string | null; id?: string | null }

export function BottomPanel() {
  const { result, validation, period, set, net, simError, focus, bottomTab, bottomCollapsed: collapsed } = useEditor();
  const [tab, setTabState] = useState<Tab>("summary");
  const userId = useAuth((s) => s.me?.id ?? "");
  const { height, maximized, setSize, startDrag, dragging, sectionRef } = usePanelSize(userId, collapsed, (v) => set({ bottomCollapsed: v }));
  const setCollapsed = (v: boolean) => setSize({ collapsed: v });
  const setTab = (t: Tab) => { setTabState(t); set({ bottomTab: t }); };
  useEffect(() => {
    if (bottomTab && bottomTab !== tab) { setTabState(bottomTab as Tab); setCollapsed(false); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bottomTab]);

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
    if (!id) return;
    if (type === "client" || type === "shutoff" || type === "hydrant" || type === "well") {
      const pool = Object.values({ client: net.clients, shutoff: net.shutoffs, hydrant: net.hydrants, well: net.wells }[type]);
      const hit = pool.find((x) => x.id === id);
      if (hit) focus([hit.uid]);
      return;
    }
    if (type !== "node" && type !== "link") return;
    const uid = byLabel[type].get(id);
    if (uid) focus([uid]);
  };


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
  // Orden de uso: lo que se mira siempre primero; la configuración y las capas al final.
  const tabList: TabDef[] = [
    { id: "summary", label: "Resumen" },
    { id: "alerts", label: "Alertas", count: alerts.length, countCls: errors ? "bad" : alerts.length ? "warn" : "" },
    { id: "nodes", label: "Nudos", count: nodeRows.length },
    { id: "links", label: "Tramos", count: linkRows.length },
    { id: "clients", label: "Clientes", count: Object.keys(net.clients).length },
    { id: "simulation", label: "Simulación" },
    { id: "charts", label: "Gráficos" },
    { id: "diagnosis", label: "Diagnóstico" },
    { id: "scenarios", label: "Escenarios" },
    { id: "sectors", label: "Cuarteles" },
    { id: "demand", label: "Demanda" },
    { id: "measurements", label: "Mediciones" },
    { id: "query", label: "Consultas" },
    { id: "layers", label: "Capas" },
    { id: "hydrants", label: "Grifos", count: Object.keys(net.hydrants).length },
    { id: "engine", label: "Corrida" },
  ];
  const kindTxt: Record<string, string> = { junction: "nudo", reservoir: "reservorio", tank: "estanque", pipe: "tubería", pump: "bomba", valve: "válvula" };
  const pname = useEditor((st) => st.project?.name ?? "proyecto");
  type NodeRow = (typeof nodeRows)[number];
  type LinkRow = (typeof linkRows)[number];
  const alertCols: DataColumn<AlertRow>[] = [
    { key: "sev", label: "Severidad", width: 110, value: (a) => (a.sev === "error" ? "Error" : "Advertencia"),
      render: (a) => <span className={`sev ${a.sev}`}>{a.sev === "error" ? "Error" : "Advertencia"}</span> },
    { key: "origin", label: "Origen", width: 150, value: (a) => a.origin },
    { key: "text", label: "Mensaje", value: (a) => a.text },
    { key: "id", label: "Elemento", width: 110, value: (a) => a.id ?? "", className: "mono" },
  ];
  const nodeCols: DataColumn<NodeRow>[] = [
    { key: "id", label: "ID", value: (r) => r.id, className: "mono" },
    { key: "kind", label: "Tipo", value: (r) => kindTxt[r.kind] },
    { key: "elevation", label: "Cota (m)", type: "num", value: (r) => r.elevation, render: (r) => fmt(r.elevation, 2) },
    { key: "demand", label: "Demanda (L/s)", type: "num", value: (r) => r.demand, render: (r) => fmt(r.demand, 3) },
    { key: "head", label: "Cota piez. (m)", type: "num", value: (r) => r.head, render: (r) => fmt(r.head, 2) },
    { key: "pressure", label: "Presión (m)", type: "num", value: (r) => r.pressure, render: (r) => fmt(r.pressure, 2), className: (r) => (r.pressure < 0 ? "bad" : "") },
  ];
  const linkCols: DataColumn<LinkRow>[] = [
    { key: "id", label: "ID", value: (r) => r.id, className: "mono" },
    { key: "kind", label: "Tipo", value: (r) => kindTxt[r.kind] },
    { key: "dn", label: "DN", type: "num", value: (r) => r.dn, render: (r) => (Number.isNaN(r.dn) ? "—" : r.dn) },
    { key: "d", label: "D int. (mm)", type: "num", value: (r) => r.d, render: (r) => fmt(r.d, 1) },
    { key: "length", label: "Largo (m)", type: "num", value: (r) => r.length, render: (r) => fmt(r.length, 2) },
    { key: "flow", label: "Caudal (L/s)", type: "num", value: (r) => r.flow, render: (r) => fmt(r.flow, 3) },
    { key: "velocity", label: "Velocidad (m/s)", type: "num", value: (r) => r.velocity, render: (r) => fmt(r.velocity, 3) },
    { key: "headloss", label: "Pérdida (m/km)", type: "num", value: (r) => (r.kind === "pipe" ? r.headloss : NaN), render: (r) => (r.kind === "pipe" ? fmt(r.headloss, 3) : "—") },
  ];

  return (
    <section ref={sectionRef} className={`bottom ${collapsed ? "collapsed" : ""} ${maximized && !collapsed ? "maxed" : ""} ${dragging ? "dragging" : ""}`}
      aria-label="Panel inferior" style={collapsed ? undefined : { height: maximized ? undefined : height }}>
      {!collapsed && !maximized && (
        <div className="bottom-resize" role="separator" aria-orientation="horizontal" aria-label="Cambiar la altura del panel inferior"
          aria-valuenow={Math.round(height)} aria-valuemin={MIN_H} aria-valuemax={Math.round(maxH())} tabIndex={0}
          title="Arrastre para cambiar la altura (doble clic: tamaño normal)" onPointerDown={startDrag}
          onDoubleClick={() => setSize({ height: DEFAULT_H })}
          onKeyDown={(e) => {
            if (e.key === "ArrowUp") { e.preventDefault(); setSize({ height: clampH(height + 24) }); }
            if (e.key === "ArrowDown") { e.preventDefault(); setSize({ height: clampH(height - 24) }); }
          }}><i /></div>
      )}
      <TabBar tabs={tabList} active={tab} onPick={(id) => setTab(id as Tab)}
        controls={(
          <div className="panel-size" role="group" aria-label="Tamaño del panel inferior">
            <button className={`ghost small ${collapsed ? "on" : ""}`} onClick={() => setSize({ collapsed: !collapsed, maximized: false })} aria-pressed={collapsed}
              aria-label={collapsed ? "Desplegar el panel inferior" : "Plegar el panel inferior"} title={collapsed ? "Desplegar el panel inferior" : "Plegar el panel inferior (más espacio para el mapa)"}>
              <Icon.minus /></button>
            <button className={`ghost small ${!collapsed && !maximized ? "on" : ""}`} onClick={() => setSize({ collapsed: false, maximized: false })}
              aria-label="Tamaño normal del panel inferior" title="Tamaño normal">
              <Icon.square /></button>
            <button className={`ghost small ${maximized && !collapsed ? "on" : ""}`} onClick={() => setSize({ collapsed: false, maximized: !maximized || collapsed })}
              aria-label="Maximizar el panel inferior" title="Maximizar (deja el mapa visible arriba)">
              <Icon.maximize /></button>
          </div>
        )} />
      {!collapsed && (
        <div className="tab-body" key={tab}>
          {tab === "summary" && <SummaryTab />}
          {tab === "alerts" && (
            alerts.length === 0 ? <p className="muted pad">{simError ?? (result ? "Sin alertas: la red cumple los criterios configurados." : "Sin resultados todavía.")}</p> : (
              <DataTable label="Alertas" rows={alerts} columns={alertCols} rowKey={(_, i) => String(i)} rowClassName={(a) => a.sev}
                onRowClick={(a) => goto(a.type, a.id)} exportName={`alertas-${pname}`} />
            )
          )}
          {tab === "nodes" && (
            <DataTable label="Nudos" rows={nodeRows} columns={nodeCols} rowKey={(r) => r.uid} initialSort={{ key: "id" }}
              onRowClick={(r) => focus([r.uid])} exportName={`nudos-${pname}`} empty={<p className="muted pad">Sin nudos.</p>} />
          )}
          {tab === "links" && (
            <DataTable label="Tramos" rows={linkRows} columns={linkCols} rowKey={(r) => r.uid} initialSort={{ key: "id" }}
              onRowClick={(r) => focus([r.uid])} exportName={`tramos-${pname}`} empty={<p className="muted pad">Sin tramos.</p>} />
          )}
          {tab === "clients" && <ClientsTab />}
          {tab === "scenarios" && <ScenariosTab />}
          {tab === "sectors" && <SectorsTab />}
          {tab === "simulation" && <SimulationTab />}
          {tab === "demand" && <DemandTab />}
          {tab === "charts" && <ChartsTab />}
          {tab === "diagnosis" && <DiagnosisTab />}
          {tab === "measurements" && <MeasurementsTab />}
          {tab === "query" && <QueryTab />}
          {tab === "hydrants" && <HydrantsTab />}
          {tab === "layers" && <LayersTab />}
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
