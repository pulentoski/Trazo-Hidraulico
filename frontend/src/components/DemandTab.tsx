// Pestaña «Demanda»: proyección de población y caudales de diseño por año, y escenarios de demanda.
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { DemandInputs, DemandResult } from "../api/types";
import { fmt } from "../lib/format";
import { flushPending } from "../state/live";
import { errorText, openProject } from "../state/projects";
import { useEditor } from "../state/store";
import { Help, NumField } from "./Fields";
import { Skeleton } from "./Skeleton";

export function DemandTab() {
  const { project, toast, options } = useEditor();
  const [res, setRes] = useState<DemandResult | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (project) api.demandProjection(project.id).then(setRes).catch((e) => toast(errorText(e), "error"));
  }, [project, toast]);
  if (!project || !res) return <div className="pad"><Skeleton /></div>;
  const inp = res.inputs;
  const save = async (patch: Partial<DemandInputs>) => {
    try { setRes(await api.saveDemandProjection(project.id, { ...inp, ...patch })); } catch (e) { toast(errorText(e), "error"); }
  };
  const apply = async (sc: "base" | "actual" | "horizonte") => {
    setBusy(true);
    try {
      if (!(await flushPending())) throw new Error("No se pudieron guardar los cambios pendientes.");
      const r = await api.applyDemandScenario(project.id, sc);
      await openProject(project.id);
      setRes(await api.demandProjection(project.id));
      toast(`Escenario aplicado: demandas × ${fmt(r.multiplier, 3)} (versión ${r.version}).`);
    } catch (e) { toast(errorText(e), "error"); } finally { setBusy(false); }
  };
  const num = (label: string, key: keyof DemandInputs, unit?: string, digits = 2) => (
    <NumField label={label} unit={unit} digits={digits} value={inp[key] as number | null}
      onCommit={(v) => v !== null && void save({ [key]: key.endsWith("year") || key === "horizon_years" || key === "base_connections" ? Math.round(v) : v } as Partial<DemandInputs>)} />
  );
  const growth = inp.growth ?? [];
  const active = options.demand_scenario ?? "base";

  return (
    <div className="demand-tab">
      <div className="demand-inputs">
        <p className="badge warn">no verificado</p>
        <p className="muted small">{res.note}</p>
        <label className="field"><span>Base</span>
          <select value={inp.base_mode ?? "arranques"} onChange={(e) => void save({ base_mode: e.target.value as DemandInputs["base_mode"] })}>
            <option value="arranques">Arranques (clientes) × hab/vivienda</option><option value="poblacion">Población</option>
          </select></label>
        {inp.base_mode === "poblacion" ? num("Población año base", "base_population", "hab", 0) : num("Arranques año base", "base_connections", "", 0)}
        {num("Habitantes por vivienda", "persons_per_dwelling", "hab/viv")}
        {num("Año base", "base_year", "", 0)}
        {num("Año que representa el modelo", "model_year", "", 0)}
        {num("Año actual", "current_year", "", 0)}
        {num("Horizonte", "horizon_years", "años", 0)}
        <fieldset><legend>Tasas de crecimiento <Help text="Cada tramo rige desde su año (p. ej. 5 % desde 2017 y 3 % desde 2029, como la planilla)." /></legend>
          {growth.map((g, i) => (
            <div className="grid2" key={i}>
              <NumField label="Desde el año" digits={0} value={g.from_year} onCommit={(v) => v !== null && void save({ growth: growth.map((x, k) => (k === i ? { ...x, from_year: Math.round(v) } : x)) })} />
              <NumField label="Tasa" unit="%/año" value={g.rate_pct} onCommit={(v) => v !== null && void save({ growth: growth.map((x, k) => (k === i ? { ...x, rate_pct: v } : x)) })} />
            </div>
          ))}
          <div className="toolbar">
            <button className="small" onClick={() => void save({ growth: [...growth, { from_year: (growth[growth.length - 1]?.from_year ?? inp.base_year) + 10, rate_pct: 1 }] })}>+ Tramo</button>
            {growth.length > 1 && <button className="small ghost" onClick={() => void save({ growth: growth.slice(0, -1) })}>Quitar último</button>}
          </div>
        </fieldset>
        {num("Dotación", "dotation_lphd", "L/hab/día", 1)}
        {num("Pérdidas", "losses_pct", "%", 1)}
        {num("Coef. día de máximo consumo", "coef_day", "", 2)}
        {num("Coef. hora de máximo consumo", "coef_hour", "", 2)}
        {num("Horas de bombeo", "pump_hours", "h/día", 1)}
        {num("Volumen de regulación", "regulation_pct", "% vol. diario QMD", 1)}
        <label className="check"><input type="checkbox" checked={!!inp.scenario_peak_day} onChange={(e) => void save({ scenario_peak_day: e.target.checked })} />
          Los escenarios aplican también el coeficiente de día máximo</label>
        <div className="toolbar">
          <a className="btn small" href={api.demandXlsxUrl(project.id)}>Exportar Excel</a>
          {res.customized && <button className="small ghost" onClick={async () => setRes(await api.resetDemandProjection(project.id))}>Valores por defecto</button>}
        </div>
      </div>
      <div className="demand-out">
        <div className="toolbar">
          <strong>Escenarios de demanda</strong>
          <Help text="Escalan las demandas de nudos y clientes (multiplicador global de EPANET) según la población del año respecto de la del año que representa el modelo. Crean una versión nueva." />
          {res.scenarios.map((s) => (
            <button key={s.id} className={`small ${active === s.id ? "primary" : ""}`} disabled={busy} onClick={() => void apply(s.id)}>
              {s.name} · ×{fmt(s.multiplier, 3)}</button>
          ))}
        </div>
        <table className="tbl compact">
          <thead><tr><th>Año</th><th className="num">Población</th><th className="num">Clientes</th><th className="num">Consumo (m³/año)</th><th className="num">Producción (m³/año)</th>
            <th className="num">Qmedio (L/s)</th><th className="num">QMD (L/s)</th><th className="num">QMH (L/s)</th><th className="num">Bombeo (L/s)</th><th className="num">Regulación (m³)</th></tr></thead>
          <tbody>
            {res.rows.map((r) => (
              <tr key={r.year} className={r.year === inp.current_year ? "current" : ""}>
                <td>{r.year}</td><td className="num">{fmt(r.population, 0)}</td><td className="num">{fmt(r.clients, 0)}</td>
                <td className="num">{fmt(r.consumption_m3, 0)}</td><td className="num">{fmt(r.production_m3, 0)}</td><td className="num">{fmt(r.qmed_lps, 2)}</td>
                <td className="num">{fmt(r.qmd_lps, 2)}</td><td className="num">{fmt(r.qmh_lps, 2)}</td><td className="num">{fmt(r.pump_lps, 2)}</td><td className="num">{fmt(r.regulation_m3, 1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
