// Atributos de gestión (SIG): tramos, válvulas, clientes, grifos, pozos y atributos libres.
import type { EClient, EHydrant, ELink, EShutoff, EWell, LinkProps } from "../lib/network";
import { fmt } from "../lib/format";
import { useEditor } from "../state/store";
import { NumField, Readout, TextField } from "./Fields";

type Opt = [string, string];
export const PIPE_CONDITION: Opt[] = [["bueno", "Bueno"], ["regular", "Regular"], ["malo", "Malo"], ["fuera_servicio", "Fuera de servicio"]];
export const NETWORK_TYPE: Opt[] = [["matriz", "Matriz"], ["distribucion", "Distribución"], ["aduccion", "Aducción"], ["impulsion", "Impulsión"]];
export const ASSET_CONDITION: Opt[] = [["bueno", "Bueno"], ["regular", "Regular"], ["malo", "Malo"], ["inoperativo", "Inoperativo"]];
export const SHUTOFF_TYPE: Opt[] = [["compuerta", "Compuerta"], ["mariposa", "Mariposa"], ["bola", "Bola"], ["otra", "Otra"]];
export const HYDRANT_TYPE: Opt[] = [["columna", "Columna"], ["subterraneo", "Subterráneo"]];

export function Choice({ label, value, options, onChange }: { label: string; value: string | null | undefined; options: Opt[]; onChange: (v: string | null) => void }) {
  return (
    <label className="field"><span>{label}</span>
      <select value={value ?? ""} onChange={(e) => onChange(e.target.value || null)}>
        <option value="">—</option>
        {options.map(([k, t]) => <option key={k} value={k}>{t}</option>)}
      </select>
    </label>
  );
}

export function Attributes({ attrs, onChange }: { attrs: Record<string, unknown> | undefined; onChange: (a: Record<string, string | number | null>) => void }) {
  const entries = Object.entries(attrs ?? {}).filter(([k]) => !k.startsWith("__"));
  return (
    <fieldset>
      <legend>Atributos libres</legend>
      {entries.length === 0 && <p className="muted small">Sin atributos. Las columnas adicionales de la planilla se guardan aquí.</p>}
      {entries.map(([k, v]) => (
        <TextField key={k} label={k} value={v === null || v === undefined ? "" : String(v)}
          onCommit={(t) => { const next = { ...(attrs ?? {}) } as Record<string, string | number | null>; if (t === "") delete next[k]; else next[k] = t; onChange(next); }} />
      ))}
      <TextField label="Nuevo atributo (nombre)" value="" placeholder="Ej.: Sector social" onCommit={(name) => {
        if (!name.trim()) return;
        onChange({ ...(attrs ?? {}) as Record<string, string | number | null>, [name.trim()]: "" });
      }} />
    </fieldset>
  );
}

function updLink(uid: string, patch: Partial<LinkProps>) {
  useEditor.getState().commit((n) => ({ ...n, links: { ...n.links, [uid]: { ...n.links[uid], props: { ...n.links[uid].props, ...patch } } } }));
}

export function PipeManagement({ link }: { link: ELink }) {
  const p = link.props;
  return (
    <>
      <fieldset>
        <legend>Gestión</legend>
        <Choice label="Estado" value={p.condition} options={PIPE_CONDITION} onChange={(v) => updLink(link.uid, { condition: v as LinkProps["condition"] })} />
        {p.condition === "fuera_servicio" && <p className="muted small">Un tramo fuera de servicio se simula cerrado.</p>}
        <NumField label="Año de instalación" value={p.install_year} digits={0} allowNull onCommit={(v) => updLink(link.uid, { install_year: v === null ? null : Math.round(v) })} />
        <Choice label="Tipo de red" value={p.network_type} options={NETWORK_TYPE} onChange={(v) => updLink(link.uid, { network_type: v as LinkProps["network_type"] })} />
        <TextField label="Observaciones" value={p.description} onCommit={(v) => updLink(link.uid, { description: v || null })} />
      </fieldset>
      <Attributes attrs={p.attributes} onChange={(a) => updLink(link.uid, { attributes: a })} />
    </>
  );
}

export function ShutoffManagement({ sh }: { sh: EShutoff }) {
  const upd = (patch: Partial<EShutoff["props"]>) => useEditor.getState().commit((n) => ({
    ...n, shutoffs: { ...n.shutoffs, [sh.uid]: { ...n.shutoffs[sh.uid], props: { ...n.shutoffs[sh.uid].props, ...patch } } } }));
  return (
    <>
      <fieldset>
        <legend>Gestión</legend>
        <Choice label="Tipo" value={sh.props.valve_type} options={SHUTOFF_TYPE} onChange={(v) => upd({ valve_type: v as EShutoff["props"]["valve_type"] })} />
        <Choice label="Condición" value={sh.props.condition} options={ASSET_CONDITION} onChange={(v) => upd({ condition: v as EShutoff["props"]["condition"] })} />
        {sh.props.condition === "inoperativo" && <p className="muted small">Inoperativa: no se considera para los cuarteles de corta.</p>}
        <NumField label="Diámetro" unit="mm" value={sh.props.diameter_mm} allowNull digits={0} onCommit={(v) => upd({ diameter_mm: v })} />
        <NumField label="Profundidad" unit="m" value={sh.props.depth_m} allowNull digits={2} onCommit={(v) => upd({ depth_m: v })} />
      </fieldset>
      <Attributes attrs={sh.props.attributes} onChange={(a) => upd({ attributes: a })} />
    </>
  );
}

export function ClientManagement({ c }: { c: EClient }) {
  const upd = (patch: Partial<EClient["props"]>) => useEditor.getState().commit((n) => ({
    ...n, clients: { ...n.clients, [c.uid]: { ...n.clients[c.uid], props: { ...n.clients[c.uid].props, ...patch } } } }));
  return (
    <>
      <fieldset>
        <legend>Datos comerciales</legend>
        <TextField label="N° de cliente" value={c.props.client_number} onCommit={(v) => upd({ client_number: v || null })} />
        <TextField label="Dirección" value={c.props.address} onCommit={(v) => upd({ address: v || null })} />
        <TextField label="Ruta de lectura" value={c.props.route} onCommit={(v) => upd({ route: v || null })} />
        <TextField label="N° de medidor" value={c.props.meter_number} onCommit={(v) => upd({ meter_number: v || null })} />
      </fieldset>
      <Attributes attrs={c.props.attributes} onChange={(a) => upd({ attributes: a })} />
    </>
  );
}

export function HydrantPanel({ h }: { h: EHydrant }) {
  const { net } = useEditor();
  const upd = (patch: Partial<EHydrant>) => useEditor.getState().commit((n) => ({ ...n, hydrants: { ...n.hydrants, [h.uid]: { ...n.hydrants[h.uid], ...patch } } }));
  const props = (patch: Partial<EHydrant["props"]>) => upd({ props: { ...h.props, ...patch } });
  const junctions = Object.values(net.nodes).filter((n) => n.kind === "junction").sort((a, b) => a.id.localeCompare(b.id, "es", { numeric: true }));
  return (
    <>
      <h3>Grifo <code>{h.id}</code></h3>
      <TextField label="ID" value={h.id} onCommit={(v) => {
        if (!/^[^\s;"]{1,31}$/.test(v) || Object.values(net.hydrants).some((x) => x.uid !== h.uid && x.id === v)) useEditor.getState().toast("ID no válido o repetido.", "error");
        else upd({ id: v });
      }} />
      <label className="field"><span>Nudo de conexión</span>
        <select value={h.node} onChange={(e) => upd({ node: e.target.value })}>
          {junctions.map((n) => <option key={n.uid} value={n.uid}>{n.id}</option>)}</select></label>
      <Choice label="Tipo" value={h.props.hydrant_type} options={HYDRANT_TYPE} onChange={(v) => props({ hydrant_type: v as EHydrant["props"]["hydrant_type"] })} />
      <Choice label="Estado" value={h.props.condition} options={ASSET_CONDITION} onChange={(v) => props({ condition: v as EHydrant["props"]["condition"] })} />
      <NumField label="Diámetro" unit="mm" value={h.props.diameter_mm} allowNull digits={0} onCommit={(v) => props({ diameter_mm: v })} />
      <NumField label="Caudal de incendio" unit="L/s" value={h.props.fire_flow_lps ?? 16} onCommit={(v) => props({ fire_flow_lps: Math.max(0.1, v ?? 16) })}
        hint="Caudal requerido para el escenario de incendio (16 L/s por defecto, valor referencial no verificado)." />
      <NumField label="Presión residual mínima" unit="m" value={h.props.min_pressure_m ?? 5} onCommit={(v) => props({ min_pressure_m: Math.max(0, v ?? 5) })} />
      <TextField label="Observaciones" value={h.props.description} onCommit={(v) => props({ description: v || null })} />
      <p className="muted small">Presión y caudal disponibles: pestaña Grifos → Escenario de incendio.</p>
      <Attributes attrs={h.props.attributes} onChange={(a) => props({ attributes: a })} />
    </>
  );
}

export function WellPanel({ w }: { w: EWell }) {
  const { net } = useEditor();
  const upd = (patch: Partial<EWell>) => useEditor.getState().commit((n) => ({ ...n, wells: { ...n.wells, [w.uid]: { ...n.wells[w.uid], ...patch } } }));
  const props = (patch: Partial<EWell["props"]>) => upd({ props: { ...w.props, ...patch } });
  const reservoirs = Object.values(net.nodes).filter((n) => n.kind === "reservoir");
  const res = w.node ? net.nodes[w.node] : null;
  const head = w.props.ground_elevation != null && w.props.dynamic_level_m != null ? w.props.ground_elevation - w.props.dynamic_level_m : null;
  return (
    <>
      <h3>Pozo <code>{w.id}</code></h3>
      <TextField label="ID" value={w.id} onCommit={(v) => {
        if (!/^[^\s;"]{1,31}$/.test(v) || Object.values(net.wells).some((x) => x.uid !== w.uid && x.id === v)) useEditor.getState().toast("ID no válido o repetido.", "error");
        else upd({ id: v });
      }} />
      <label className="field"><span>Reservorio asociado</span>
        <select value={w.node ?? ""} onChange={(e) => upd({ node: e.target.value || null })}>
          <option value="">— (sin modelo hidráulico)</option>
          {reservoirs.map((n) => <option key={n.uid} value={n.uid}>{n.id}</option>)}</select></label>
      <NumField label="Cota de terreno" unit="m" value={w.props.ground_elevation} allowNull onCommit={(v) => props({ ground_elevation: v })} />
      <NumField label="Profundidad" unit="m" value={w.props.depth_m} allowNull onCommit={(v) => props({ depth_m: v })} />
      <NumField label="Nivel estático" unit="m" value={w.props.static_level_m} allowNull onCommit={(v) => props({ static_level_m: v })} hint="Profundidad del agua en reposo, bajo el terreno." />
      <NumField label="Nivel dinámico" unit="m" value={w.props.dynamic_level_m} allowNull onCommit={(v) => props({ dynamic_level_m: v })} hint="Profundidad del agua bombeando, bajo el terreno." />
      <NumField label="Caudal autorizado" unit="L/s" value={w.props.authorized_flow_lps} allowNull onCommit={(v) => props({ authorized_flow_lps: v })} />
      <Choice label="Estado" value={w.props.condition} options={ASSET_CONDITION} onChange={(v) => props({ condition: v as EWell["props"]["condition"] })} />
      <TextField label="Observaciones" value={w.props.description} onCommit={(v) => props({ description: v || null })} />
      {head !== null && (
        <Readout label="Cota del nivel dinámico" value={fmt(head, 2)} unit="m"
          hint={res ? `Carga del reservorio ${res.id}: ${res.props.head != null ? fmt(res.props.head, 2) : "sin definir"} m.` : "Asocie un reservorio para usarlo en el modelo."} />
      )}
      {res && head !== null && res.props.head !== head && (
        <button className="small" onClick={() => useEditor.getState().commit((n) => ({ ...n, nodes: { ...n.nodes, [res.uid]: { ...res, props: { ...res.props, head } } } }))}>
          Usar como carga del reservorio {res.id}</button>
      )}
      <Attributes attrs={w.props.attributes} onChange={(a) => props({ attributes: a })} />
    </>
  );
}
