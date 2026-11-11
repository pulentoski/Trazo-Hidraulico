// Página «Gestión» de un proyecto (/proyecto/:id/gestion): datos del Resumen con más detalle, gráficos y registros
// de operación de un APR, en 7 pestañas, con filtros de período, sector y ruta, metas configurables e informe mensual.
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router";
import type { GQuery } from "../api/client";
import { api } from "../api/client";
import type { GFilters, GIndicator, GMapRef, GTab, GTable, GestionSettings, ProjectOut, RecordKind, RecordSpec, TabResult } from "../api/types";
import { Modal } from "../components/Dialogs";
import { GChart } from "../components/GChart";
import { PageHeader } from "../components/PageHeader";
import { RecordsPanel } from "../components/RecordsPanel";
import { fmt } from "../lib/format";
import { PATHS } from "../paths";
import { canEdit, useAuth } from "../state/auth";
import { errorText } from "../state/projects";
import { useEditor } from "../state/store";

export const GESTION_TABS: { id: GTab; label: string; records: RecordKind[] }[] = [
  { id: "operacion", label: "Operación", records: ["energia"] },
  { id: "clientes", label: "Clientes y consumo", records: ["lecturas"] },
  { id: "perdidas", label: "Pérdidas", records: [] },
  { id: "activos", label: "Activos y mantenimiento", records: ["mantenciones"] },
  { id: "cumplimiento", label: "Cumplimiento", records: ["cloro", "cortes", "reclamos"] },
  { id: "planificacion", label: "Planificación", records: [] },
  { id: "equipo", label: "Equipo", records: ["mantenciones"] },
];
type Preset = "mes" | "trimestre" | "anio" | "personalizado";
const PRESETS: { id: Preset; label: string }[] = [
  { id: "mes", label: "Mes" }, { id: "trimestre", label: "Trimestre" }, { id: "anio", label: "Año" }, { id: "personalizado", label: "Personalizado" },
];
const STATUS_LABEL: Record<string, string> = { bueno: "Bueno", regular: "Regular", malo: "Malo" };

const iso = (d: Date) => d.toISOString().slice(0, 10);
function lastDayOfMonth(d: Date): Date { return new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 0)); }
function rangeFor(p: Preset, end: Date): [string, string] {
  const last = lastDayOfMonth(end);
  const months = p === "mes" ? 1 : p === "trimestre" ? 3 : 12;
  const first = new Date(Date.UTC(last.getUTCFullYear(), last.getUTCMonth() - months + 1, 1));
  return [iso(first), iso(last)];
}

function num(v: number | null | undefined, unit = "", d?: number): string {
  if (v === null || v === undefined) return "—";
  const digits = d ?? (Number.isInteger(v) || Math.abs(v) >= 1000 ? 0 : Math.abs(v) >= 100 ? 1 : 2);
  return `${fmt(v, digits)}${unit ? ` ${unit}` : ""}`;
}

/** Abre el editor y encuadra/resalta los elementos (el detalle viaja por sessionStorage). */
export function openInMap(navigate: (to: string) => void, pid: string, ref: GMapRef, label: string) {
  try { sessionStorage.setItem(`trazo.ver.${pid}`, JSON.stringify({ ...ref, label })); } catch { /* sin almacenamiento */ }
  navigate(`${PATHS.project(pid)}?ver=gestion`);
}

function TableView({ t, pid, tab, q }: { t: GTable; pid: string; tab: GTab; q: GQuery }) {
  const [all, setAll] = useState(false);
  const rows = all ? t.rows : t.rows.slice(0, 20);
  return (
    <div className="gtable" data-table={t.key}>
      <div className="gtable-head">
        <b>{t.title}</b> <span className="muted small">{t.rows.length} filas</span>
        <span className="spacer" />
        <a className="btn small ghost" href={api.gestionTableUrl(pid, tab, t.key, "xlsx", q)}>Excel</a>
        <a className="btn small ghost" href={api.gestionTableUrl(pid, tab, t.key, "csv", q)}>CSV</a>
      </div>
      {t.rows.length ? (
        <div className="table-scroll">
          <table className="tbl compact">
            <thead><tr>{t.columns.map((c) => <th key={c.key} className={c.num ? "num" : ""}>{c.label}{c.unit ? ` (${c.unit})` : ""}</th>)}</tr></thead>
            <tbody>{rows.map((r, i) => (
              <tr key={i}>{t.columns.map((c) => {
                const v = (r as Record<string, unknown>)[c.key];
                return <td key={c.key} className={c.num ? "num" : ""}>{typeof v === "number" ? num(v) : v === null || v === undefined ? "—" : String(v)}</td>;
              })}</tr>))}</tbody>
          </table>
          {!all && t.rows.length > 20 && <button className="ghost small" onClick={() => setAll(true)}>Ver las {t.rows.length} filas</button>}
        </div>
      ) : <p className="muted small">Sin datos en el período.</p>}
    </div>
  );
}

function IndicatorCard({ i, res, pid, q, onLoad }: { i: GIndicator; res: TabResult; pid: string; q: GQuery; onLoad: (k: RecordKind) => void }) {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const table = i.table ? res.tables.find((t) => t.key === i.table) : undefined;
  const up = (i.delta_pct ?? 0) > 0;
  return (
    <article className={`kpi-card ${i.status ?? ""}`} aria-label={i.label} data-indicator={i.key}>
      <header>
        <h3>{i.label}</h3>
        {i.status && <span className={`status-chip ${i.status}`}>{STATUS_LABEL[i.status]}</span>}
        {i.status && !i.target_verified && <span className="badge warn" title="Meta sugerida: revísela en «Metas»">no verificado</span>}
      </header>
      <div className="kpi-value">
        <b>{num(i.value)}</b> <span className="unit">{i.unit}</span>
        {i.delta_pct !== null && i.delta_pct !== undefined && (
          <span className={`delta ${up ? "up" : i.delta_pct < 0 ? "down" : ""}`} title={`Período anterior: ${num(i.previous, i.unit)}`}>
            {up ? "▲" : i.delta_pct < 0 ? "▼" : "="} {fmt(Math.abs(i.delta_pct), 1)} %
          </span>)}
        {i.previous !== null && i.previous !== undefined && <span className="muted small"> antes: {num(i.previous, i.unit)}</span>}
      </div>
      {i.note && <p className="muted small kpi-note">{i.note}</p>}
      {i.empty && (
        <div className="empty-hint" role="note">
          <p><b>Falta:</b> {i.empty.missing}.</p>
          <p className="small"><b>Cómo cargarlo:</b> {i.empty.how}.</p>
          {i.empty.record && <button className="small" onClick={() => onLoad(i.empty!.record!)}>Cargar datos</button>}
        </div>
      )}
      {i.chart && <GChart chart={i.chart} />}
      <footer>
        {table && <button className="ghost small" aria-expanded={open} onClick={() => setOpen(!open)}>{open ? "Ocultar detalle" : "Detalle"}</button>}
        {table && <a className="btn small ghost" href={api.gestionTableUrl(pid, res.tab, table.key, "xlsx", q)}>Excel</a>}
        {table && <a className="btn small ghost" href={api.gestionTableUrl(pid, res.tab, table.key, "csv", q)}>CSV</a>}
        {i.map && i.map.ids.length > 0 && <button className="ghost small" onClick={() => openInMap(navigate, pid, i.map!, i.label)}>Ver en el mapa</button>}
      </footer>
      {open && table && <TableView t={table} pid={pid} tab={res.tab} q={q} />}
    </article>
  );
}

function Calendar({ items }: { items: { date: string; kind: string; element?: string | null; status: string; assignee?: string | null }[] }) {
  const [month, setMonth] = useState(() => { const d = new Date(); return new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), 1)); });
  const y = month.getUTCFullYear();
  const m = month.getUTCMonth();
  const days = new Date(Date.UTC(y, m + 1, 0)).getUTCDate();
  const offset = (new Date(Date.UTC(y, m, 1)).getUTCDay() + 6) % 7;
  const key = (d: number) => `${y}-${String(m + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
  const by = new Map<string, typeof items>();
  for (const it of items) by.set(it.date, [...(by.get(it.date) ?? []), it]);
  const overdue = items.filter((x) => x.status === "atrasada");
  const raw = month.toLocaleDateString("es-CL", { month: "long", year: "numeric", timeZone: "UTC" });
  const label = raw.charAt(0).toUpperCase() + raw.slice(1);
  return (
    <section className="calendar-wrap" aria-label="Calendario de mantenciones">
      <div className="cal-head">
        <button className="ghost small" onClick={() => setMonth(new Date(Date.UTC(y, m - 1, 1)))} aria-label="Mes anterior">◀</button>
        <b>{label}</b>
        <button className="ghost small" onClick={() => setMonth(new Date(Date.UTC(y, m + 1, 1)))} aria-label="Mes siguiente">▶</button>
      </div>
      <div className="calendar">
        {["L", "M", "M", "J", "V", "S", "D"].map((d, i) => <div key={i} className="cal-dow">{d}</div>)}
        {Array.from({ length: offset }, (_, i) => <div key={`o${i}`} />)}
        {Array.from({ length: days }, (_, i) => (
          <div key={i} className="cal-day">
            <span className="cal-n">{i + 1}</span>
            {(by.get(key(i + 1)) ?? []).map((it, k) => (
              <span key={k} className={`cal-item ${it.status}`} title={`${it.kind} ${it.element ?? ""} · ${it.assignee ?? "sin responsable"}`}>{it.kind} {it.element ?? ""}</span>
            ))}
          </div>
        ))}
      </div>
      <div className="overdue">
        <h4>Atrasadas ({overdue.length})</h4>
        {overdue.length ? <ul>{overdue.map((o, i) => <li key={i}><b>{o.date}</b> · {o.kind} {o.element ?? ""} · {o.assignee ?? "sin responsable"}</li>)}</ul>
          : <p className="muted small">Ninguna mantención atrasada.</p>}
      </div>
    </section>
  );
}

function TargetsDialog({ pid, onClose, onSaved }: { pid: string; onClose: () => void; onSaved: () => void }) {
  const toast = useEditor((s) => s.toast);
  const [st, setSt] = useState<GestionSettings | null>(null);
  useEffect(() => { api.gestionSettings(pid).then(setSt).catch((e) => toast(errorText(e), "error")); }, [pid, toast]);
  if (!st) return <Modal title="Metas e indicadores" onClose={onClose}><p className="muted">Cargando…</p></Modal>;
  type T = NonNullable<GestionSettings["targets"]>[string];
  const tg = st.targets ?? {};
  const setT = (k: string, patch: Partial<T>) => setSt({ ...st, targets: { ...tg, [k]: { ...tg[k], ...patch } } });
  const n = (v: string) => (v.trim() === "" ? null : Number(v.replace(",", ".")));
  const save = async () => {
    try { await api.saveGestionSettings(pid, st); toast("Metas guardadas."); onSaved(); onClose(); } catch (e) { toast(errorText(e), "error"); }
  };
  const reset = async () => {
    if (!window.confirm("¿Volver a las metas y rangos sugeridos?")) return;
    try { setSt(await api.resetGestionSettings(pid)); onSaved(); } catch (e) { toast(errorText(e), "error"); }
  };
  return (
    <Modal title="Metas e indicadores" onClose={onClose} wide>
      <p className="muted small">Umbrales por indicador: «bueno» y «malo» (entre ambos, «regular»). Los valores sugeridos quedan marcados
        «no verificado» hasta que los revise y marque «Verificada».</p>
      <div className="table-scroll targets">
        <table className="tbl compact">
          <thead><tr><th>Indicador</th><th>Unidad</th><th className="num">Bueno</th><th className="num">Malo</th><th>Mayor es mejor</th><th>Verificada</th></tr></thead>
          <tbody>{Object.entries(tg).map(([k, t]) => (
            <tr key={k}>
              <td>{t.label}</td><td>{t.unit}</td>
              <td><input className="num-in" aria-label={`${t.label}: bueno`} defaultValue={String(t.good)} onBlur={(e) => setT(k, { good: n(e.target.value) ?? t.good })} /></td>
              <td><input className="num-in" aria-label={`${t.label}: malo`} defaultValue={String(t.bad)} onBlur={(e) => setT(k, { bad: n(e.target.value) ?? t.bad })} /></td>
              <td><input type="checkbox" checked={t.higher_is_better} onChange={(e) => setT(k, { higher_is_better: e.target.checked })} /></td>
              <td><input type="checkbox" aria-label={`${t.label}: verificada`} checked={!!t.verified} onChange={(e) => setT(k, { verified: e.target.checked })} /></td>
            </tr>))}</tbody>
        </table>
      </div>
      <div className="targets-extra">
        <label className="field"><span>Derecho de agua (L/s)</span><input defaultValue={st.water_right_lps ?? ""} placeholder="caudal autorizado del pozo"
          onBlur={(e) => setSt({ ...st, water_right_lps: n(e.target.value) })} /></label>
        <label className="field"><span>Volumen anual del derecho (m³)</span><input defaultValue={st.water_right_m3_year ?? ""} placeholder="derecho × año"
          onBlur={(e) => setSt({ ...st, water_right_m3_year: n(e.target.value) })} /></label>
        <label className="field"><span>Cloro libre mínimo (mg/L)</span><input defaultValue={st.chlorine_min} onBlur={(e) => setSt({ ...st, chlorine_min: n(e.target.value) ?? st.chlorine_min })} /></label>
        <label className="field"><span>Cloro libre máximo (mg/L)</span><input defaultValue={st.chlorine_max} onBlur={(e) => setSt({ ...st, chlorine_max: n(e.target.value) ?? st.chlorine_max })} /></label>
        <label className="field"><span>Rango de cloro verificado</span><input type="checkbox" checked={!!st.chlorine_verified} onChange={(e) => setSt({ ...st, chlorine_verified: e.target.checked })} /></label>
        <label className="field"><span>Consumo típico de un cliente nuevo (m³/mes)</span><input defaultValue={st.typical_client_m3_month ?? ""} placeholder="promedio de los residenciales"
          onBlur={(e) => setSt({ ...st, typical_client_m3_month: n(e.target.value) })} /></label>
        <label className="field"><span>Tope de clientes a probar (capacidad)</span><input defaultValue={st.capacity_max_clients} onBlur={(e) => setSt({ ...st, capacity_max_clients: n(e.target.value) ?? st.capacity_max_clients })} /></label>
      </div>
      <div className="modal-actions">
        <button className="ghost" onClick={() => void reset()}>Valores sugeridos</button>
        <button className="ghost" onClick={onClose}>Cancelar</button>
        <button className="primary" onClick={() => void save()}>Guardar metas</button>
      </div>
    </Modal>
  );
}

export function GestionPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const toast = useEditor((s) => s.toast);
  const roleIn = useAuth((s) => s.roleIn);
  const [project, setProject] = useState<ProjectOut | null>(null);
  const [filters, setFilters] = useState<GFilters | null>(null);
  const [specs, setSpecs] = useState<RecordSpec[]>([]);
  const [res, setRes] = useState<TabResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [targets, setTargets] = useState(false);
  const [openRecord, setOpenRecord] = useState<{ kind: RecordKind; n: number } | null>(null);
  const tab = (GESTION_TABS.find((t) => t.id === params.get("pestana"))?.id ?? "operacion") as GTab;
  const preset = (params.get("periodo") as Preset) || "anio";
  const sector = params.get("sector") ?? "";
  const ruta = params.get("ruta") ?? "";
  const update = (patch: Record<string, string | null>) => {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(patch)) { if (v === null || v === "") next.delete(k); else next.set(k, v); }
    setParams(next, { replace: true });
  };

  useEffect(() => {
    let alive = true;
    Promise.all([api.getProject(id), api.gestionFilters(id), api.recordSpecs(id)])
      .then(([p, f, s]) => { if (alive) { setProject(p); setFilters(f); setSpecs(s); } })
      .catch((e) => { toast(`No se pudo abrir «Gestión»: ${errorText(e)}`, "error"); navigate(PATHS.home, { replace: true }); });
    return () => { alive = false; };
  }, [id, navigate, toast]);

  const endRef = filters?.data_end ? new Date(`${filters.data_end}T00:00:00Z`) : new Date();
  const [defStart, defEnd] = rangeFor(preset === "personalizado" ? "anio" : preset, endRef);
  const desde = preset === "personalizado" ? params.get("desde") ?? defStart : defStart;
  const hasta = preset === "personalizado" ? params.get("hasta") ?? defEnd : defEnd;
  const q: GQuery = useMemo(() => ({ desde, hasta, sector: sector || undefined, ruta: ruta || undefined }), [desde, hasta, sector, ruta]);

  const load = useCallback(() => {
    if (!filters) return;
    setLoading(true);
    api.gestionTab(id, tab, q).then(setRes).catch((e) => toast(errorText(e), "error")).finally(() => setLoading(false));
  }, [id, tab, q, filters, toast]);
  useEffect(() => { load(); }, [load]);

  const readOnly = project ? !canEdit(roleIn(project.org_id)) : true;
  const tabDef = GESTION_TABS.find((t) => t.id === tab)!;
  const recordSpecs = tabDef.records.map((k) => specs.find((s) => s.kind === k)).filter((s): s is RecordSpec => !!s);
  const loadRecord = (k: RecordKind) => {
    const owner = GESTION_TABS.find((t) => t.records.includes(k));
    if (owner && owner.id !== tab) update({ pestana: owner.id });
    setOpenRecord({ kind: k, n: Date.now() });
  };
  const usedTables = new Set(res?.indicators.map((i) => i.table).filter(Boolean));
  const calendar = (res?.extra as { calendar?: { date: string; kind: string; element?: string | null; status: string; assignee?: string | null }[] } | undefined)?.calendar;

  return (
    <div className="page gestion-page">
      <PageHeader />
      <main className="page-body gestion">
        <div className="gestion-head">
          <div>
            <button className="ghost small" onClick={() => navigate(PATHS.project(id))}>← Editor</button>
            <h1 className="page-title">Gestión <span className="muted">· {project?.name ?? "…"}</span></h1>
            {filters?.model_version != null && <p className="muted small">Versión del modelo {filters.model_version}
              {filters.data_start ? ` · datos desde ${filters.data_start} hasta ${filters.data_end}` : " · sin registros de operación todavía"}</p>}
          </div>
          <div className="inline">
            <button onClick={() => setTargets(true)}>Metas</button>
            <a className="btn primary" href={api.gestionReportUrl(id, "html", q)} target="_blank" rel="noopener">Informe mensual</a>
            <a className="btn" href={api.gestionReportUrl(id, "xlsx", q)}>Informe Excel</a>
          </div>
        </div>
        <section className="gestion-filters" aria-label="Filtros">
          <div className="seg" role="group" aria-label="Período">
            {PRESETS.map((p) => <button key={p.id} className={preset === p.id ? "on" : ""} onClick={() => update({ periodo: p.id === "anio" ? null : p.id,
              ...(p.id === "personalizado" ? { desde, hasta } : { desde: null, hasta: null }) })}>{p.label}</button>)}
          </div>
          <label className="field inline-field"><span>Desde</span>
            <input type="date" value={desde} aria-label="Desde" disabled={preset !== "personalizado"} onChange={(e) => update({ desde: e.target.value })} /></label>
          <label className="field inline-field"><span>Hasta</span>
            <input type="date" value={hasta} aria-label="Hasta" disabled={preset !== "personalizado"} onChange={(e) => update({ hasta: e.target.value })} /></label>
          <label className="field inline-field"><span>Sector</span>
            <select value={sector} aria-label="Sector" onChange={(e) => update({ sector: e.target.value })}>
              <option value="">Todos</option>{filters?.sectors.map((s) => <option key={s} value={s}>{s}</option>)}
            </select></label>
          <label className="field inline-field"><span>Ruta</span>
            <select value={ruta} aria-label="Ruta" onChange={(e) => update({ ruta: e.target.value })}>
              <option value="">Todas</option>{filters?.routes.map((r) => <option key={r} value={r}>{r}</option>)}
            </select></label>
          {res && <span className="muted small">Comparado con {res.period.prev_start} a {res.period.prev_end}</span>}
        </section>
        <nav className="gestion-tabs" role="tablist" aria-label="Pestañas de gestión">
          {GESTION_TABS.map((t) => (
            <button key={t.id} role="tab" aria-selected={tab === t.id} className={tab === t.id ? "on" : ""} onClick={() => update({ pestana: t.id === "operacion" ? null : t.id })}>{t.label}</button>
          ))}
        </nav>
        <div className="gestion-body" role="tabpanel" aria-label={tabDef.label} aria-busy={loading}>
          {!res ? <p className="muted">Cargando…</p> : (<>
            {(res.notes ?? []).map((n) => <p key={n} className="notice small">{n}</p>)}
            <div className="kpi-grid">
              {res.indicators.map((i) => <IndicatorCard key={i.key} i={i} res={res} pid={id} q={q} onLoad={loadRecord} />)}
            </div>
            {(res.charts ?? []).some((c) => c.series.some((s) => s.values.some((v) => v !== null))) && (
              <section className="extra-charts" aria-label="Gráficos">
                {(res.charts ?? []).map((c) => <div key={c.title} className="kpi-card chart-card"><GChart chart={c} /></div>)}
              </section>
            )}
            {tab === "activos" && calendar && <Calendar items={calendar} />}
            {tab === "perdidas" && (
              <p className="muted small">Los eventos de fuga, rotura y reparación se registran en el editor: Resumen → Pérdidas (manual o planilla).
                {" "}<button className="link" onClick={() => navigate(PATHS.project(id))}>Abrir el editor</button></p>
            )}
            <section className="detail-tables" aria-label="Tablas de detalle">
              <h2>Tablas de detalle</h2>
              {res.tables.filter((t) => !usedTables.has(t.key) || t.rows.length).map((t) => (
                <details key={t.key} className="table-details"><summary>{t.title} <span className="muted small">({t.rows.length})</span></summary>
                  <TableView t={t} pid={id} tab={tab} q={q} /></details>
              ))}
            </section>
            {recordSpecs.length > 0 && (
              <section className="records" aria-label="Registros">
                <h2>Registros</h2>
                {recordSpecs.map((s) => <RecordsPanel key={s.kind} pid={id} spec={s} readOnly={readOnly} onChanged={load}
                  openNonce={openRecord?.kind === s.kind ? openRecord.n : undefined} />)}
              </section>
            )}
          </>)}
        </div>
      </main>
      {targets && <TargetsDialog pid={id} onClose={() => setTargets(false)} onSaved={load} />}
    </div>
  );
}
