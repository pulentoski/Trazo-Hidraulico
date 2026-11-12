// Panel general del proyecto («Resumen»): indicadores de la última simulación en la hora elegida (por defecto la
// hora punta). Cada número enlaza a su lista y al mapa; las zonas por presión y el área operacional son capas.
import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { ElementList, LeakEventIn, SummaryGroup, SummaryResult } from "../api/types";
import { fmt } from "../lib/format";
import type { ElType } from "../lib/summary";
import type { LngLat } from "../lib/geo";
import { clp, hourLabel, polygonsOf, uidMaps, uidsOf, zoneColor } from "../lib/summary";
import { errorText } from "../state/projects";
import { useEditor } from "../state/store";
import { SummarySettingsDialog } from "./SummarySettings";
import { Icon } from "./Icons";

interface Listing { title: string; type: ElType; ids: string[]; values?: Record<string, string> }

const TYPE_TAB: Partial<Record<ElType, string>> = { node: "nodes", link: "links", client: "clients", hydrant: "hydrants" };
const TYPE_NAME: Record<ElType, string> = { node: "nudos", link: "tramos", client: "clientes", shutoff: "válvulas", hydrant: "grifos", well: "pozos" };
const KIND_TXT: Record<string, string> = { fuga: "Fuga", rotura: "Rotura", reparacion: "Reparación" };

export function SummaryTab() {
  const { project, net, serverVersion, result, readOnly, overlay, set, toast, revision, savedRevision } = useEditor();
  const [data, setData] = useState<SummaryResult | null>(null);
  const [scenario, setScenario] = useState("modelo");
  const [period, setPeriod] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [listing, setListing] = useState<Listing | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const maps = useMemo(() => uidMaps(net), [net]);
  const pid = project?.id;

  const load = useCallback(async () => {
    if (!pid) return;
    setBusy(true);
    try {
      const r = await api.summary(pid, { scenario, period });
      setData(r);
      setError(null);
      if (r.period !== null && r.period !== undefined) set({ period: r.period });
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }, [pid, scenario, period, set]);

  // Se recalcula al guardar una versión nueva o al cambiar escenario u hora.
  useEffect(() => { void load(); }, [load, serverVersion]);
  // Al terminar una simulación solo hace falta recalcular si el resumen vigente no la incluía (el servidor ya
  // simula la versión al armar el resumen: así no se pide dos veces al abrir el proyecto).
  const runVersion = result?.model_version;
  useEffect(() => {
    if (runVersion === undefined || !data) return;
    if (data.model_version === runVersion && !data.sim_note) return;
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [result?.run_id]);

  // Capas del mapa siguen los datos vigentes (si están activas).
  const zonesOn = overlay.zones.length > 0;
  const areaOn = overlay.area.length > 0;
  const zoneLayer = useCallback((d: SummaryResult) => d.zones.features.flatMap((f, i) =>
    polygonsOf(f.geometry).map((coords, k) => ({ key: `z${i}-${k}`, coords, color: zoneColor(f.cls), label: `${f.node}: ${fmt(f.pressure, 1)} m` }))), []);
  const areaLayer = useCallback((d: SummaryResult) => polygonsOf(d.area.geometry).map((coords, k) => ({ key: `a${k}`, coords, color: "#0b6aa8" })), []);
  useEffect(() => {
    if (!data) return;
    const st = useEditor.getState().overlay;
    if (st.zones.length || st.area.length) set({ overlay: { zones: st.zones.length ? zoneLayer(data) : [], area: st.area.length ? areaLayer(data) : [] } });
  }, [data, set, zoneLayer, areaLayer]);
  useEffect(() => () => useEditor.getState().set({ highlight: [] }), []);

  const show = (title: string, type: ElType, ids: string[], values?: Record<string, string>) => {
    setListing({ title, type, ids, values });
    const uids = uidsOf(maps, type, ids);
    set({ highlight: uids });
    useEditor.getState().frame(uids);
  };
  const goto = (type: ElType, id: string) => {
    const uid = maps[type].get(id);
    if (uid) useEditor.getState().focus([uid]);
  };
  /** Número que enlaza a su lista y al mapa. */
  const N = ({ value, title, list, digits = 0, unit, values }: { value: number | null | undefined; title: string; list?: ElementList | { type: ElType; ids?: string[] }; digits?: number; unit?: string; values?: Record<string, string> }) => {
    const txt = `${fmt(value, digits)}${unit ? ` ${unit}` : ""}`;
    const ids = list?.ids ?? [];
    if (!list || !ids.length) return <b className="num-link off">{txt}</b>;
    return <button type="button" className="num-link" title={`Ver ${title.toLowerCase()} en la lista y el mapa`} onClick={() => show(title, list.type as ElType, ids, values)}>{txt}</button>;
  };
  const groups = (title: string, rows: SummaryGroup[], type: ElType, mode: "km" | "count" | "m3") => (
    <table className="tbl compact mini">
      <tbody>
        {rows.map((g) => (
          <tr key={g.key}>
            <td>{g.key}</td>
            <td className="num">{mode === "km" ? <N value={g.km} digits={3} unit="km" title={`${title}: ${g.key}`} list={{ type, ids: g.ids }} />
              : <N value={g.count} title={`${title}: ${g.key}`} list={{ type, ids: g.ids }} />}</td>
            {mode === "km" && <td className="num muted">{g.count}</td>}
            {mode === "m3" && <td className="num muted">{fmt(g.m3_day, 2)} m³/d</td>}
          </tr>
        ))}
      </tbody>
    </table>
  );

  if (!pid) return null;
  /** Al mostrar una capa de grupo (zonas, área), el mapa encuadra todos sus polígonos. */
  const frameRings = (layer: { coords: LngLat[][] }[]) => useEditor.getState().frame([], { points: layer.flatMap((z) => z.coords.flat()) });
  const toggleZones = () => {
    if (!data) return;
    const zones = zonesOn ? [] : zoneLayer(data);
    set({ overlay: { ...overlay, zones } });
    if (zones.length) frameRings(zones);
  };
  const toggleArea = () => {
    if (!data) return;
    const area = areaOn ? [] : areaLayer(data);
    set({ overlay: { ...overlay, area } });
    if (area.length) frameRings(area);
  };
  const dirty = revision !== savedRevision;

  return (
    <div className="summary-tab">
      <div className="toolbar summary-bar">
        <label className="inline">Escenario
          <select value={scenario} onChange={(e) => { setScenario(e.target.value); setPeriod(null); }} aria-label="Escenario">
            {(data?.scenarios ?? [{ id: "modelo", name: "Modelo (última simulación)" }]).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </label>
        <label className="inline">Hora
          <select value={period ?? ""} onChange={(e) => setPeriod(e.target.value === "" ? null : Number(e.target.value))} aria-label="Hora" disabled={!data?.times.length}>
            <option value="">Hora punta{data?.peak_period != null && data.times.length ? ` (${hourLabel(data.times[data.peak_period])})` : ""}</option>
            {(data?.times ?? []).map((t, i) => <option key={i} value={i}>{hourLabel(t)}{i === data?.peak_period ? " · punta" : ""}{i === data?.pressures.critical_period ? " · crítica" : ""}</option>)}
          </select>
        </label>
        <button className={`small ${zonesOn ? "on-toggle" : ""}`} onClick={toggleZones} disabled={!data?.zones.features.length} aria-pressed={zonesOn}>Zonas por presión</button>
        <button className={`small ${areaOn ? "on-toggle" : ""}`} onClick={toggleArea} disabled={!data?.area.geometry} aria-pressed={areaOn}>Área operacional</button>
        <span className="tabs-spacer" />
        {busy && <span className="muted small">Calculando…</span>}
        {data && <span className="muted small">v{data.model_version}{dirty ? " · hay cambios sin guardar" : ""}</span>}
        <a className="btn small" href={api.summaryUrl(pid, "html", { scenario, period })} target="_blank" rel="noreferrer" title="Resumen imprimible: use Imprimir → Guardar como PDF">PDF (imprimible)</a>
        <a className="btn small" href={api.summaryUrl(pid, "xlsx", { scenario, period })}>Excel</a>
        {!readOnly && <button className="small" onClick={() => setSettingsOpen(true)}>Configurar…</button>}
      </div>
      {error && <p className="pad bad-text">{error}</p>}
      {!data && !error && <p className="pad muted">Calculando el resumen…</p>}
      {data && (
        <div className="summary-layout">
          <div className="summary-grid">
            {data.sim_note && <div className="card s-card wide warn-card">{data.sim_note}</div>}
            <Card title="Clientes">
              <div className="kpis">
                <Kpi label="Total"><N value={data.clients.total.count} title="Clientes" list={data.clients.total} /></Kpi>
                <Kpi label="Activos"><N value={data.clients.active.count} title="Clientes activos" list={data.clients.active} /></Kpi>
                <Kpi label="Proyectados"><N value={data.clients.projected.count} title="Clientes proyectados" list={data.clients.projected} /></Kpi>
                <Kpi label="Arranques"><b>{data.clients.connections}</b></Kpi>
              </div>
              <h5>Por ruta</h5>{groups("Ruta", data.clients.by_route, "client", "m3")}
              <h5>Por sector</h5>{groups("Sector", data.clients.by_sector, "client", "m3")}
            </Card>
            <Card title="Red">
              <div className="kpis">
                <Kpi label="Km de red"><N value={data.network.km_total} digits={3} title="Tuberías" list={data.network.pipes} /></Kpi>
                <Kpi label="Válvulas"><N value={data.network.valves.count + data.network.control_valves.count} title="Válvulas de corte" list={data.network.valves} /></Kpi>
                <Kpi label="Grifos"><N value={data.network.hydrants.count} title="Grifos" list={data.network.hydrants} /></Kpi>
                <Kpi label="Estanques"><N value={data.network.tanks.count} title="Estanques" list={data.network.tanks} /></Kpi>
                <Kpi label="Pozos"><N value={data.network.wells.count} title="Pozos" list={data.network.wells} /></Kpi>
              </div>
              <div className="cols2">
                <div><h5>Material</h5>{groups("Material", data.network.by_material, "link", "km")}</div>
                <div><h5>Diámetro</h5>{groups("Diámetro", data.network.by_dn, "link", "km")}</div>
                <div><h5>Estado</h5>{groups("Estado", data.network.by_condition, "link", "km")}</div>
                <div><h5>Antigüedad</h5>{groups("Antigüedad", data.network.by_age, "link", "km")}</div>
              </div>
            </Card>
            <Card title="Presiones" sub={data.period != null && data.times.length ? `a las ${hourLabel(data.times[data.period])}` : "sin simulación"}>
              {data.pressures.min ? (<>
                <div className="kpis">
                  <Kpi label="Mínima"><button type="button" className="num-link" onClick={() => goto("node", data.pressures.min!.id)}>{fmt(data.pressures.min.value, 1)} m</button><small>{data.pressures.min.id}</small></Kpi>
                  <Kpi label="Promedio"><b>{fmt(data.pressures.avg, 1)} m</b></Kpi>
                  <Kpi label="Máxima"><button type="button" className="num-link" onClick={() => goto("node", data.pressures.max!.id)}>{fmt(data.pressures.max!.value, 1)} m</button><small>{data.pressures.max!.id}</small></Kpi>
                </div>
                <dl className="kv compact">
                  <dt>Nudos bajo {fmt(data.pressures.pmin, 0)} m</dt><dd><N value={data.pressures.below_min.count} title="Nudos bajo la presión mínima" list={data.pressures.below_min} /></dd>
                  <dt>Clientes bajo {fmt(data.pressures.pmin, 0)} m</dt><dd><N value={data.pressures.clients_below.count} title="Clientes bajo la presión mínima" list={data.pressures.clients_below} /></dd>
                  <dt>Nudos sobre {fmt(data.pressures.pmax, 0)} m</dt><dd><N value={data.pressures.above_max.count} title="Nudos sobre la presión máxima" list={data.pressures.above_max} /></dd>
                  {data.pressures.unsupplied.count > 0 && <><dt>Sin suministro</dt><dd><N value={data.pressures.unsupplied.count} title="Nudos sin suministro" list={data.pressures.unsupplied} /></dd></>}
                  <dt>Hora más crítica</dt><dd>{data.pressures.critical_time != null ? <button type="button" className="link" onClick={() => setPeriod(data.pressures.critical_period ?? null)}>{hourLabel(data.pressures.critical_time)}</button> : "—"} · {fmt(data.pressures.critical_value, 1)} m en {data.pressures.critical_node ? <button type="button" className="link" onClick={() => goto("node", data.pressures.critical_node!)}>{data.pressures.critical_node}</button> : "—"}</dd>
                </dl>
              </>) : <p className="muted">Simule la red para ver presiones.</p>}
            </Card>
            <Card title="Zonas por presión" sub="áreas de influencia de cada nudo">
              <table className="tbl compact mini">
                <thead><tr><th>Rango (m.c.a.)</th><th className="num">km²</th><th className="num">Nudos</th><th className="num">Clientes</th></tr></thead>
                <tbody>
                  {data.zones.ranges.map((r) => (
                    <tr key={r.cls}>
                      <td><i className="swatch" style={{ background: zoneColor(r.cls) }} />{r.label}</td>
                      <td className="num">{fmt(r.area_km2, 4)}</td>
                      <td className="num"><N value={r.nodes.count} title={`Nudos con presión ${r.label} m`} list={r.nodes} /></td>
                      <td className="num"><N value={r.clients.count} title={`Clientes en zona ${r.label} m`} list={r.clients} /></td>
                    </tr>))}
                </tbody>
              </table>
              <div className="toolbar plain">
                <button className={`small ${zonesOn ? "on-toggle" : ""}`} onClick={toggleZones} disabled={!data.zones.features.length}>{zonesOn ? "Ocultar capa" : "Ver en el mapa"}</button>
                <a className="btn small" href={api.zonesGeojsonUrl(pid, { scenario, period })}>GeoJSON</a>
              </div>
            </Card>
            <Card title="Clientes sobre cota" sub={data.over_elevation_period != null && data.times.length ? `hora crítica ${hourLabel(data.times[data.over_elevation_period])}` : undefined}>
              {data.over_elevation.length ? (<>
                <p className="small">Cota de terreno + presión mínima sobre la cota piezométrica disponible:
                  {" "}<N value={data.over_elevation.length} title="Clientes sobre cota" list={{ type: "client", ids: data.over_elevation.map((o) => o.client) }}
                    values={Object.fromEntries(data.over_elevation.map((o) => [o.client, `déficit ${fmt(o.deficit, 1)} m`]))} /> clientes.</p>
                <table className="tbl compact mini">
                  <thead><tr><th>Cliente</th><th className="num">Terreno</th><th className="num">Piezom.</th><th className="num">Déficit</th></tr></thead>
                  <tbody>{data.over_elevation.map((o) => (
                    <tr key={o.client} className="clickable" onClick={() => goto("client", o.client)}>
                      <td>{o.client} <span className="muted">{o.name}</span></td><td className="num">{fmt(o.ground, 1)}</td><td className="num">{fmt(o.head, 1)}</td><td className="num bad">{fmt(o.deficit, 1)} m</td>
                    </tr>))}</tbody>
                </table>
              </>) : <p className="muted">{data.simulated ? "Todos los clientes quedan bajo la cota piezométrica disponible menos la presión mínima." : "Sin simulación."}</p>}
            </Card>
            <Card title="Clientes por tubería" sub="tramos con más clientes abastecidos">
              <table className="tbl compact mini">
                <tbody>{data.clients_per_pipe.slice(0, 8).map((x) => (
                  <tr key={x.link}><td><button type="button" className="link" onClick={() => goto("link", x.link)}>{x.link}</button></td>
                    <td className="num"><N value={x.clients} title={`Clientes del tramo ${x.link}`} list={{ type: "client", ids: x.ids }} /></td>
                    <td className="bar-cell"><i style={{ width: `${(x.clients / (data.clients_per_pipe[0]?.clients || 1)) * 100}%` }} /></td></tr>))}</tbody>
              </table>
            </Card>
            <Card title="Mayores consumidores" sub={`top ${data.settings.top_n}`}>
              <div className="toolbar plain">
                <button className="small" onClick={() => show("Mayores consumidores", "client", data.top_consumers.map((x) => x.client),
                  Object.fromEntries(data.top_consumers.map((x) => [x.client, `${fmt(x.m3_month, 1)} m³/mes · ${fmt(x.pct, 1)} %`])))}>Resaltar en el mapa</button>
              </div>
              <table className="tbl compact mini">
                <thead><tr><th>Cliente</th><th className="num">m³/mes</th><th className="num">%</th></tr></thead>
                <tbody>{data.top_consumers.map((x) => (
                  <tr key={x.client} className="clickable" onClick={() => goto("client", x.client)}>
                    <td>{x.client} <span className="muted">{x.name}</span></td><td className="num">{fmt(x.m3_month, 1)}</td><td className="num">{fmt(x.pct, 1)}</td></tr>))}</tbody>
              </table>
            </Card>
            <Card title="Consumo" sub="clientes activos">
              <div className="kpis">
                <Kpi label="Diario"><b>{fmt(data.consumption.m3_day, 1)} m³</b></Kpi>
                <Kpi label="Mensual"><b>{fmt(data.consumption.m3_month, 0)} m³</b></Kpi>
                <Kpi label="Caudal medio"><b>{fmt(data.consumption.lps, 3)} L/s</b></Kpi>
              </div>
              <div className="cols2">
                <div><h5>Por sector</h5>{groups("Sector", data.consumption.by_sector, "client", "m3")}</div>
                <div><h5>Por ruta</h5>{groups("Ruta", data.consumption.by_route, "client", "m3")}</div>
              </div>
              <h5>Proyección</h5>
              <table className="tbl compact mini"><tbody>{data.consumption.projection.map((x) => (
                <tr key={x.years}><td>A {x.years} años ({x.year})</td><td className="num">{fmt(x.m3_day, 1)} m³/d</td><td className="num">{fmt(x.m3_month, 0)} m³/mes</td><td className="num muted">×{fmt(x.factor, 2)}</td></tr>))}</tbody></table>
              <p className="muted small">{data.consumption.projection_note}</p>
            </Card>
            <Card title="Área operacional" sub={`margen ${fmt(data.area.margin_m, 0)} m`}>
              <div className="kpis"><Kpi label="Superficie"><b>{fmt(data.area.area_km2, 3)} km²</b></Kpi><Kpi label="Hectáreas"><b>{fmt(data.area.area_km2 * 100, 1)} ha</b></Kpi></div>
              <div className="toolbar plain">
                <button className={`small ${areaOn ? "on-toggle" : ""}`} onClick={toggleArea} disabled={!data.area.geometry}>{areaOn ? "Ocultar capa" : "Ver en el mapa"}</button>
                <a className="btn small" href={api.areaGeojsonUrl(pid)}>Exportar GeoJSON</a>
              </div>
            </Card>
            <LossesCard data={data} show={show} goto={goto} reload={load} readOnly={readOnly} pid={pid} net={net} toast={toast} />
            <MaintenanceCard data={data} show={show} goto={goto} />
            <Card title="Estanque y pozo">
              {data.tank_well.tanks.map((t) => (
                <dl key={t.id} className="kv compact">
                  <dt>Estanque</dt><dd><button type="button" className="link" onClick={() => goto("node", t.id)}>{t.id}</button> · {fmt(t.useful_m3, 0)} m³ útiles</dd>
                  <dt>Autonomía</dt><dd className={t.autonomy_h != null && t.autonomy_h < 12 ? "warn-text" : ""}>{fmt(t.autonomy_h, 1)} h <span className="muted small">(a {fmt(t.outflow_lps, 2)} L/s de consumo medio)</span></dd>
                  <dt>Nivel simulado</dt><dd>{fmt(t.level_min, 2)} – {fmt(t.level_max, 2)} m</dd>
                </dl>))}
              {data.tank_well.wells.map((w) => (
                <dl key={w.id} className="kv compact">
                  <dt>Pozo</dt><dd><button type="button" className="link" onClick={() => goto("well", w.id)}>{w.id}</button>{w.pump && <> · bomba <button type="button" className="link" onClick={() => goto("link", w.pump!)}>{w.pump}</button></>}</dd>
                  <dt>Bomba</dt><dd>{fmt(w.pump_hours_day, 1)} h/día · {fmt(w.flow_running_lps, 2)} L/s en marcha</dd>
                  <dt>Usado / autorizado</dt><dd className={w.over_authorized ? "bad-text" : ""}>{fmt(w.m3_day, 0)} / {fmt(w.authorized_m3_day, 0)} m³/día ({fmt(w.use_pct, 0)} %){w.over_authorized ? " · caudal sobre el autorizado" : ""}</dd>
                </dl>))}
              {!data.tank_well.tanks.length && !data.tank_well.wells.length && <p className="muted">Sin estanques ni pozos.</p>}
            </Card>
            <Card title="Alertas" sub={`${data.alerts.length}`} wide>
              {data.alerts.length ? (
                <ul className="alert-list">{data.alerts.map((a, i) => (
                  <li key={i} className={a.severity}>
                    <span className={`sev ${a.severity}`}>{a.topic}</span> {a.text}
                    {a.type && a.id && <button type="button" className="link" onClick={() => goto(a.type as ElType, a.id!)}>ir</button>}
                  </li>))}</ul>
              ) : <p className="muted">Sin alertas: todo cumple.</p>}
            </Card>
          </div>
          {listing && (
            <aside className="summary-list" aria-label={listing.title}>
              <header><b>{listing.title}</b> <span className="muted">({listing.ids.length} {TYPE_NAME[listing.type]})</span>
                <button className="ghost small" onClick={() => { setListing(null); set({ highlight: [] }); }} aria-label="Cerrar lista"><Icon.close /></button></header>
              <ul>{listing.ids.map((id) => (
                <li key={id}><button type="button" className="link" onClick={() => goto(listing.type, id)}>{id}</button>
                  {listing.values?.[id] && <span className="muted small"> {listing.values[id]}</span>}</li>))}</ul>
              {TYPE_TAB[listing.type] && <button className="small" onClick={() => set({ bottomTab: TYPE_TAB[listing.type]! })}>Abrir la pestaña {TYPE_NAME[listing.type]}</button>}
            </aside>
          )}
        </div>
      )}
      {settingsOpen && <SummarySettingsDialog pid={pid} materials={data?.maintenance.life.map((l) => l.material) ?? []}
        onClose={() => setSettingsOpen(false)} onSaved={() => { setSettingsOpen(false); void load(); }} />}
    </div>
  );
}

function Card({ title, sub, wide, children }: { title: string; sub?: string; wide?: boolean; children: React.ReactNode }) {
  return (
    <section className={`card s-card ${wide ? "wide" : ""}`} aria-label={title}>
      <h4>{title}{sub && <span className="muted"> · {sub}</span>}</h4>
      {children}
    </section>
  );
}

function Kpi({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="kpi"><span>{label}</span>{children}</div>;
}

type Show = (title: string, type: ElType, ids: string[], values?: Record<string, string>) => void;

function LossesCard({ data, show, goto, reload, readOnly, pid, net, toast }: {
  data: SummaryResult; show: Show; goto: (t: ElType, id: string) => void; reload: () => Promise<void>; readOnly: boolean; pid: string;
  net: ReturnType<typeof useEditor.getState>["net"]; toast: (t: string, k?: "info" | "error") => void;
}) {
  const lo = data.losses;
  const pipes = useMemo(() => Object.values(net.links).filter((l) => l.kind === "pipe").map((l) => l.id).sort((a, b) => a.localeCompare(b, "es", { numeric: true })), [net.links]);
  const [form, setForm] = useState<LeakEventIn>({ link_id: "", event_date: new Date().toISOString().slice(0, 10), kind: "fuga", flow_lps: null, note: null });
  const [errors, setErrors] = useState<string[]>([]);
  const add = async () => {
    if (!form.link_id) return toast("Elija el tramo del evento.", "error");
    try { await api.addLeaks(pid, [form]); setForm({ ...form, note: null, flow_lps: null }); await reload(); } catch (e) { toast(errorText(e), "error"); }
  };
  const remove = async (id: number) => { if (!window.confirm("¿Eliminar este evento de fuga?")) return; try { await api.deleteLeaks(pid, [id]); await reload(); } catch (e) { toast(errorText(e), "error"); } };
  const upload = async (f: File | undefined) => {
    if (!f) return;
    try {
      const r = await api.importLeaks(pid, f);
      setErrors(r.errors);
      if (r.created) { toast(`${r.created} eventos importados.`); await reload(); }
    } catch (e) { toast(errorText(e), "error"); }
  };
  return (
    <section className="card s-card" aria-label="Pérdidas y filtraciones">
      <h4>Pérdidas y filtraciones <span className="muted">· {lo.total_events} eventos</span></h4>
      {!lo.has_events && !lo.has_production && <p className="notice warn small">{lo.help}</p>}
      <div className="stack-s">
        <div>
          <h5>Agua no contabilizada</h5>
          {lo.balance.length ? (
            <table className="tbl compact mini">
              <thead><tr><th>Sector</th><th className="num">Prod. m³/d</th><th className="num">Cons. m³/d</th><th className="num">ANC</th></tr></thead>
              <tbody>{lo.balance.map((b) => (
                <tr key={b.sector} title={`${b.meters.join(", ")} · ${b.period_from.slice(0, 10)} a ${b.period_to.slice(0, 10)}`}>
                  <td>{b.sector} <span className="muted small">({<N2 n={b.clients.count} onClick={() => show(`Clientes del sector ${b.sector}`, "client", b.clients.ids ?? [])} />} cl.)</span></td>
                  <td className="num">{fmt(b.production_m3_day, 1)}</td><td className="num">{fmt(b.consumption_m3_day, 1)}</td>
                  <td className={`num ${b.nrw_pct != null && b.nrw_pct > 30 ? "bad" : ""}`}>{fmt(b.nrw_pct, 1)} %</td></tr>))}</tbody>
            </table>
          ) : <p className="muted small">Sin datos de producción: registre lecturas del medidor del pozo o de un macromedidor (pestaña Mediciones, medición «medidor»).</p>}
          <h5>Tramos con más eventos</h5>
          {lo.top_links.length ? (
            <table className="tbl compact mini"><tbody>{lo.top_links.map((x) => (
              <tr key={x.link} className="clickable" onClick={() => goto("link", x.link)}>
                <td>{x.link}</td><td className="num">{x.events}</td><td className="muted small">{Object.entries(x.kinds).map(([k, v]) => `${KIND_TXT[k] ?? k} ${v}`).join(" · ")}</td></tr>))}</tbody></table>
          ) : <p className="muted small">Sin datos.</p>}
          {lo.top_links.length > 0 && <button className="small" onClick={() => show("Tramos con eventos", "link", lo.top_links.map((x) => x.link),
            Object.fromEntries(lo.top_links.map((x) => [x.link, `${x.events} eventos`])))}>Ver en el mapa</button>}
        </div>
        <div>
          <h5>Registro de eventos</h5>
          {!readOnly && (
            <div className="leak-form">
              <select value={form.link_id} onChange={(e) => setForm({ ...form, link_id: e.target.value })} aria-label="Tramo"><option value="">Tramo…</option>{pipes.map((p) => <option key={p}>{p}</option>)}</select>
              <input type="date" value={form.event_date} onChange={(e) => setForm({ ...form, event_date: e.target.value })} aria-label="Fecha" />
              <select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value as LeakEventIn["kind"] })} aria-label="Tipo">
                <option value="fuga">Fuga</option><option value="rotura">Rotura</option><option value="reparacion">Reparación</option></select>
              <input inputMode="decimal" placeholder="L/s" value={form.flow_lps ?? ""} aria-label="Caudal estimado (L/s)"
                onChange={(e) => { const v = Number(e.target.value.replace(",", ".")); setForm({ ...form, flow_lps: e.target.value === "" || Number.isNaN(v) ? null : v }); }} />
              <input placeholder="Observación" value={form.note ?? ""} onChange={(e) => setForm({ ...form, note: e.target.value || null })} aria-label="Observación" />
              <button className="small primary" onClick={() => void add()}>Agregar</button>
              <label className="btn small">Importar Excel/CSV<input type="file" accept=".xlsx,.csv" hidden onChange={(e) => { void upload(e.target.files?.[0]); e.target.value = ""; }} /></label>
              <a className="btn small ghost" href={api.leaksTemplateUrl(pid)}>Plantilla</a>
            </div>
          )}
          {errors.length > 0 && <ul className="issues">{errors.slice(0, 6).map((x, i) => <li key={i} className="error">{x}</li>)}</ul>}
          {lo.events.length ? (
            <div className="scroll-box">
              <table className="tbl compact mini">
                <thead><tr><th>Fecha</th><th>Tramo</th><th>Tipo</th><th className="num">L/s</th><th>Observación</th>{!readOnly && <th />}</tr></thead>
                <tbody>{lo.events.map((ev) => (
                  <tr key={ev.id}>
                    <td>{ev.event_date}</td><td><button type="button" className="link" onClick={() => goto("link", ev.link_id)}>{ev.link_id}</button></td>
                    <td>{KIND_TXT[ev.kind]}</td><td className="num">{fmt(ev.flow_lps, 2)}</td><td>{ev.note ?? ""}</td>
                    {!readOnly && <td className="right"><button className="ghost small" title="Eliminar evento (pide confirmación)" aria-label={`Eliminar evento ${ev.id}`} onClick={() => void remove(ev.id)}><Icon.trash /></button></td>}
                  </tr>))}</tbody>
              </table>
            </div>
          ) : <p className="muted small">Sin datos: ingrese eventos con el formulario o importe una planilla (hoja «Pérdidas»: Tramo, Fecha, Tipo, Caudal estimado, Observación).</p>}
        </div>
      </div>
    </section>
  );
}

function N2({ n, onClick }: { n: number; onClick: () => void }) {
  return n ? <button type="button" className="num-link" onClick={onClick}>{n}</button> : <>{n}</>;
}

function MaintenanceCard({ data, show, goto }: { data: SummaryResult; show: Show; goto: (t: ElType, id: string) => void }) {
  const m = data.maintenance;
  const exp = Object.fromEntries(m.pipes.map((p) => [p.link, p.expiry_year ? `vence ${p.expiry_year}` : "sin año"]));
  return (
    <section className="card s-card" aria-label="Mantenimiento a futuro">
      <h4>Mantenimiento a futuro {!(m.life_verified && m.prices_verified) && <span className="badge warn">no verificado</span>}</h4>
      <div className="stack-s">
        <div>
          <h5>Vencimientos</h5>
          <table className="tbl compact mini"><tbody>
            <tr><td>Vencidos</td><td className="num"><N2 n={m.expired.ids.length} onClick={() => show("Tramos vencidos", "link", m.expired.ids, exp)} /></td><td className="num">{fmt(m.expired.km, 3)} km</td></tr>
            {m.due.map((d) => <tr key={d.years}><td>En {d.years} años</td><td className="num"><N2 n={d.ids.length} onClick={() => show(`Tramos que vencen en ${d.years} años`, "link", d.ids, exp)} /></td><td className="num">{fmt(d.km, 3)} km</td></tr>)}
            <tr><td>En mal estado</td><td className="num"><N2 n={m.bad_condition.count} onClick={() => show("Tramos en mal estado", "link", m.bad_condition.ids ?? [], exp)} /></td><td className="num">{fmt(m.bad_condition_km, 3)} km</td></tr>
            {m.unknown_year.count > 0 && <tr><td>Sin año de instalación</td><td className="num"><N2 n={m.unknown_year.count} onClick={() => show("Tramos sin año", "link", m.unknown_year.ids ?? [])} /></td><td /></tr>}
          </tbody></table>
          <h5>Vida útil (años)</h5>
          <p className="small">{m.life.map((l) => `${l.material} ${l.years}`).join(" · ")}</p>
          <p className="muted small">Editable en «Configurar…»: valores sugeridos {m.life_verified ? "revisados" : "no verificado"}.</p>
        </div>
        <div>
          <h5>Plan de renovación (20 años) · {clp(m.plan_cost)}</h5>
          {m.plan.length ? (
            <table className="tbl compact mini">
              <thead><tr><th>Año</th><th className="num">Km</th><th className="num">Costo</th><th>Tramos</th></tr></thead>
              <tbody>{m.plan.map((p) => (
                <tr key={p.year}><td>{p.year}{p.year === m.current_year ? " (incluye vencidos)" : ""}</td><td className="num">{fmt(p.km, 3)}</td><td className="num">{clp(p.cost)}</td>
                  <td>{p.ids.map((i) => <button key={i} type="button" className="link chip-link" onClick={() => goto("link", i)}>{i}</button>)}</td></tr>))}</tbody>
            </table>
          ) : <p className="muted small">Ningún tramo vence en los próximos 20 años.</p>}
        </div>
      </div>
    </section>
  );
}
