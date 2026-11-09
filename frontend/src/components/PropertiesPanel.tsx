import { useMemo } from "react";
import { api } from "../api/client";
import type { CatalogPipe, HydraulicOptions } from "../api/types";
import { fmt, fmtLen } from "../lib/format";
import type { ELink, ENode, LinkProps, Network, NodeProps } from "../lib/network";
import { ROUGHNESS_LABEL, estimatedLength, roughnessFor, tankStorage } from "../lib/network";
import { useEditor } from "../state/store";
import { NumField, Readout, TextField } from "./Fields";

const ID_RE = /^[^\s;"]{1,31}$/;
const KIND_LABEL = { junction: "Nudo de consumo", reservoir: "Reservorio", tank: "Estanque", pipe: "Tubería", pump: "Bomba", valve: "Válvula" };
const SOURCE_LABEL = { manual: "Manual", inp: "Importada (.inp)", supuesta: "Supuesta en la importación (por verificar)" };
const STATUS_TXT: Record<number, string> = { 0: "cerrada (sin altura)", 1: "cerrado temporalmente", 2: "cerrado", 3: "abierto", 4: "activa", 5: "sobre caudal máx.", 6: "sin caudal de consigna", 7: "sin presión de consigna" };

function updateNode(uid: string, patch: { id?: string; props?: Partial<NodeProps> }) {
  useEditor.getState().commit((n) => {
    const cur = n.nodes[uid];
    return { ...n, nodes: { ...n.nodes, [uid]: { ...cur, ...patch, props: { ...cur.props, ...(patch.props ?? {}) } } } };
  });
}

function updateLinks(uids: string[], patch: Partial<LinkProps>, other?: Partial<ELink>) {
  useEditor.getState().commit((n) => {
    const links = { ...n.links };
    for (const u of uids) if (links[u]) links[u] = { ...links[u], ...(other ?? {}), props: { ...links[u].props, ...patch } };
    return { ...n, links };
  });
}

function catalogPatch(item: CatalogPipe, formula: HydraulicOptions["headloss"]): Partial<LinkProps> {
  return {
    material: item.material, pipe_class: item.pipe_class, dn: item.dn, catalog_pipe_id: item.id,
    inner_diameter_mm: item.inner_diameter_mm, roughness: roughnessFor(formula, item),
  };
}

function idError(net: Network, kind: "node" | "link", uid: string, id: string): string | null {
  if (!ID_RE.test(id)) return "Máx. 31 caracteres, sin espacios, «;» ni comillas.";
  const pool = kind === "node" ? Object.values(net.nodes) : Object.values(net.links);
  if (pool.some((e) => e.uid !== uid && e.id === id)) return "Ya existe otro elemento con ese ID.";
  return null;
}

function Issues({ id, type }: { id: string; type: "node" | "link" }) {
  const { validation, result } = useEditor();
  const items = [
    ...(validation?.errors ?? []).filter((i) => i.element_id === id && i.element_type === type).map((i) => ({ t: "error", m: i.message })),
    ...(validation?.warnings ?? []).filter((i) => i.element_id === id && i.element_type === type).map((i) => ({ t: "warning", m: i.message })),
    ...(result?.alerts ?? []).filter((a) => a.element_id === id && a.element_type === type).map((a) => ({ t: "warning", m: a.message })),
    ...(result?.messages ?? []).filter((m) => m.element_id === id).map((m) => ({ t: m.severity, m: m.message })),
  ];
  if (!items.length) return null;
  return <ul className="issues">{items.map((i, k) => <li key={k} className={i.t}>{i.m}</li>)}</ul>;
}

function NodePanel({ node }: { node: ENode }) {
  const { net, result, period } = useEditor();
  const p = node.props;
  const r = result?.nodes[node.id];
  const setElev = (v: number | null) =>
    updateNode(node.uid, { props: { elevation: v, elevation_source: "manual", elevation_method: v === null ? null : "Ingreso manual" } });
  const tank = node.kind === "tank" ? tankStorage(p, r?.pressure[period]) : null;
  return (
    <>
      <h3>{KIND_LABEL[node.kind]} <code>{node.id}</code></h3>
      <TextField label="ID" value={node.id} error={null} onCommit={(v) => {
        const err = idError(net, "node", node.uid, v);
        if (err) useEditor.getState().toast(err, "error");
        else updateNode(node.uid, { id: v });
      }} />
      <div className="coords">{fmt(node.pos[1], 6)}°, {fmt(node.pos[0], 6)}° (WGS84)</div>
      <fieldset>
        <legend>Cota</legend>
        <NumField label={node.kind === "tank" ? "Cota de fondo" : "Cota de terreno"} unit="m" value={p.elevation} allowNull onCommit={setElev} invalid={p.elevation == null}
          hint={p.elevation == null ? "Sin cota: ingrésela para poder simular" : undefined} />
        {p.elevation == null && <ul className="issues"><li className="error">Falta la cota: es obligatoria para simular.</li></ul>}
        {p.elevation_source === "supuesta" && <ul className="issues"><li className="warning">Cota supuesta en la importación{p.elevation_method ? ` (${p.elevation_method})` : ""}: ingrese la cota real.</li></ul>}
        <label className="field"><span>Fuente</span>
          <select value={p.elevation_source} onChange={(e) => updateNode(node.uid, { props: { elevation_source: e.target.value as NodeProps["elevation_source"] } })}>
            {Object.entries(SOURCE_LABEL).filter(([k]) => k !== "supuesta" || p.elevation_source === "supuesta").map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </label>
        <TextField label="Método" value={p.elevation_method} placeholder="Ej.: levantamiento GNSS, plano…" onCommit={(v) => updateNode(node.uid, { props: { elevation_method: v || null } })} />
      </fieldset>
      {node.kind === "junction" && (
        <fieldset>
          <legend>Demanda</legend>
          <NumField label="Demanda base" unit="L/s" value={p.base_demand} onCommit={(v) => updateNode(node.uid, { props: { base_demand: v ?? 0 } })} />
          <TextField label="Patrón" value={p.demand_pattern} placeholder="(ninguno)" onCommit={(v) => updateNode(node.uid, { props: { demand_pattern: v || null } })} />
          {(p.demands?.length ?? 0) > 0 && <div className="muted">+ {p.demands!.length} categorías de demanda adicionales (importadas)</div>}
        </fieldset>
      )}
      {node.kind === "reservoir" && (
        <fieldset>
          <legend>Reservorio</legend>
          <NumField label="Carga total (nivel)" unit="m" value={p.head} allowNull invalid={p.head == null} onCommit={(v) => updateNode(node.uid, { props: { head: v } })} />
        </fieldset>
      )}
      {node.kind === "tank" && (
        <fieldset>
          <legend>Estanque</legend>
          <NumField label="Nivel inicial" unit="m" value={p.init_level} allowNull onCommit={(v) => updateNode(node.uid, { props: { init_level: v } })} />
          <NumField label="Nivel mínimo" unit="m" value={p.min_level} allowNull onCommit={(v) => updateNode(node.uid, { props: { min_level: v } })} />
          <NumField label="Nivel máximo" unit="m" value={p.max_level} allowNull onCommit={(v) => updateNode(node.uid, { props: { max_level: v } })} />
          <NumField label="Diámetro" unit="m" value={p.tank_diameter} allowNull onCommit={(v) => updateNode(node.uid, { props: { tank_diameter: v } })} />
          <NumField label="Volumen mínimo" unit="m³" value={p.min_volume} allowNull onCommit={(v) => updateNode(node.uid, { props: { min_volume: v } })} />
          <Readout label="Cota de rebalse (fondo + nivel máx.)" value={fmt(tank?.overflowElevation, 2)} unit="m" />
        </fieldset>
      )}
      {r && (
        <fieldset className="results">
          <legend>Resultados {result!.times.length > 1 ? `(t = ${Math.round(result!.times[period] / 360) / 10} h)` : ""}</legend>
          {node.kind === "tank" ? (<>
            <Readout label="Nivel de agua" value={fmt(r.pressure[period], 2)} unit="m" />
            <Readout label="Volumen almacenado" value={fmt(tank?.volume, 1)} unit="m³" />
          </>) : <Readout label="Presión" value={fmt(r.pressure[period], 2)} unit="m" tone={r.pressure[period] < 0 ? "bad" : ""} />}
          <Readout label="Cota piezométrica" value={fmt(r.head[period], 2)} unit="m" />
          <Readout label={node.kind === "junction" ? "Demanda" : "Aporte (−) / consumo (+)"} value={fmt(r.demand[period], 3)} unit="L/s" />
        </fieldset>
      )}
      <Issues id={node.id} type="node" />
    </>
  );
}

function PipeSelect({ links, catalog, formula }: { links: ELink[]; catalog: CatalogPipe[]; formula: HydraulicOptions["headloss"] }) {
  const first = links[0].props;
  const material = first.catalog_pipe_id ? first.material ?? "PVC" : "custom";
  const classes = [...new Set(catalog.filter((c) => c.material === material).map((c) => c.pipe_class))];
  const cls = first.pipe_class && classes.includes(first.pipe_class) ? first.pipe_class : classes[0];
  const dns = catalog.filter((c) => c.material === material && c.pipe_class === cls);
  const uids = links.map((l) => l.uid);
  const apply = (m: string, c: string | undefined, dn: number | undefined) => {
    if (m === "custom") return updateLinks(uids, { catalog_pipe_id: null, material: null, pipe_class: null });
    const pool = catalog.filter((x) => x.material === m);
    const cc = c && pool.some((x) => x.pipe_class === c) ? c : pool[0]?.pipe_class;
    const options = pool.filter((x) => x.pipe_class === cc);
    const item = options.find((x) => x.dn === dn) ?? options.reduce<CatalogPipe | undefined>((best, x) =>
      !best || Math.abs(x.dn - (dn ?? 110)) < Math.abs(best.dn - (dn ?? 110)) ? x : best, undefined);
    if (item) updateLinks(uids, catalogPatch(item, formula));
  };
  const verified = catalog.find((c) => c.id === first.catalog_pipe_id)?.verified;
  return (
    <fieldset>
      <legend>Tubería {links.length > 1 ? `(${links.length} tramos)` : ""}</legend>
      <div className="row3">
        <label className="field"><span>Material</span>
          <select value={material} onChange={(e) => apply(e.target.value, cls, first.dn ?? undefined)}>
            {[...new Set(catalog.map((c) => c.material))].map((m) => <option key={m} value={m}>{m}</option>)}
            <option value="custom">Otro / personalizado</option>
          </select>
        </label>
        {material !== "custom" && (<>
          <label className="field"><span>Clase</span>
            <select value={cls} onChange={(e) => apply(material, e.target.value, first.dn ?? undefined)}>
              {classes.map((c) => <option key={c}>{c}</option>)}
            </select>
          </label>
          <label className="field"><span>DN</span>
            <select value={first.dn ?? ""} onChange={(e) => apply(material, cls, Number(e.target.value))}>
              {dns.map((d) => <option key={d.id} value={d.dn}>{d.dn}</option>)}
            </select>
          </label>
        </>)}
      </div>
      {material !== "custom" && verified === false && <div className="muted small">Catálogo referencial (no verificado).</div>}
      <NumField label="Diámetro interior" unit="mm" value={first.inner_diameter_mm} allowNull disabled={material !== "custom"}
        onCommit={(v) => updateLinks(uids, { inner_diameter_mm: v })} />
      <NumField label={ROUGHNESS_LABEL[formula]} value={first.roughness} allowNull digits={4} disabled={material !== "custom"}
        onCommit={(v) => updateLinks(uids, { roughness: v })} hint="El significado depende de la fórmula de pérdida del proyecto" />
      <NumField label="Coef. pérdidas menores" value={first.minor_loss} onCommit={(v) => updateLinks(uids, { minor_loss: v ?? 0 })} />
      <label className="field"><span>Estado inicial</span>
        <select value={first.initial_status} onChange={(e) => updateLinks(uids, { initial_status: e.target.value as LinkProps["initial_status"] })}>
          <option value="open">Abierta</option><option value="closed">Cerrada</option><option value="cv">Con válvula de retención</option>
        </select>
      </label>
    </fieldset>
  );
}

function LinkPanel({ link }: { link: ELink }) {
  const { net, catalog, options, result, period } = useEditor();
  const p = link.props;
  const r = result?.links[link.id];
  const from = net.nodes[link.from];
  const to = net.nodes[link.to];
  const est = estimatedLength(net, link);
  return (
    <>
      <h3>{KIND_LABEL[link.kind]} <code>{link.id}</code></h3>
      <TextField label="ID" value={link.id} onCommit={(v) => {
        const err = idError(net, "link", link.uid, v);
        if (err) useEditor.getState().toast(err, "error");
        else updateLinks([link.uid], {}, { id: v });
      }} />
      <div className="topo">
        <span>{from?.id}</span> → <span>{to?.id}</span>
        <button className="ghost small" title="Invertir sentido (nudo inicial ↔ final)" onClick={() => updateLinks([link.uid], {}, { from: link.to, to: link.from, vertices: [...link.vertices].reverse() })}>⇄ invertir</button>
      </div>
      {link.kind === "pipe" ? (
        <>
          <PipeSelect links={[link]} catalog={catalog} formula={options.headloss} />
          <fieldset>
            <legend>Largos</legend>
            <Readout label="En planta" value={fmtLen(p.length_plan_m ?? est)} />
            <Readout label="Con pendiente" value={fmtLen(p.length_slope_m)} />
            <label className="field"><span>Largo hidráulico usado</span>
              <select value={p.length_choice} onChange={(e) => {
                const choice = e.target.value as LinkProps["length_choice"];
                const geo = choice === "plan" ? p.length_plan_m ?? est : choice === "slope" ? p.length_slope_m ?? est : p.length_hydraulic_m ?? est;
                updateLinks([link.uid], { length_choice: choice, length_hydraulic_m: geo });
              }}>
                <option value="slope">Con pendiente (desde cotas)</option>
                <option value="plan">En planta</option>
                <option value="manual">Manual</option>
              </select>
            </label>
            <NumField label="Largo hidráulico (enviado al motor)" unit="m" value={p.length_hydraulic_m} allowNull invalid={!p.length_hydraulic_m}
              hint="Escriba un largo para fijarlo a mano: prevalece sobre el geométrico"
              onCommit={(v) => updateLinks([link.uid], { length_hydraulic_m: v, length_choice: "manual" })} />
          </fieldset>
        </>
      ) : link.kind === "pump" ? (
        <fieldset><legend>Bomba</legend>
          <Readout label="Curva" value={p.pump_curve ?? (p.pump_power ? `potencia ${fmt(p.pump_power, 1)} kW` : "—")} />
          <NumField label="Velocidad relativa" value={p.pump_speed ?? 1} onCommit={(v) => updateLinks([link.uid], { pump_speed: v })} />
          <label className="field"><span>Estado inicial</span>
            <select value={p.initial_status} onChange={(e) => updateLinks([link.uid], { initial_status: e.target.value as LinkProps["initial_status"] })}>
              <option value="open">En operación</option><option value="closed">Detenida</option>
            </select>
          </label>
        </fieldset>
      ) : (
        <fieldset><legend>Válvula {p.valve_type}</legend>
          <NumField label="Diámetro" unit="mm" value={p.inner_diameter_mm} onCommit={(v) => updateLinks([link.uid], { inner_diameter_mm: v })} />
          <NumField label="Consigna" value={p.valve_setting} allowNull onCommit={(v) => updateLinks([link.uid], { valve_setting: v })} />
        </fieldset>
      )}
      {r && (
        <fieldset className="results">
          <legend>Resultados</legend>
          <Readout label="Caudal" value={fmt(r.flow[period], 3)} unit="L/s" />
          <Readout label="Velocidad" value={fmt(Math.abs(r.velocity[period]), 3)} unit="m/s" />
          <Readout label={link.kind === "pipe" ? "Pérdida unitaria" : "Pérdida / ganancia"} value={fmt(link.kind === "pipe" ? Math.abs(r.headloss[period]) : r.headloss[period], 3)} unit={link.kind === "pipe" ? "m/km" : "m"} />
          <Readout label="Estado" value={STATUS_TXT[r.status[period]] ?? String(r.status[period])} />
        </fieldset>
      )}
      <Issues id={link.id} type="link" />
    </>
  );
}

function MultiPanel({ uids }: { uids: string[] }) {
  const { net, catalog, options, requestDelete } = useEditor();
  const nodes = uids.filter((u) => net.nodes[u]).length;
  const pipes = uids.map((u) => net.links[u]).filter((l): l is ELink => !!l && l.kind === "pipe");
  return (
    <>
      <h3>Selección múltiple</h3>
      <p>{nodes} nudos · {pipes.length} tuberías · {uids.length - nodes - pipes.length} otros</p>
      {pipes.length > 0 && <PipeSelect links={pipes} catalog={catalog} formula={options.headloss} />}
      <button className="danger" onClick={() => requestDelete(uids)}>Eliminar selección…</button>
    </>
  );
}

function ProjectPanel() {
  const { project, options, profiles, engine, catalog, setOptions, toast, set, net } = useEditor();
  const profile = profiles.find((p) => p.id === project?.design_profile_id);
  const counts = useMemo(() => {
    const ls = Object.values(net.links);
    return { nodes: Object.keys(net.nodes).length, pipes: ls.filter((l) => l.kind === "pipe").length,
      km: ls.reduce((s, l) => s + (l.props.length_hydraulic_m ?? 0), 0) / 1000 };
  }, [net]);
  if (!project) return <p className="muted">Abra o cree un proyecto.</p>;

  const changeFormula = (formula: HydraulicOptions["headloss"]) => {
    let updated = 0;
    let custom = 0;
    setOptions({ ...options, headloss: formula }, (n) => {
      const links = { ...n.links };
      for (const [k, l] of Object.entries(links)) {
        if (l.kind !== "pipe") continue;
        const item = catalog.find((c) => c.id === l.props.catalog_pipe_id);
        if (item) {
          links[k] = { ...l, props: { ...l.props, roughness: roughnessFor(formula, item) } };
          updated++;
        } else custom++;
      }
      return { ...n, links };
    });
    toast(`Fórmula ${formula}: rugosidad actualizada en ${updated} tramos de catálogo.` +
      (custom ? ` Revise ${custom} tramos sin catálogo: su rugosidad cambia de significado.` : ""), custom ? "error" : "info");
  };

  return (
    <>
      <h3>Proyecto</h3>
      <TextField label="Nombre" value={project.name} onCommit={async (v) => {
        if (!v.trim()) return;
        const p = await api.updateProject(project.id, { name: v.trim() });
        set({ project: p });
      }} />
      <div className="muted small">{counts.nodes} nudos · {counts.pipes} tuberías · {fmt(counts.km, 2)} km · largos en EPSG:{project.length_srid}</div>
      <fieldset>
        <legend>Opciones hidráulicas</legend>
        <label className="field"><span>Fórmula de pérdida</span>
          <select value={options.headloss} onChange={(e) => changeFormula(e.target.value as HydraulicOptions["headloss"])}>
            <option value="H-W">Hazen-Williams (C)</option>
            <option value="D-W">Darcy-Weisbach (ε, mm)</option>
            <option value="C-M">Chezy-Manning (n)</option>
          </select>
        </label>
        <label className="field"><span>Análisis de demanda</span>
          <select value={options.demand_model} onChange={(e) => setOptions({ ...options, demand_model: e.target.value as HydraulicOptions["demand_model"] })}>
            <option value="DDA">Por demanda (DDA)</option>
            <option value="PDA">Por presión (PDA)</option>
          </select>
        </label>
        {options.demand_model === "PDA" && (<>
          <NumField label="Presión mínima" unit="m" value={options.minimum_pressure} onCommit={(v) => setOptions({ ...options, minimum_pressure: v ?? 0 })} />
          <NumField label="Presión requerida" unit="m" value={options.required_pressure} onCommit={(v) => setOptions({ ...options, required_pressure: v ?? 15 })} />
          <NumField label="Exponente" value={options.pressure_exponent} onCommit={(v) => setOptions({ ...options, pressure_exponent: v ?? 0.5 })} />
        </>)}
      </fieldset>
      {profile && (
        <fieldset>
          <legend>Criterios de diseño {profile.verified ? "" : <span className="badge warn">no verificado</span>}</legend>
          <div className="muted small">{profile.name} · v{profile.version} · vigente desde {profile.valid_from}</div>
          <table className="tbl compact">
            <tbody>
              {profile.criteria.map((c) => (
                <tr key={c.key}><td>{c.label}</td><td className="num">{c.min != null ? `≥ ${fmt(c.min, 1)}` : ""}{c.max != null ? `≤ ${fmt(c.max, 1)}` : ""} {c.unit}</td></tr>
              ))}
            </tbody>
          </table>
          <div className="muted small">{profile.source}</div>
        </fieldset>
      )}
      {engine && (
        <fieldset>
          <legend>Motor hidráulico</legend>
          <div className="small">OWA-EPANET {engine.wheel_version} · tag {engine.epanet_tag}</div>
          <div className="small mono" title={engine.epanet_sha ?? ""}>SHA {engine.epanet_sha?.slice(0, 12)}</div>
        </fieldset>
      )}
    </>
  );
}

export function PropertiesPanel() {
  const { selection, net } = useEditor();
  let body: React.ReactNode;
  if (selection.length > 1) body = <MultiPanel uids={selection} />;
  else if (selection.length === 1 && net.nodes[selection[0]]) body = <NodePanel node={net.nodes[selection[0]]} />;
  else if (selection.length === 1 && net.links[selection[0]]) body = <LinkPanel link={net.links[selection[0]]} />;
  else body = <ProjectPanel />;
  return <aside className="props" aria-label="Propiedades">{body}</aside>;
}
