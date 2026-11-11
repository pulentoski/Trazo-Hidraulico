import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { CatalogPipe, HydraulicOptions } from "../api/types";
import { fmt, fmtLen, parseNum } from "../lib/format";
import type { EClient, ELink, ENode, EShutoff, LinkProps, Network, NodeProps } from "../lib/network";
import { ROUGHNESS_LABEL, estimatedLength, nodeDemand, roughnessFor, tankStorage, toLps } from "../lib/network";
import { errorText } from "../state/projects";
import { CLIENT_TYPES } from "./ClientDialog";
import { useEditor } from "../state/store";
import { Attributes, ClientManagement, HydrantPanel, PipeManagement, ShutoffManagement, WellPanel } from "./AssetPanels";
import { FieldLabel, Help, NumField, Readout, TextField } from "./Fields";
import { PumpOperation } from "./PumpOperation";
import { useAuth } from "../state/auth";
import { useSections } from "../state/sections";
import { ExpandAll, Section } from "./Section";

const ID_RE = /^[^\s;"]{1,31}$/;
const KIND_LABEL = { junction: "Nudo de consumo", reservoir: "Reservorio", tank: "Estanque", pipe: "Tubería", pump: "Bomba", valve: "Válvula" };
const SOURCE_LABEL = { manual: "Manual", inp: "Importada (.inp)", supuesta: "Supuesta en la importación (por verificar)" };
/** Ayudas de los campos técnicos. */
export const HELP = {
  elevationGround: "Cota del terreno en el nudo (m). La presión es cota piezométrica − cota de terreno. Es obligatoria: no se supone.",
  elevationTank: "Cota del fondo del estanque (m). Los niveles se miden desde aquí: cota piezométrica = cota de fondo + nivel de agua.",
  initLevel: "Altura de agua sobre el fondo al inicio de la simulación (m). Debe estar entre el nivel mínimo y el máximo.",
  minLevel: "Nivel mínimo sobre el fondo (m): bajo él el estanque se considera vacío y deja de entregar agua.",
  maxLevel: "Nivel máximo sobre el fondo (m): nivel de rebalse; sobre él el estanque no recibe más agua.",
  tankDiameter: "Diámetro interior del estanque cilíndrico (m). Define el área: volumen = área × altura de agua.",
  minVolume: "Volumen bajo el nivel mínimo (m³), p. ej. por fondo no cilíndrico. Con 0, EPANET usa área × nivel mínimo.",
  overflow: "Cota del nivel máximo = cota de fondo + nivel máximo (m).",
  waterLevel: "Altura del agua sobre el fondo del estanque (m) en el periodo mostrado.",
  storedVolume: "Volumen de agua almacenado en el periodo mostrado (m³), calculado como EPANET: Vmín + área × (nivel − nivel mínimo).",
  baseDemand: "Consumo medio del nudo (L/s). Se multiplica por el patrón horario, si lo hay. En PDA la entrega depende de la presión.",
  roughness: {
    "H-W": "Coeficiente C de Hazen-Williams (adimensional): mayor C, menos pérdida. PVC/HDPE nuevos ≈ 150.",
    "D-W": "Rugosidad absoluta ε de Darcy-Weisbach en milímetros (mm). PVC ≈ 0,0015 mm; HDPE ≈ 0,007 mm.",
    "C-M": "Coeficiente n de Manning (s/m^1/3). PVC ≈ 0,009.",
  } as Record<string, string>,
  dn: "DN: diámetro nominal comercial (en PVC y HDPE coincide con el diámetro exterior). No es el de cálculo.",
  innerDiameter: "Diámetro interior que usa el motor: diámetro exterior − 2 × espesor, según material y clase. Con catálogo se fija automáticamente.",
  lengthChoice: "Origen del largo hidráulico: con pendiente (planta + desnivel entre cotas), en planta, o manual.",
  lengthHydraulic: "Largo que se envía al motor (m). Escriba un valor para fijarlo a mano: prevalece sobre el largo geométrico.",
};

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
    inner_diameter_mm: item.inner_diameter_mm, roughness: roughnessFor(formula, item), inner_diameter_source: "catalogo",
  };
}

function idError(net: Network, kind: "node" | "link", uid: string, id: string): string | null {
  if (!ID_RE.test(id)) return "Máx. 31 caracteres, sin espacios, «;» ni comillas.";
  const pool = kind === "node" ? Object.values(net.nodes) : Object.values(net.links);
  if (pool.some((e) => e.uid !== uid && e.id === id)) return "Ya existe otro elemento con ese ID.";
  return null;
}

function Issues({ id, type }: { id: string; type: "node" | "link" | "client" }) {
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
      <Section id="nudo.cota" title="Cota" primary={!r && node.kind === "junction"}>
        <NumField label={node.kind === "tank" ? "Cota de fondo" : "Cota de terreno"} unit="m" value={p.elevation} allowNull onCommit={setElev} invalid={p.elevation == null}
          hint={node.kind === "tank" ? HELP.elevationTank : HELP.elevationGround} />
        {p.elevation == null && <ul className="issues"><li className="error">Falta la cota: es obligatoria para simular.</li></ul>}
        {p.elevation_source === "supuesta" && <ul className="issues"><li className="warning">Cota supuesta en la importación{p.elevation_method ? ` (${p.elevation_method})` : ""}: ingrese la cota real.</li></ul>}
        <label className="field"><span>Fuente</span>
          <select value={p.elevation_source} onChange={(e) => updateNode(node.uid, { props: { elevation_source: e.target.value as NodeProps["elevation_source"] } })}>
            {Object.entries(SOURCE_LABEL).filter(([k]) => k !== "supuesta" || p.elevation_source === "supuesta").map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </label>
        <TextField label="Método" value={p.elevation_method} placeholder="Ej.: levantamiento GNSS, plano…" onCommit={(v) => updateNode(node.uid, { props: { elevation_method: v || null } })} />
      </Section>
      {node.kind === "junction" && (
        <Section id="nudo.demanda" title="Demanda">
          <NumField label="Demanda base" unit="L/s" hint={HELP.baseDemand} value={p.base_demand} onCommit={(v) => updateNode(node.uid, { props: { base_demand: v ?? 0 } })} />
          <TextField label="Patrón" value={p.demand_pattern} placeholder="(ninguno)" onCommit={(v) => updateNode(node.uid, { props: { demand_pattern: v || null } })} />
          {(p.demands?.length ?? 0) > 0 && <div className="muted">+ {p.demands!.length} categorías de demanda adicionales (importadas)</div>}
          <DemandBreakdown nodeUid={node.uid} />
        </Section>
      )}
      {node.kind === "reservoir" && (
        <Section id="nudo.reservorio" title="Reservorio" primary={!r}>
          <NumField label="Carga total (nivel)" unit="m" value={p.head} allowNull invalid={p.head == null} onCommit={(v) => updateNode(node.uid, { props: { head: v } })} />
        </Section>
      )}
      {node.kind === "tank" && (
        <Section id="nudo.estanque" title="Estanque" primary={!r}>
          <NumField label="Nivel inicial" unit="m" hint={HELP.initLevel} value={p.init_level} allowNull onCommit={(v) => updateNode(node.uid, { props: { init_level: v } })} />
          <NumField label="Nivel mínimo" unit="m" hint={HELP.minLevel} value={p.min_level} allowNull onCommit={(v) => updateNode(node.uid, { props: { min_level: v } })} />
          <NumField label="Nivel máximo" unit="m" hint={HELP.maxLevel} value={p.max_level} allowNull onCommit={(v) => updateNode(node.uid, { props: { max_level: v } })} />
          <NumField label="Diámetro" unit="m" hint={HELP.tankDiameter} value={p.tank_diameter} allowNull onCommit={(v) => updateNode(node.uid, { props: { tank_diameter: v } })} />
          <NumField label="Volumen útil (al nivel máximo)" unit="m³" digits={1}
            value={p.tank_diameter && p.max_level != null ? (Math.PI / 4) * p.tank_diameter ** 2 * (p.max_level - (p.min_level ?? 0)) : null} allowNull
            hint="Ingrese el volumen en vez del diámetro: se calcula el diámetro del cilindro equivalente entre el nivel mínimo y el máximo (√(4·V / (π·altura)))."
            onCommit={(v) => {
              const h = (p.max_level ?? 0) - (p.min_level ?? 0);
              if (v && v > 0 && h > 0) updateNode(node.uid, { props: { tank_diameter: Math.round(Math.sqrt((4 * v) / (Math.PI * h)) * 10000) / 10000 } });
            }} />
          <NumField label="Volumen mínimo" unit="m³" hint={HELP.minVolume} value={p.min_volume} allowNull onCommit={(v) => updateNode(node.uid, { props: { min_volume: v } })} />
          <Readout label="Cota de rebalse" hint={HELP.overflow} value={fmt(tank?.overflowElevation, 2)} unit="m" />
        </Section>
      )}
      {r && (
        <Section id="nudo.resultados" className="results" primary title={<>Resultados {result!.times.length > 1 ? `(t = ${Math.round(result!.times[period] / 360) / 10} h)` : ""}</>}>
          {node.kind === "tank" ? (<>
            <Readout label="Nivel de agua" hint={HELP.waterLevel} value={fmt(r.pressure[period], 2)} unit="m" />
            <Readout label="Volumen almacenado" hint={HELP.storedVolume} value={fmt(tank?.volume, 1)} unit="m³" />
          </>) : <Readout label="Presión" value={fmt(r.pressure[period], 2)} unit="m" tone={r.pressure[period] < 0 ? "bad" : ""} />}
          <Readout label="Cota piezométrica" value={fmt(r.head[period], 2)} unit="m" />
          <Readout label={node.kind === "junction" ? "Demanda" : "Aporte (−) / consumo (+)"} value={fmt(r.demand[period], 3)} unit="L/s" />
        </Section>
      )}
      <Attributes attrs={node.props.attributes} onChange={(a) => updateNode(node.uid, { props: { attributes: a } })} />
      <Issues id={node.id} type="node" />
    </>
  );
}

function PipeSelect({ links, catalog, formula, primary = true }: { links: ELink[]; catalog: CatalogPipe[]; formula: HydraulicOptions["headloss"]; primary?: boolean }) {
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
  const catalogItem = catalog.find((c) => c.id === first.catalog_pipe_id);
  const verified = catalogItem?.verified;
  return (
    <Section id="tramo.tuberia" title={<>Tubería {links.length > 1 ? `(${links.length} tramos)` : ""}</>} primary={primary}>
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
          <label className="field"><FieldLabel label="DN" help={HELP.dn} />
            <select value={first.dn ?? ""} onChange={(e) => apply(material, cls, Number(e.target.value))}>
              {dns.map((d) => <option key={d.id} value={d.dn}>{d.dn}</option>)}
            </select>
          </label>
        </>)}
      </div>
      {material !== "custom" && verified === false && <div className="muted small">Catálogo referencial (no verificado).</div>}
      <NumField label="Diámetro interior" unit="mm" hint={HELP.innerDiameter} value={first.inner_diameter_mm} allowNull
        onCommit={(v) => updateLinks(uids, { inner_diameter_mm: v, inner_diameter_source: "manual" })} />
      <div className="muted small inline">
        Fuente: {first.inner_diameter_source === "manual" ? <b>manual</b> : "catálogo"}
        {first.inner_diameter_source === "manual" && catalogItem && (
          <button type="button" className="link" onClick={() => updateLinks(uids, { inner_diameter_mm: catalogItem.inner_diameter_mm, inner_diameter_source: "catalogo" })}>
            restablecer del catálogo ({fmt(catalogItem.inner_diameter_mm, 1)} mm)</button>)}
      </div>
      {catalogItem?.review && <div className="issue-line warning small">Catálogo en revisión: {catalogItem.review}</div>}
      <NumField label={ROUGHNESS_LABEL[formula]} value={first.roughness} allowNull digits={4} disabled={material !== "custom"}
        onCommit={(v) => updateLinks(uids, { roughness: v })} hint={HELP.roughness[formula]} />
      <NumField label="Coef. pérdidas menores" value={first.minor_loss} onCommit={(v) => updateLinks(uids, { minor_loss: v ?? 0 })} />
      <label className="field"><span>Estado inicial</span>
        <select value={first.initial_status} onChange={(e) => updateLinks(uids, { initial_status: e.target.value as LinkProps["initial_status"] })}>
          <option value="open">Abierta</option><option value="closed">Cerrada</option><option value="cv">Con válvula de retención</option>
        </select>
      </label>
    </Section>
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
          <PipeSelect links={[link]} catalog={catalog} formula={options.headloss} primary={!r} />
          <Section id="tramo.largos" title="Largos">
            <Readout label="En planta" value={fmtLen(p.length_plan_m ?? est)} />
            <Readout label="Con pendiente" value={fmtLen(p.length_slope_m)} />
            <label className="field"><FieldLabel label="Largo hidráulico usado" help={HELP.lengthChoice} />
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
              hint={HELP.lengthHydraulic}
              onCommit={(v) => updateLinks([link.uid], { length_hydraulic_m: v, length_choice: "manual" })} />
          </Section>
          <PipeManagement link={link} />
        </>
      ) : link.kind === "pump" ? (
        <>
        <Section id="bomba.bomba" title="Bomba" primary={!r}>
          <Readout label="Curva" value={p.pump_curve ?? (p.pump_power ? `potencia ${fmt(p.pump_power, 1)} kW` : "—")} />
          <NumField label="Velocidad relativa" value={p.pump_speed ?? 1} onCommit={(v) => updateLinks([link.uid], { pump_speed: v })} />
          <label className="field"><span>Estado inicial</span>
            <select value={p.initial_status} onChange={(e) => updateLinks([link.uid], { initial_status: e.target.value as LinkProps["initial_status"] })}>
              <option value="open">En operación</option><option value="closed">Detenida</option>
            </select>
          </label>
        </Section>
        <PumpOperation link={link} />
        </>
      ) : (
        <>
        <Section id="valvula.valvula" title={`Válvula ${p.valve_type ?? ""}`} primary={!r}>
          <NumField label="Diámetro" unit="mm" value={p.inner_diameter_mm} onCommit={(v) => updateLinks([link.uid], { inner_diameter_mm: v })} />
          <NumField label="Consigna" value={p.valve_setting} allowNull onCommit={(v) => updateLinks([link.uid], { valve_setting: v })} />
        </Section>
        <PumpOperation link={link} />
        </>
      )}
      {r && (
        <Section id="tramo.resultados" className="results" title="Resultados" primary>
          <Readout label="Caudal" value={fmt(r.flow[period], 3)} unit="L/s" />
          <Readout label="Velocidad" value={fmt(Math.abs(r.velocity[period]), 3)} unit="m/s" />
          <Readout label={link.kind === "pipe" ? "Pérdida unitaria" : "Pérdida / ganancia"} value={fmt(link.kind === "pipe" ? Math.abs(r.headloss[period]) : r.headloss[period], 3)} unit={link.kind === "pipe" ? "m/km" : "m"} />
          <Readout label="Estado" value={STATUS_TXT[r.status[period]] ?? String(r.status[period])} />
        </Section>
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
      <Section id="proyecto.datos" title="Proyecto">
        <TextField label="Nombre" value={project.name} onCommit={async (v) => {
          if (!v.trim()) return;
          const p = await api.updateProject(project.id, { name: v.trim() });
          set({ project: p });
        }} />
        <div className="muted small">{counts.nodes} nudos · {counts.pipes} tuberías · {fmt(counts.km, 2)} km · largos en EPSG:{project.length_srid}</div>
      </Section>
      <Section id="proyecto.opciones" title="Opciones hidráulicas" primary>
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
        <label className="check"><input type="checkbox" checked={!!options.include_projected_clients}
          onChange={(e) => setOptions({ ...options, include_projected_clients: e.target.checked })} />Incluir clientes proyectados en la demanda</label>
      </Section>
      <DesignParamsEditor profileName={profile?.name ?? null} />
      {engine && (
        <Section id="proyecto.motor" title="Motor hidráulico">
          <div className="small">OWA-EPANET {engine.wheel_version} · tag {engine.epanet_tag}</div>
          <div className="small mono" title={engine.epanet_sha ?? ""}>SHA {engine.epanet_sha?.slice(0, 12)}</div>
        </Section>
      )}
    </>
  );
}

/** Desglose de la demanda del nudo: manual + clientes (trazabilidad). */
function DemandBreakdown({ nodeUid }: { nodeUid: string }) {
  const { net, options, select } = useEditor();
  const d = nodeDemand(net, nodeUid, !!options.include_projected_clients);
  if (!d.clients.length) return null;
  return (
    <div className="results" style={{ marginTop: 8 }}>
      <Readout label="Demanda manual" value={fmt(d.manual, 3)} unit="L/s" />
      {d.clients.map((c) => {
        const counted = d.counted.includes(c);
        return (
          <div key={c.uid} className="readout">
            <span><button type="button" className="link" onClick={() => select([c.uid])}>{c.id}</button> {c.props.name ?? ""}{!counted && " (proyectado, no suma)"}</span>
            <b className={counted ? "" : "muted"}>{fmt(toLps(c.props.consumption_value, c.props.consumption_unit), 3)}</b><em>L/s</em>
          </div>
        );
      })}
      <Readout label="Demanda total del nudo" value={fmt(d.total, 3)} unit="L/s" />
    </div>
  );
}

function ClientPanel({ c }: { c: EClient }) {
  const { net, result, period, designParams } = useEditor();
  const upd = (patch: Partial<EClient["props"]>) => useEditor.getState().commit((n) => ({
    ...n, clients: { ...n.clients, [c.uid]: { ...n.clients[c.uid], props: { ...n.clients[c.uid].props, ...patch } } } }));
  const node = net.nodes[c.node];
  const r = node ? result?.nodes[node.id] : undefined;
  const pmin = designParams?.find((p) => p.key === "pressure_min")?.value as number | undefined;
  let pressure = r?.pressure[period];
  if (pressure !== undefined && c.props.elevation != null && node?.props.elevation != null) pressure += node.props.elevation - c.props.elevation;
  return (
    <>
      <h3>Cliente <code>{c.id}</code></h3>
      <TextField label="Nombre o dirección" value={c.props.name} onCommit={(v) => upd({ name: v || null })} />
      <label className="field"><span>Tipo</span>
        <select value={c.props.client_type} onChange={(e) => upd({ client_type: e.target.value as EClient["props"]["client_type"] })}>
          {CLIENT_TYPES.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}</select></label>
      <NumField label="Consumo" unit={c.props.consumption_unit === "m3/mes" ? "m³/mes" : "L/s"} value={c.props.consumption_value}
        onCommit={(v) => upd({ consumption_value: Math.max(0, v ?? 0) })} hint="En m³/mes se convierte a L/s con mes de 30 días." />
      <label className="field"><span>Unidad</span>
        <select value={c.props.consumption_unit} onChange={(e) => upd({ consumption_unit: e.target.value as EClient["props"]["consumption_unit"] })}>
          <option value="L/s">L/s</option><option value="m3/mes">m³/mes</option></select></label>
      <Readout label="Consumo en L/s" value={fmt(toLps(c.props.consumption_value, c.props.consumption_unit), 4)} unit="L/s" />
      <label className="field"><span>Estado</span>
        <select value={c.props.status} onChange={(e) => upd({ status: e.target.value as EClient["props"]["status"] })}>
          <option value="activo">Activo</option><option value="proyectado">Proyectado</option><option value="suspendido">Suspendido</option></select></label>
      <Section id="cliente.conexion" title="Conexión" primary={pressure === undefined}>
        <Readout label="Nudo asignado" value={node?.id ?? "—"} />
        <Readout label="Tubería" value={c.link ? net.links[c.link]?.id ?? "—" : "—"} />
        <Readout label="Modo" value={c.props.connection_mode === "new_node" ? "nudo nuevo en el arranque" : "nudo más cercano"} />
        <NumField label="Cota del terreno" unit="m" value={c.props.elevation} allowNull onCommit={(v) => upd({ elevation: v })}
          hint="Opcional: con ella la presión del cliente se calcula en su cota (cota piezométrica del nudo − cota del cliente)." />
      </Section>
      {pressure !== undefined && (
        <Section id="cliente.resultados" className="results" title="Resultados" primary>
          <Readout label="Presión en el cliente" value={fmt(pressure, 2)} unit="m" tone={pmin !== undefined && pressure < pmin ? "bad" : ""} />
        </Section>)}
      <ClientManagement c={c} />
      <Issues id={c.id} type="client" />
    </>
  );
}

function ShutoffPanel({ sh }: { sh: EShutoff }) {
  const { net, scenarios } = useEditor();
  const upd = (patch: Partial<EShutoff>) => useEditor.getState().commit((n) => ({ ...n, shutoffs: { ...n.shutoffs, [sh.uid]: { ...n.shutoffs[sh.uid], ...patch } } }));
  const used = scenarios.filter((x) => (x.closed ?? []).includes(sh.id)).map((x) => x.name);
  return (
    <>
      <h3>Llave de corte <code>{sh.id}</code></h3>
      <TextField label="Nombre" value={sh.props.name} placeholder="Ej.: Llave calle Norte" onCommit={(v) => upd({ props: { ...sh.props, name: v || null } })} />
      <Readout label="Tubería" value={net.links[sh.link]?.id ?? "—"} />
      <NumField label="Posición" unit="%" value={Math.round(sh.position * 1000) / 10} digits={1}
        onCommit={(v) => upd({ position: Math.max(0, Math.min(1, (v ?? 50) / 100)) })} hint="Posición a lo largo de la tubería (0 % = inicio)." />
      <label className="field"><span>Estado en el modelo <Help text="Cerrada = la tubería se cierra en EPANET. Los escenarios pueden cambiar el estado sin modificar el modelo." /></span>
        <select value={sh.props.state} onChange={(e) => upd({ props: { ...sh.props, state: e.target.value as EShutoff["props"]["state"] } })}>
          <option value="open">Abierta</option><option value="closed">Cerrada</option></select></label>
      {used.length > 0 && <p className="muted small">Cerrada en los escenarios: {used.join(", ")}.</p>}
      <ShutoffManagement sh={sh} />
    </>
  );
}

/** Parámetros de diseño del proyecto: editables, con fuente y estado de verificación. */
function DesignParamsEditor({ profileName }: { profileName: string | null }) {
  const { project, designParams, set, toast } = useEditor();
  if (!project || !designParams) return null;
  const save = async (key: string, value: number | number[], verified: boolean, source?: string) => {
    try {
      const r = await api.saveDesignParams(project.id, [{ key, value, verified, source: source ?? null }]);
      set({ designParams: r.params });
      toast("Parámetro actualizado. Las alertas se recalculan al simular.");
    } catch (e) {
      toast(errorText(e), "error");
    }
  };
  const groups: [string, string][] = [["criterio", "Criterios de diseño"], ["demanda", "Demanda"], ["curva", "Curvas"]];
  return (
    <>
      {groups.map(([g, title]) => (
        <Section key={g} id={`proyecto.${g}`} title={title} extra={designParams.some((p) => p.group === g && !p.verified) && <span className="badge warn">no verificado</span>}>
          {g === "criterio" && profileName && <div className="muted small">Por defecto: perfil «{profileName}»</div>}
          {designParams.filter((p) => p.group === g).map((p) => (
            <div key={p.key} className="param">
              <div className="param-head">
                <span>{p.label}{p.bound ? (p.bound === "min" ? " (mín.)" : " (máx.)") : ""}</span>
                {Array.isArray(p.value)
                  ? <CurveField value={p.value} onCommit={(v) => void save(p.key, v, p.verified)} />
                  : <span className="with-unit"><NumInput value={p.value} onCommit={(v) => void save(p.key, v, p.verified)} /><em>{p.unit}</em></span>}
              </div>
              <div className="param-foot">
                <span className="muted small">{p.source}</span>
                <label className="check small" title="Marque solo si revisó el valor contra la norma o el estudio">
                  <input type="checkbox" checked={p.verified} onChange={(e) => void save(p.key, p.value, e.target.checked, p.source)} />verificado</label>
              </div>
            </div>))}
        </Section>
      ))}
    </>
  );
}

function NumInput({ value, onCommit }: { value: number; onCommit: (v: number) => void }) {
  const [t, setT] = useState(fmt(value, 2).replace(/,?0+$/, ""));
  useEffect(() => setT(fmt(value, 2).replace(/,?0+$/, "")), [value]);
  return <input inputMode="decimal" value={t} onChange={(e) => setT(e.target.value)}
    onBlur={() => { const v = parseNum(t); if (v !== null && v !== value) onCommit(v); else setT(fmt(value, 2).replace(/,?0+$/, "")); }}
    onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()} />;
}

function CurveField({ value, onCommit }: { value: number[]; onCommit: (v: number[]) => void }) {
  const text = value.map((x) => fmt(x, 2).replace(/,?0+$/, "")).join("; ");
  const [t, setT] = useState(text);
  useEffect(() => setT(text), [text]);
  const mean = value.reduce((a, b) => a + b, 0) / value.length;
  return (
    <span>
      <input style={{ width: 180, textAlign: "left" }} value={t} onChange={(e) => setT(e.target.value)} title="24 coeficientes separados por «;»"
        onBlur={() => {
          const vals = t.split(";").map((x) => parseNum(x));
          if (vals.length === value.length && vals.every((x) => x !== null)) onCommit(vals as number[]);
          else setT(text);
        }} />
      <div className={`small ${Math.abs(mean - 1) > 0.005 ? "warn-text" : "muted"}`}>promedio {fmt(mean, 3)}</div>
    </span>
  );
}

export function PropertiesPanel() {
  const { selection, net } = useEditor();
  const userId = useAuth((s) => s.me?.id ?? "");
  const setUser = useSections((s) => s.setUser);
  useEffect(() => setUser(String(userId)), [userId, setUser]);
  let body: React.ReactNode;
  if (selection.length > 1) body = <MultiPanel uids={selection} />;
  else if (selection.length === 1 && net.clients[selection[0]]) body = <ClientPanel c={net.clients[selection[0]]} />;
  else if (selection.length === 1 && net.shutoffs[selection[0]]) body = <ShutoffPanel sh={net.shutoffs[selection[0]]} />;
  else if (selection.length === 1 && net.hydrants[selection[0]]) body = <HydrantPanel h={net.hydrants[selection[0]]} />;
  else if (selection.length === 1 && net.wells[selection[0]]) body = <WellPanel w={net.wells[selection[0]]} />;
  else if (selection.length === 1 && net.nodes[selection[0]]) body = <NodePanel node={net.nodes[selection[0]]} />;
  else if (selection.length === 1 && net.links[selection[0]]) body = <LinkPanel link={net.links[selection[0]]} />;
  else body = <ProjectPanel />;
  return (
    <aside className="props" aria-label="Propiedades">
      <div className="props-bar">
        <ExpandAll />
      </div>
      {body}
    </aside>
  );
}
