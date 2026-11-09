// Pestaña «Gráficos»: estanque, presión, caudal, curva de masas y perfil de presiones a lo largo de una ruta.
import { useMemo, useState } from "react";
import { fmt } from "../lib/format";
import { massCurve, routeLengthM, shortestRoute } from "../lib/charts";
import { hourLabel } from "../lib/patterns";
import { useEditor } from "../state/store";
import { Chart } from "./Chart";

type Kind = "tank" | "pressure" | "flow" | "mass" | "profile";
const KINDS: { id: Kind; label: string }[] = [
  { id: "tank", label: "Estanque: nivel y volumen" }, { id: "pressure", label: "Presión de un nudo o cliente" },
  { id: "flow", label: "Caudal de un tramo o bomba" }, { id: "mass", label: "Consumo contra bombeo (curva de masas)" },
  { id: "profile", label: "Perfil de presiones en una ruta" },
];
const byId = <T extends { id: string }>(xs: T[]) => [...xs].sort((a, b) => a.id.localeCompare(b.id, "es", { numeric: true }));

export function ChartsTab() {
  const { net, result, period, designParams, set } = useEditor();
  const [kind, setKind] = useState<Kind>("tank");
  const [el, setEl] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const pmin = designParams?.find((p) => p.key === "pressure_min")?.value as number | undefined;
  const tanks = byId(Object.values(net.nodes).filter((n) => n.kind === "tank"));
  const junctions = byId(Object.values(net.nodes).filter((n) => n.kind === "junction"));
  const clients = byId(Object.values(net.clients));
  const links = byId(Object.values(net.links));
  const allNodes = byId(Object.values(net.nodes));
  const route = useMemo(() => (from && to && from !== to ? shortestRoute(net, from, to) : null), [net, from, to]);
  if (!result) return <p className="muted pad">Simule el modelo para ver gráficos.</p>;
  const x = result.times.map((t) => t / 3600);
  const fx = (h: number) => hourLabel(h * 3600);
  const eps = result.times.length > 1;

  let body: React.ReactNode = null;
  if (kind === "tank") {
    const t = net.nodes[el] ?? tanks[0];
    if (!t) body = <p className="muted pad">El modelo no tiene estanques.</p>;
    else {
      const lv = result.nodes[t.id]?.pressure ?? [];
      const area = t.props.tank_diameter ? (Math.PI * t.props.tank_diameter ** 2) / 4 : null;
      body = (
        <Chart title={`Estanque ${t.id}: nivel${area ? " y volumen" : ""}`} x={x} xLabel="Hora" xFormat={fx} yLabel="Nivel (m)"
          series={[{ name: "Nivel", values: lv }]} right={area ? { factor: area, label: "Volumen (m³)" } : undefined}
          refLines={[...(t.props.max_level != null ? [{ value: t.props.max_level, label: "Nivel máximo" }] : []),
            ...(t.props.min_level != null ? [{ value: t.props.min_level, label: "Nivel mínimo", color: "#e07b00" }] : [])]}
          fileName={`estanque-${t.id}`} />
      );
    }
  } else if (kind === "pressure") {
    const c = net.clients[el];
    const n = c ? net.nodes[c.node] : net.nodes[el] ?? junctions[0];
    if (!n) body = <p className="muted pad">Sin nudos.</p>;
    else {
      const base = result.nodes[n.id]?.pressure ?? [];
      const adj = c && c.props.elevation != null && n.props.elevation != null ? n.props.elevation - c.props.elevation : 0;
      const name = c ? `cliente ${c.id} (nudo ${n.id})` : `nudo ${n.id}`;
      body = <Chart title={`Presión: ${name}`} x={x} xLabel="Hora" xFormat={fx} yLabel="Presión (m)" fileName={`presion-${c?.id ?? n.id}`}
        series={[{ name: "Presión", values: base.map((p) => p + adj) }]}
        refLines={pmin !== undefined ? [{ value: pmin, label: `Mínimo ${fmt(pmin, 0)} m` }] : []} />;
    }
  } else if (kind === "flow") {
    const l = net.links[el] ?? links.find((k) => k.kind === "pump") ?? links[0];
    if (!l) body = <p className="muted pad">Sin tramos.</p>;
    else body = <Chart title={`Caudal: ${l.kind === "pump" ? "bomba" : l.kind === "valve" ? "válvula" : "tramo"} ${l.id}`} x={x} xLabel="Hora" xFormat={fx}
      yLabel="Caudal (L/s)" step series={[{ name: "Caudal", values: result.links[l.id]?.flow ?? [] }]} fileName={`caudal-${l.id}`} />;
  } else if (kind === "mass") {
    const mc = massCurve(net, result);
    body = (<>
      <Chart title="Curva de masas: consumo y bombeo acumulados" x={x} xLabel="Hora" xFormat={fx} yLabel="Volumen acumulado (m³)"
        series={[{ name: "Consumo", values: mc.consumption }, { name: "Bombeo", values: mc.pumping }]} fileName="curva-de-masas" />
      <p className="muted small pad">Volumen de regulación por curva de masas (máx − mín de bombeo − consumo): <b>{fmt(mc.regulation, 1)} m³</b>.
        Consumo {fmt(mc.consumption[mc.consumption.length - 1], 1)} m³ · bombeo {fmt(mc.pumping[mc.pumping.length - 1], 1)} m³.</p>
    </>);
  } else {
    if (!route) body = <p className="muted pad">Elija el nudo inicial y el final de la ruta (se usa el camino más corto).</p>;
    else {
      const ids = route.nodes.map((u) => net.nodes[u]);
      const dist = route.dist;
      const head = ids.map((n) => result.nodes[n.id]?.head[period] ?? null);
      const pr = ids.map((n) => result.nodes[n.id]?.pressure[period] ?? null);
      const ground = ids.map((n) => n.props.elevation ?? null);
      const tlabel = hourLabel(result.times[period] ?? 0);
      body = (<>
        <Chart title={`Perfil ${ids[0].id} → ${ids[ids.length - 1].id} (${tlabel})`} x={dist} xLabel="Distancia (m)" xFormat={(v) => fmt(v, 0)}
          yLabel="Cota (m)" series={[{ name: "Cota piezométrica", values: head }, { name: "Terreno", values: ground, dashed: true }]}
          fileName={`perfil-cotas-${ids[0].id}-${ids[ids.length - 1].id}`} />
        <Chart title={`Presión a lo largo de la ruta (${tlabel})`} x={dist} xLabel="Distancia (m)" xFormat={(v) => fmt(v, 0)} yLabel="Presión (m)"
          series={[{ name: "Presión", values: pr }]} refLines={pmin !== undefined ? [{ value: pmin, label: `Mínimo ${fmt(pmin, 0)} m` }] : []}
          fileName={`perfil-presion-${ids[0].id}-${ids[ids.length - 1].id}`} />
        <p className="muted small pad">{ids.length} nudos · {fmt(routeLengthM(net, route.links), 0)} m. La hora se elige con el deslizador del mapa.
          <button className="small ghost" onClick={() => set({ highlight: [...route.nodes, ...route.links] })}>Resaltar en el mapa</button></p>
      </>);
    }
  }

  const elementSelect = kind === "tank" ? (
    <select value={el} onChange={(e) => setEl(e.target.value)}>{tanks.map((t) => <option key={t.uid} value={t.uid}>{t.id}</option>)}</select>
  ) : kind === "pressure" ? (
    <select value={el} onChange={(e) => setEl(e.target.value)}>
      <optgroup label="Nudos">{junctions.map((n) => <option key={n.uid} value={n.uid}>{n.id}</option>)}</optgroup>
      <optgroup label="Clientes">{clients.map((c) => <option key={c.uid} value={c.uid}>{c.id}{c.props.name ? ` · ${c.props.name}` : ""}</option>)}</optgroup>
    </select>
  ) : kind === "flow" ? (
    <select value={el} onChange={(e) => setEl(e.target.value)}>{links.map((l) => <option key={l.uid} value={l.uid}>{l.id} ({l.kind === "pump" ? "bomba" : l.kind === "valve" ? "válvula" : "tubería"})</option>)}</select>
  ) : kind === "profile" ? (<>
    <select value={from} onChange={(e) => setFrom(e.target.value)} aria-label="Desde"><option value="">Desde…</option>{allNodes.map((n) => <option key={n.uid} value={n.uid}>{n.id}</option>)}</select>
    <select value={to} onChange={(e) => setTo(e.target.value)} aria-label="Hasta"><option value="">Hasta…</option>{allNodes.map((n) => <option key={n.uid} value={n.uid}>{n.id}</option>)}</select>
  </>) : null;

  return (
    <div className="charts-tab">
      <div className="toolbar">
        <select value={kind} onChange={(e) => { setKind(e.target.value as Kind); setEl(""); }} aria-label="Tipo de gráfico">
          {KINDS.map((k) => <option key={k.id} value={k.id}>{k.label}</option>)}
        </select>
        {elementSelect}
        {!eps && kind !== "profile" && <span className="muted small">Simulación estática: configure 24 h en la pestaña Simulación para ver la variación horaria.</span>}
      </div>
      {body}
    </div>
  );
}
